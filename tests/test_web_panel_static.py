from pathlib import Path


STATIC = Path(__file__).resolve().parents[1] / "src" / "ai_tools" / "web_panel" / "static"


def read_static(name: str) -> str:
    return (STATIC / name).read_text(encoding="utf-8")


def test_web_panel_is_compact_sidekick_not_dashboard() -> None:
    html = read_static("index.html")

    assert "sidekick-shell" in html
    assert "sidekick-panel" in html
    assert "brand-lockup" in html
    assert "brand-icon" in html
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
    assert "<h2>Ask</h2>" in html
    assert "Choose a version" in html
    assert "Manual prompt" not in html


def test_web_panel_uses_redwood_tokens_and_wraps_text() -> None:
    css = read_static("styles.css")
    html = read_static("index.html")

    assert "/static/assets/fonts/fonts.css" in html
    assert "/static/assets/codex-sidekick-icon.png" in html
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
    assert "min-height: 100vh" in css
    assert ".sidekick-shell {\n  display: grid;\n  justify-content: end;\n  min-height: 100vh;\n  padding: var(--rds-space-sm);" in css
    assert ".sidekick-panel {\n  display: grid;\n  align-self: start;\n  gap: var(--rds-space-sm);" in css
    assert "border-radius: var(--rds-radius-xl)" in css
    assert "box-shadow: var(--rds-shadow-sm)" in css
    assert "max-height: 58vh" in css


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
    assert "refinementPrompt" in js
    assert "refine-thread-mode" in html
    assert 'intent: refineThreadModeEl.value === "new" ? "new" : "auto"' in js


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
    assert "rewrite-feedback" in html
    assert "selectOutput" in js
    assert "Apply to source" in html
    assert "Review edits" in js
    assert "Copy text" in html
    assert "Copied to clipboard." in js
    assert "Applied to source." in js
    assert "Reviewing changes." in js
    assert "Ask Codex to revise" in html
    assert "Revise with instruction" in html
    assert "Tell Codex what to change." in html
    assert "Fresh thread" in html
    assert "Revision requested." in js
    assert "Current draft:" in js
    assert "selectedOutputKey" in js
    assert "renderVersionTabs" in js
    assert "Corrected" in html
    assert "Rewritten" in html
    assert "/select-output" in js
    assert "/review-output" in js
    assert "text_pair" in js
    assert "primary_output" in js


def test_web_panel_supports_ask_mode_without_selected_text() -> None:
    js = read_static("app.js")
    html = read_static("index.html")

    assert "mode-ask-btn" in html
    assert "ask-input" in html
    assert "ask-submit-btn" in html
    assert "ask-question-view" not in html
    assert "ask-question-text" not in html
    assert "Answer" in html
    assert "Start new" in html
    assert "Ask a question without selecting text first." in html
    assert 'source_label: "Ask"' in js
    assert 'source_kind: "manual"' in js
    assert "lastAskQuestion" in js
    assert "askInputEl.value = lastAskQuestion" in js
    assert "function isAskRun(run)" in js
    assert 'run.panel_mode === "ask"' in js
    assert "function askQuestionForRun(run)" in js
    assert "extractAiToolsInput(run.prompt || \"\")" in js
    assert "currentRun.display_input_text || currentRun.prompt" not in js
    assert "function askAnswerForRun(run)" in js
    assert 'run.status !== "completed"' in js
    assert "structured.text" in js
    assert 'run.panel_mode !== "ask"' in js
    assert "payload.run && payload.run.panel_mode ? payload.run.panel_mode : payload.panel_mode" in js
    assert 'lastAskQuestion = prompt;\n    askInputEl.value = "";' not in js
    assert 'currentMode === "ask" || currentRun.source.source_label === "Ask"' not in js


def test_web_panel_carries_blank_mode_editor_text_on_user_toggle() -> None:
    js = read_static("app.js")

    assert "function transferBlankModeText(nextMode)" in js
    assert 'if (nextMode === "ask" && askInputEl.value.trim() === "")' in js
    assert "askInputEl.value = selectedOutputTextareaEl.value" in js
    assert 'if (nextMode === "rewrite" && selectedOutputTextareaEl.value.trim() === "")' in js
    assert "selectedOutputTextareaEl.value = askInputEl.value" in js
    assert "selectedOutputDirty = selectedOutputTextareaEl.value.trim() !== \"\"" in js
    assert 'setMode("rewrite", { persist: true, transferBlank: true })' in js
    assert 'setMode("ask", { persist: true, transferBlank: true })' in js
