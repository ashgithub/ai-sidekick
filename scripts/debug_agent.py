#!/usr/bin/env python3
from __future__ import annotations

import argparse
import ast
import json
import sys
from pathlib import Path
from typing import Any

from ai_tools.agent_runtime import AgentRequest, DeepAgentRuntime
from ai_tools.utils.config import get_settings


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Simple non-UI deep-agent debug runner")
    parser.add_argument("--text", help="Input text to process")
    parser.add_argument("--app", help="Application context hint")
    parser.add_argument("--nudge", help="Nudge hint")
    parser.add_argument("--model", help="Override model name")
    parser.add_argument("--verbose-events", action="store_true", help="Print full pretty event payloads")
    parser.add_argument("--timeout-seconds", type=int, default=30, help="Stream timeout")
    parser.add_argument("--max-events", type=int, default=500, help="Maximum streamed events")
    return parser.parse_args()


def _build_request(args: argparse.Namespace, text: str) -> AgentRequest:
    nudge = (args.nudge or "").strip().lower()
    options: dict[str, Any] = {}
    if nudge and nudge != "auto":
        options["nudge"] = nudge
    return AgentRequest(
        input_text=text,
        ui_tab=nudge or "universal",
        app_context=args.app,
        options=options,
        selected_model=args.model,
    )


def _parse_event_text(event_text: str) -> tuple[str, dict[str, Any] | None]:
    lines = event_text.splitlines()
    if not lines:
        return "values", None
    header = lines[0].strip()
    mode = "values"
    inline_payload = ""
    if header.startswith("[") and "]" in header:
        right_bracket = header.index("]")
        mode = header[1:right_bracket]
        inline_payload = header[right_bracket + 1 :].strip()
    payload_lines: list[str] = []
    if inline_payload:
        payload_lines.append(inline_payload)
    payload_lines.extend(lines[1:])
    if not payload_lines:
        return mode, None
    payload_text = "\n".join(payload_lines)
    try:
        payload = json.loads(payload_text)
    except json.JSONDecodeError:
        try:
            payload = ast.literal_eval(payload_text)
        except (ValueError, SyntaxError):
            return mode, None
    return mode, payload if isinstance(payload, dict) else None


def _count_skill_reads(payload: dict[str, Any]) -> int:
    count = 0
    for value in payload.values():
        if isinstance(value, dict):
            count += _count_skill_reads(value)
            continue
        if isinstance(value, list):
            for item in value:
                if isinstance(item, dict):
                    count += _count_skill_reads(item)
    for key, value in payload.items():
        if key == "tool_calls" and isinstance(value, list):
            for tool_call in value:
                if not isinstance(tool_call, dict):
                    continue
                args = tool_call.get("args", {})
                if isinstance(args, dict):
                    file_path = str(args.get("file_path", ""))
                    if "skills/" in file_path and file_path.endswith("/SKILL.md"):
                        count += 1
    return count


def _collect_tool_calls(value: Any) -> list[dict[str, Any]]:
    calls: list[dict[str, Any]] = []
    if isinstance(value, dict):
        for key, item in value.items():
            if key == "tool_calls" and isinstance(item, list):
                for tool_call in item:
                    if isinstance(tool_call, dict):
                        calls.append(tool_call)
            calls.extend(_collect_tool_calls(item))
    elif isinstance(value, list):
        for item in value:
            calls.extend(_collect_tool_calls(item))
    return calls


def _tool_call_file_path(tool_call: dict[str, Any]) -> str:
    args = tool_call.get("args", {})
    if isinstance(args, dict):
        return str(args.get("file_path", ""))
    if isinstance(args, str):
        try:
            parsed_args = json.loads(args)
        except json.JSONDecodeError:
            return ""
        if isinstance(parsed_args, dict):
            return str(parsed_args.get("file_path", ""))
    return ""


def _compact_event_lines(event_text: str) -> list[str]:
    mode, payload = _parse_event_text(event_text)
    if payload is None:
        return [f"[{mode}] event"]

    if "MemoryMiddleware.before_agent" in payload:
        mem = payload.get("MemoryMiddleware.before_agent", {})
        memory_contents = mem.get("memory_contents", {}) if isinstance(mem, dict) else {}
        return [f"[memory] loaded ({len(memory_contents)})"]

    if "SkillsMiddleware.before_agent" in payload:
        meta = payload.get("SkillsMiddleware.before_agent", {})
        skills_metadata = meta.get("skills_metadata", []) if isinstance(meta, dict) else []
        return [f"[skills] metadata loaded ({len(skills_metadata)})"]

    if "PatchToolCallsMiddleware.before_agent" in payload:
        return ["[prompt] patched messages"]

    if "TodoListMiddleware.after_model" in payload:
        return ["[todo] after_model"]

    if "model" in payload and isinstance(payload["model"], dict):
        model_payload = payload["model"]
        lines = ["[model] update"]
        messages = model_payload.get("messages")
        if isinstance(messages, list) and messages:
            lines.append(f"  messages={len(messages)}")
        tool_calls = _collect_tool_calls(model_payload)
        if tool_calls:
            lines.append(f"  tool_calls={len(tool_calls)}")
        if "structured_response" in model_payload:
            lines.append("  structured response available")
        return lines

    tool_calls = _collect_tool_calls(payload)
    if tool_calls:
        return [f"[tool] calls={len(tool_calls)}"]

    messages = payload.get("messages")
    if isinstance(messages, list) and messages:
        lines = ["[messages] update"]
        if "structured_response" in payload:
            lines.append("  structured response available")
        return lines

    if "structured_response" in payload:
        return ["[result-ready] structured response available"]

    return [f"[{mode}] event"]


def _update_event_stats(stats: dict[str, int | bool], event_text: str) -> None:
    mode, payload = _parse_event_text(event_text)
    stats["events"] = int(stats.get("events", 0)) + 1
    if mode in {"updates", "values"}:
        stats["updates"] = int(stats.get("updates", 0)) + 1
    if payload is None:
        return
    if "SkillsMiddleware.before_agent" in payload:
        meta = payload.get("SkillsMiddleware.before_agent", {})
        skills_metadata = meta.get("skills_metadata", []) if isinstance(meta, dict) else []
        stats["skills_registered"] = len(skills_metadata)
    if "structured_response" in payload:
        stats["structured_seen"] = True
    if "model" in payload and isinstance(payload["model"], dict) and "structured_response" in payload["model"]:
        stats["structured_seen"] = True
    if "model" in payload and isinstance(payload["model"], dict):
        model_payload = payload["model"]
        model_tool_calls = _collect_tool_calls(model_payload)
        stats["tool_calls"] = int(stats.get("tool_calls", 0)) + len(model_tool_calls)
        model_skill_reads = 0
        for tool_call in model_tool_calls:
            file_path = _tool_call_file_path(tool_call)
            if "skills/" in file_path and file_path.endswith("/SKILL.md"):
                model_skill_reads += 1
        stats["skill_reads"] = int(stats.get("skill_reads", 0)) + model_skill_reads
        return

    payload_tool_calls = _collect_tool_calls(payload)
    stats["tool_calls"] = int(stats.get("tool_calls", 0)) + len(payload_tool_calls)
    payload_skill_reads = 0
    for tool_call in payload_tool_calls:
        file_path = _tool_call_file_path(tool_call)
        if "skills/" in file_path and file_path.endswith("/SKILL.md"):
            payload_skill_reads += 1
    stats["skill_reads"] = int(stats.get("skill_reads", 0)) + payload_skill_reads


def main() -> int:
    args = _parse_args()
    text = (args.text or "").strip()
    if not text and not sys.stdin.isatty():
        text = sys.stdin.read().strip()
    if not text:
        print("error: provide --text or pipe stdin", file=sys.stderr)
        return 2

    settings = get_settings()
    runtime = DeepAgentRuntime(settings, project_root=Path.cwd())
    request = _build_request(args, text)
    schema_model, render_kind = runtime.prepare_request_context(request)

    print("[request]")
    print(runtime.preview_execution_summary(request))

    stats: dict[str, int | bool] = {
        "events": 0,
        "updates": 0,
        "skills_registered": 0,
        "tool_calls": 0,
        "skill_reads": 0,
        "structured_seen": False,
    }

    def emit_event(event_text: str) -> None:
        _update_event_stats(stats, event_text)
        if args.verbose_events:
            print(event_text)
            return
        for line in _compact_event_lines(event_text):
            print(line)

    structured = runtime.invoke_streamed(
        request,
        schema_model,
        timeout_seconds=args.timeout_seconds,
        max_events=args.max_events,
        event_callback=emit_event,
        debug=False,
    )

    primary = runtime._primary_output(render_kind, structured)
    print("[result]")
    print(json.dumps(structured, indent=2, ensure_ascii=False, sort_keys=True))
    print("[primary]")
    print(primary)
    print("[summary]")
    print(
        "events={events} updates={updates} skills_registered={skills_registered} "
        "tool_calls={tool_calls} skill_reads={skill_reads} structured_seen={structured_seen}".format(
            **stats
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
