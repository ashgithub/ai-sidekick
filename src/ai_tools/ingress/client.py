"""Small clients for submitting local work to the resident sidekick."""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from urllib import request

from ai_tools.codex_bridge.config import load_web_panel_config


def build_ai_tools_prompt(*, text: str, app_context: str | None = None, nudge: str | None = None) -> str:
    lines = [
        "AI Tools request",
        "",
        "Use the Codex model configured for this app-server session. Do not select or mention a separate model.",
        "Transform the input using the requested context. Return JSON only.",
        "",
        "Expected JSON shape:",
        "{",
        '  "render_kind": "single_text | text_pair | alternatives",',
        '  "primary_output": "string",',
        '  "structured_output": {',
        '    "text": "string",',
        '    "corrected": "string",',
        '    "rewritten": "string",',
        '    "alternatives": [{"value": "string", "explanation": "string"}]',
        "  }",
        "}",
        "",
        "Routing rules:",
        "- Slack/email/proofread/rewrite requests should use render_kind=text_pair with corrected and rewritten.",
        "- Terminal/command requests should use render_kind=alternatives with one to three safe command alternatives.",
        "- Explain/ask requests should use render_kind=single_text with text.",
        "- primary_output should be rewritten for text_pair, the first alternative value for alternatives, or text for single_text.",
        "",
        "Skill instructions:",
        "- For Slack text, follow skills/proofread-slack/SKILL.md.",
        "- For email text, follow skills/proofread-email/SKILL.md.",
        "- For general proofreading, follow skills/proofread-general/SKILL.md.",
        "- For command requests, follow skills/commands/SKILL.md.",
        "- For explanations, follow skills/explain/SKILL.md.",
        "- For direct Q&A, follow skills/ask/SKILL.md.",
        "- These skill files are prepared under the current Codex cwd; do not search outside the cwd for them unless a listed file is missing.",
        "",
    ]
    if app_context:
        lines.append(f"App context: {app_context}")
    if nudge:
        lines.append(f"Nudge: {nudge}")
    if app_context or nudge:
        lines.append("")
    lines.extend(["Input:", text.strip()])
    return "\n".join(lines).strip()


def build_zsh_prompt(request_text: str) -> str:
    return (
        "Convert this natural language request into one safe zsh command for macOS/Linux. "
        "Return only the command, with no Markdown, no explanation, and no execution. "
        "Prefer rg, fd, bat, zoxide, and safe read-only commands when they fit. "
        f"Request: {request_text.strip()}"
    )


def strip_command_response(response_text: str) -> str:
    generated = response_text.replace("\r", "").strip()
    for fence in ("```zsh\n", "```sh\n", "```bash\n", "```\n"):
        if generated.startswith(fence):
            generated = generated.removeprefix(fence)
            break
    if generated.endswith("\n```"):
        generated = generated.removesuffix("\n```")
    if generated.endswith("```"):
        generated = generated.removesuffix("```")
    return generated.strip()


def parse_submit_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Submit an AI Tools request to the resident Codex sidekick")
    parser.add_argument("--text", help="Input text. Defaults to stdin when omitted.")
    parser.add_argument("--app", dest="app_context", help="Application context hint")
    parser.add_argument("--nudge", help="Nudge hint for the request")
    parser.add_argument("--tab", help="Legacy alias that maps to nudge")
    parser.add_argument("--intent", choices=["new", "continue", "steer", "auto"], default="new")
    parser.add_argument("--prompt-kind", choices=["ai_tools", "zsh"], default="ai_tools")
    parser.add_argument("--wait", action="store_true", help="Wait for the run to finish and print the final response")
    parser.add_argument("--command-output", action="store_true", help="Strip command-generation fences when printing wait output")
    parser.add_argument("--source-kind", default="ai_tools")
    parser.add_argument("--source-label", default="AI Tools")
    parser.add_argument("--source-id", default="ai-tools")
    parser.add_argument("--config", default=None)
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--show", action="store_true", default=True)
    parser.add_argument("--no-show", action="store_false", dest="show")
    return parser.parse_args(argv)


def submit_invocation(
    *,
    base_url: str,
    source_kind: str,
    source_label: str,
    source_id: str,
    prompt: str,
    intent: str,
    show: bool = True,
) -> dict[str, object]:
    payload = json.dumps(
        {
            "source_kind": source_kind,
            "source_label": source_label,
            "source_id": source_id,
            "prompt": prompt,
            "intent": intent,
        }
    ).encode("utf-8")
    response = request.urlopen(
        request.Request(
            f"{base_url}/api/invoke",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        ),
        timeout=10,
    )
    result = json.loads(response.read().decode("utf-8"))
    if show:
        request.urlopen(
            request.Request(f"{base_url}/api/panel/show", data=b"{}", method="POST"),
            timeout=3,
        ).read()
    return result


def submit_ai_tools_invocation(
    *,
    base_url: str,
    source_kind: str,
    source_label: str,
    source_id: str,
    text: str,
    app_context: str | None = None,
    nudge: str | None = None,
    intent: str = "new",
    show: bool = True,
) -> dict[str, object]:
    payload = json.dumps(
        {
            "source_kind": source_kind,
            "source_label": source_label,
            "source_id": source_id,
            "text": text,
            "app_context": app_context,
            "nudge": nudge,
            "intent": intent,
        }
    ).encode("utf-8")
    response = request.urlopen(
        request.Request(
            f"{base_url}/api/ai-tools",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        ),
        timeout=10,
    )
    result = json.loads(response.read().decode("utf-8"))
    if show:
        request.urlopen(
            request.Request(f"{base_url}/api/panel/show", data=b"{}", method="POST"),
            timeout=3,
        ).read()
    return result


def wait_for_run(*, base_url: str, run_id: str, timeout_seconds: float = 120) -> dict[str, object]:
    deadline = time.monotonic() + timeout_seconds
    terminal = {"completed", "failed", "not_found", "stale_source", "cancelled"}
    while time.monotonic() < deadline:
        response = request.urlopen(f"{base_url}/api/runs/{run_id}", timeout=5)
        payload = json.loads(response.read().decode("utf-8"))
        if str(payload.get("status")) in terminal:
            return payload
        time.sleep(0.5)
    raise TimeoutError(f"Timed out waiting for run {run_id}")


def main(argv: list[str] | None = None) -> int:
    args = parse_submit_args(argv)
    text = args.text if args.text is not None else sys.stdin.read()
    text = text.strip()
    if not text:
        print("No input text provided.", file=sys.stderr)
        return 2

    repo_root = Path(args.repo_root).resolve()
    config = load_web_panel_config(Path(args.config) if args.config else None, repo_root=repo_root)
    base_url = f"http://{config.server.host}:{config.server.port}"
    nudge = args.nudge or args.tab
    try:
        if args.prompt_kind == "ai_tools":
            result = submit_ai_tools_invocation(
                base_url=base_url,
                source_kind=args.source_kind,
                source_label=args.source_label,
                source_id=args.source_id,
                text=text,
                app_context=args.app_context,
                nudge=nudge,
                intent=args.intent,
                show=args.show,
            )
        else:
            result = submit_invocation(
                base_url=base_url,
                source_kind=args.source_kind,
                source_label=args.source_label,
                source_id=args.source_id,
                prompt=build_zsh_prompt(text),
                intent=args.intent,
                show=args.show,
            )
    except Exception as exc:  # noqa: BLE001
        print("Codex sidekick is not running or did not accept the request.", file=sys.stderr)
        print("Start it with: ./scripts/start_web_panel_daemon.sh --restart", file=sys.stderr)
        print(f"Detail: {exc}", file=sys.stderr)
        return 1

    if args.wait:
        run_id = str(result["run_id"])
        run = wait_for_run(base_url=base_url, run_id=run_id)
        output = str(run.get("primary_output") or run.get("response_text", ""))
        print(strip_command_response(output) if args.command_output else output)
        return 0

    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
