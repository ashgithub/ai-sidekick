"""Shared compact prompt contract for AI Tools runs."""

from __future__ import annotations


def infer_ai_tools_render_kind(nudge: str | None) -> str:
    normalized = (nudge or "").strip().lower()
    if normalized in {"commands", "command", "shell", "terminal"}:
        return "alternatives"
    if normalized in {"ask", "explain", "qa", "q&a"}:
        return "single_text"
    return "text_pair"


def ai_tools_schema_example(render_kind: str) -> str:
    if render_kind == "alternatives":
        return (
            '{"render_kind":"alternatives","primary_output":"<best command>",'
            '"structured_output":{"alternatives":[{"value":"<command>","explanation":"<short why>"}]}}'
        )
    if render_kind == "single_text":
        return '{"render_kind":"single_text","primary_output":"<answer>","structured_output":{"text":"<answer>"}}'
    return (
        '{"render_kind":"text_pair","primary_output":"<rewritten>",'
        '"structured_output":{"corrected":"<corrected>","rewritten":"<rewritten>"}}'
    )
