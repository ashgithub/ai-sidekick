from pathlib import Path


STATIC = Path(__file__).resolve().parents[1] / "src" / "ai_tools" / "web_panel" / "static"


def read_static(name: str) -> str:
    return (STATIC / name).read_text(encoding="utf-8")


def test_web_panel_is_compact_sidekick_not_dashboard() -> None:
    html = read_static("index.html")

    assert "sidekick-shell" in html
    assert "sidekick-card" in html
    assert "rail-left" not in html
    assert "rail-right" not in html
    assert "run-list" not in html
    assert '<details class="debug-panel">' in html
    assert "<summary>Prompt</summary>" in html
    assert "<summary>Trace</summary>" in html
    assert "<summary>Manual prompt</summary>" in html


def test_web_panel_uses_redwood_tokens_and_wraps_text() -> None:
    css = read_static("styles.css")

    assert "--rds-page-background-neutral30: #F1EFED" in css
    assert "--rds-surface-neutral10: #FBF9F8" in css
    assert "--rds-text-primary: #161513" in css
    assert "--rds-danger: #B3311F" in css
    assert "font-family: var(--rds-font-family-primary)" in css
    assert "white-space: pre-wrap" in css
    assert "overflow-wrap: anywhere" in css
    assert "grid-template-columns: minmax(320px, 560px)" in css


def test_web_panel_js_reads_current_run_and_maps_attention_states() -> None:
    js = read_static("app.js")

    assert 'fetchJson("/api/current-run")' in js
    assert "status-not_found" in js
    assert "status-stale_source" in js
    assert "No @codex message found" in js
    assert "Stale @codex message" in js
    assert "renderPhaseList" in js
