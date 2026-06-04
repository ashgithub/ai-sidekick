from pathlib import Path


STATIC = Path(__file__).resolve().parents[1] / "src" / "ai_tools" / "web_panel" / "static"


def read_static(name: str) -> str:
    return (STATIC / name).read_text(encoding="utf-8")


def test_web_panel_is_compact_sidekick_not_dashboard() -> None:
    html = read_static("index.html")

    assert "sidekick-shell" in html
    assert "sidekick-panel" in html
    assert "mode-tabs" in html
    assert "task-canvas" in html
    assert "details-drawer" in html
    assert "rail-left" not in html
    assert "rail-right" not in html
    assert "run-list" not in html
    assert "response-card" not in html
    assert "composer-card" not in html
    assert "review-output-card" not in html
    assert '<details class="debug-drawer">' in html
    assert "<summary>Prompt sent</summary>" in html
    assert "<summary>Raw output</summary>" in html
    assert "<summary>Event trace</summary>" in html
    assert "<summary>Details</summary>" in html
    assert "Ask anything" in html
    assert "Choose a version" in html
    assert "Manual prompt" not in html


def test_web_panel_uses_redwood_tokens_and_wraps_text() -> None:
    css = read_static("styles.css")
    html = read_static("index.html")

    assert "/static/assets/fonts/fonts.css" in html
    assert "--rds-page-background-neutral30: #F1EFED" in css
    assert "--rds-surface-neutral10: #FBF9F8" in css
    assert "--rds-text-primary: #161513" in css
    assert "--rds-danger: #B3311F" in css
    assert '--rds-font-family-primary: "Oracle Sans", "Segoe UI", Arial, sans-serif' in css
    assert "white-space: pre-wrap" in css
    assert "overflow-wrap: anywhere" in css
    assert "max-width: 560px" in css


def test_web_panel_uses_compact_sidekick_spacing() -> None:
    css = read_static("styles.css")

    assert "width: min(calc(100vw - 16px), 560px)" in css
    assert "max-width: 560px" in css
    assert ".sidekick-shell {\n  display: grid;\n  justify-content: end;\n  min-height: 100vh;\n  padding: var(--rds-space-sm);" in css
    assert ".sidekick-panel {\n  display: grid;\n  align-self: start;\n  gap: var(--rds-space-sm);" in css
    assert "max-height: 52vh" in css


def test_web_panel_js_reads_current_run_and_maps_attention_states() -> None:
    js = read_static("app.js")
    html = read_static("index.html")

    assert 'fetchJson("/api/current-run")' in js
    assert "new EventSource" in js
    assert 'fetchJson("/api/invoke"' in js
    assert 'fetchJson("/api/panel/show"' in js
    assert "renderReadableText" in js
    assert "raw_response_text" in js
    assert "panel_mode" in js
    assert "setMode" in js
    assert "status-not_found" in js
    assert "status-stale_source" in js
    assert "status-cancelled" in js
    assert "abortRun" in js
    assert "/abort" in js
    assert "Abort" in html
    assert "Hide" in html
    assert "closePanel" in js
    assert "/api/panel/hide" in js
    assert "No @codex message found" in js
    assert "Stale @codex message" in js
    assert "renderPhaseList" in js


def test_web_panel_reconnects_event_stream_instead_of_going_stale() -> None:
    js = read_static("app.js")

    assert "eventStreamReconnectTimer" in js
    assert "scheduleEventStreamReconnect" in js
    assert "events.onopen" in js
    assert "setTimeout(startEventStream, 1000)" in js


def test_web_panel_renders_structured_ai_tools_outputs() -> None:
    js = read_static("app.js")
    html = read_static("index.html")

    assert "version-tabs" in html
    assert "selected-output-textarea" in html
    assert "selectOutput" in js
    assert "Use selected version" in html
    assert "selectedOutputKey" in js
    assert "renderVersionTabs" in js
    assert "Corrected" in html
    assert "Rewritten" in html
    assert "/select-output" in js
    assert "text_pair" in js
    assert "primary_output" in js


def test_web_panel_supports_ask_mode_without_selected_text() -> None:
    js = read_static("app.js")
    html = read_static("index.html")

    assert "mode-ask-btn" in html
    assert "ask-input" in html
    assert "ask-submit-btn" in html
    assert "Ask a question without selecting text first." in html
    assert 'source_label: "Ask"' in js
    assert 'source_kind: "manual"' in js
