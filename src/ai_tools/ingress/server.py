"""Loopback-only HTTP ingress for local shortcuts and panel reads."""

from __future__ import annotations

import json
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from ai_tools.codex_bridge.config import ShortcutProfileConfig, default_shortcut_profiles
from ai_tools.codex_bridge.models import SourceMetadata
from ai_tools.codex_bridge.models import RunStatus

from .client import build_ai_tools_prompt
from .manual import manual_source_metadata
from .slack import SlackIngressPayload, build_slack_worker_prompt


def serialize_panel_run(run: Any) -> dict[str, Any]:
    payload = run.model_dump(mode="json")
    payload.pop("transcript", None)
    return payload


def serialize_panel_payload(service: Any) -> dict[str, Any]:
    run = service.current_run()
    panel_mode = service.panel_mode() if hasattr(service, "panel_mode") else "rewrite"
    return {"run": serialize_panel_run(run) if run else None, "panel_mode": panel_mode}


class LocalIngressServer:
    def __init__(
        self,
        *,
        service: Any,
        host: str = "127.0.0.1",
        port: int = 0,
        static_dir: Path | None = None,
        slack_prompt_file: Path | None = None,
        slack_latest_message_max_age_minutes: int = 30,
        panel_visibility: str = "manual",
        shortcut_profiles: list[ShortcutProfileConfig] | None = None,
        shortcut_pending_retry_after_ms: int = 200,
        shortcut_review_retry_after_ms: int = 500,
    ) -> None:
        self.service = service
        self.host = host
        self.port = port
        self.static_dir = static_dir
        self.slack_prompt_file = slack_prompt_file
        self.slack_latest_message_max_age_minutes = slack_latest_message_max_age_minutes
        self.panel_visibility = panel_visibility
        self.shortcut_profiles = shortcut_profiles or default_shortcut_profiles()
        self.shortcut_pending_retry_after_ms = shortcut_pending_retry_after_ms
        self.shortcut_review_retry_after_ms = shortcut_review_retry_after_ms
        self._server: ThreadingHTTPServer | None = None
        self._thread = None

    def start(self) -> None:
        if self._server is not None:
            return
        server = ThreadingHTTPServer((self.host, self.port), self._build_handler())
        self._server = server
        self.port = int(server.server_address[1])
        import threading

        self._thread = threading.Thread(target=server.serve_forever, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        if self._server is None:
            return
        self._server.shutdown()
        self._server.server_close()
        if self._thread is not None:
            self._thread.join(timeout=2)
        self._server = None
        self._thread = None

    def _build_handler(self):
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self) -> None:  # noqa: N802
                parsed = urlparse(self.path)
                if parsed.path == "/":
                    self._serve_static("index.html", content_type="text/html; charset=utf-8")
                    return
                if parsed.path.startswith("/static/"):
                    name = parsed.path.removeprefix("/static/")
                    content_type = "text/plain; charset=utf-8"
                    if name.endswith(".js"):
                        content_type = "application/javascript; charset=utf-8"
                    elif name.endswith(".css"):
                        content_type = "text/css; charset=utf-8"
                    elif name.endswith(".ttf"):
                        content_type = "font/ttf"
                    self._serve_static(name, content_type=content_type)
                    return
                if parsed.path == "/healthz":
                    self._write_json(HTTPStatus.OK, {"status": "ok"})
                    return
                if parsed.path == "/readyz":
                    readiness = outer.service.readiness()
                    status = HTTPStatus.OK if readiness.get("ready") is True else HTTPStatus.SERVICE_UNAVAILABLE
                    self._write_json(status, readiness)
                    return
                if parsed.path in {"/runs", "/api/runs"}:
                    runs = [serialize_panel_run(run) for run in outer.service.list_runs()]
                    self._write_json(HTTPStatus.OK, {"runs": runs})
                    return
                if parsed.path == "/api/current-run":
                    self._write_json(HTTPStatus.OK, serialize_panel_payload(outer.service))
                    return
                if parsed.path == "/api/events":
                    self._write_event_stream()
                    return
                if parsed.path.startswith("/api/shortcut/results/"):
                    run_id = parsed.path.removeprefix("/api/shortcut/results/")
                    query = parse_qs(parsed.query)
                    client_action = str((query.get("client_action") or [""])[0])
                    run = outer.service.get_run(run_id)
                    if run is None:
                        self._write_json(HTTPStatus.NOT_FOUND, {"state": "failed", "message": "run not found"})
                        return
                    self._write_json(HTTPStatus.OK, outer._shortcut_result_payload(run, client_action=client_action))
                    return
                if parsed.path.startswith("/api/runs/"):
                    run_id = parsed.path.removeprefix("/api/runs/")
                    run = outer.service.get_run(run_id)
                    if run is None:
                        self._write_json(HTTPStatus.NOT_FOUND, {"error": "run not found"})
                        return
                    self._write_json(HTTPStatus.OK, serialize_panel_run(run))
                    return
                self._write_json(HTTPStatus.NOT_FOUND, {"error": "not found"})

            def do_POST(self) -> None:  # noqa: N802
                body = self._read_json_body()
                parsed = urlparse(self.path)
                if parsed.path == "/ingest/slack":
                    try:
                        payload = SlackIngressPayload.model_validate(body)
                        run = outer.service.submit_run(
                            source=payload.to_source_metadata(),
                            prompt=build_slack_worker_prompt(
                                payload.prompt,
                                prompt_file=outer.slack_prompt_file,
                                latest_message_max_age_minutes=outer.slack_latest_message_max_age_minutes,
                            ),
                        )
                    except Exception as exc:  # noqa: BLE001
                        self._write_json(
                            HTTPStatus.INTERNAL_SERVER_ERROR,
                            {
                                "error": "submit_failed",
                                "message": str(exc),
                                "detail": type(exc).__name__,
                            },
                        )
                        return
                    self._write_json(
                        HTTPStatus.OK,
                        {"run_id": run.run_id, "status": "accepted", "panel_visibility": outer.panel_visibility},
                    )
                    return
                if parsed.path in {"/runs/manual", "/api/runs/manual"}:
                    prompt = str(body.get("prompt", "")).strip()
                    run = outer.service.submit_or_route(
                        source=manual_source_metadata(),
                        prompt=prompt,
                        intent=str(body.get("intent", "new")),
                    )
                    self._write_json(HTTPStatus.OK, {"run_id": run.run_id, "status": "accepted"})
                    return
                if parsed.path == "/api/invoke":
                    try:
                        source = SourceMetadata(
                            source_kind=str(body.get("source_kind", "manual")).strip() or "manual",
                            source_label=str(body.get("source_label", "Manual")).strip() or "Manual",
                            source_id=str(body.get("source_id", "manual")).strip() or "manual",
                        )
                        run = outer.service.submit_or_route(
                            source=source,
                            prompt=str(body.get("prompt", "")).strip(),
                            intent=str(body.get("intent", "new")).strip() or "new",
                        )
                    except Exception as exc:  # noqa: BLE001
                        self._write_json(
                            HTTPStatus.INTERNAL_SERVER_ERROR,
                            {
                                "error": "submit_failed",
                                "message": str(exc),
                                "detail": type(exc).__name__,
                            },
                        )
                        return
                    self._write_json(
                        HTTPStatus.OK,
                        {"run_id": run.run_id, "status": "accepted", "panel_visibility": outer.panel_visibility},
                    )
                    return
                if parsed.path == "/api/ai-tools":
                    try:
                        app_context = str(body.get("app_context", "")).strip() or None
                        nudge = str(body.get("nudge", "")).strip() or None
                        intent = str(body.get("intent", "new")).strip() or "new"
                        source = SourceMetadata(
                            source_kind=str(body.get("source_kind", "ai_tools")).strip() or "ai_tools",
                            source_label=str(body.get("source_label", "AI Tools")).strip() or "AI Tools",
                            source_id=str(body.get("source_id", "ai-tools")).strip() or "ai-tools",
                        )
                        prompt = build_ai_tools_prompt(
                            text=str(body.get("text", "")).strip(),
                            app_context=app_context,
                            nudge=nudge,
                        )
                        run = outer.service.submit_or_route(
                            source=source,
                            prompt=prompt,
                            intent=intent,
                            thread_key=outer._ai_tools_thread_key(
                                source=source,
                                app_context=app_context,
                                nudge=nudge,
                            ),
                        )
                    except Exception as exc:  # noqa: BLE001
                        self._write_json(
                            HTTPStatus.INTERNAL_SERVER_ERROR,
                            {
                                "error": "submit_failed",
                                "message": str(exc),
                                "detail": type(exc).__name__,
                            },
                        )
                        return
                    self._write_json(
                        HTTPStatus.OK,
                        {"run_id": run.run_id, "status": "accepted", "panel_visibility": outer.panel_visibility},
                    )
                    return
                if parsed.path == "/api/shortcut":
                    try:
                        app = str(body.get("app", "")).strip()
                        text = str(body.get("text", "")).strip()
                        interaction = str(body.get("interaction", "replace-selection")).strip() or "replace-selection"
                        if not text:
                            outer.service.show_panel(mode="ask")
                            self._write_json(
                                HTTPStatus.OK,
                                {
                                    "status": "accepted",
                                    "client_action": "show_sidekick",
                                    "panel_visibility": outer.panel_visibility,
                                },
                            )
                            return
                        profile = outer._resolve_shortcut_profile(app)
                        app_context = profile.app_context or app or None
                        source_label = app or app_context or "AI Tools"
                        source = SourceMetadata(
                            source_kind="ai_tools",
                            source_label=source_label,
                            source_id=outer._shortcut_source_id(app=app, interaction=interaction),
                        )
                        prompt = build_ai_tools_prompt(
                            text=text,
                            app_context=app_context,
                            nudge=profile.nudge,
                        )
                        run = outer.service.submit_or_route(
                            source=source,
                            prompt=prompt,
                            intent=profile.intent,
                            thread_key=outer._ai_tools_thread_key(
                                source=source,
                                app_context=app_context,
                                nudge=profile.nudge,
                                profile_name=profile.name,
                            ),
                        )
                        if profile.show_panel:
                            outer.service.show_panel(mode=profile.panel_mode)
                    except Exception as exc:  # noqa: BLE001
                        self._write_json(
                            HTTPStatus.INTERNAL_SERVER_ERROR,
                            {
                                "error": "submit_failed",
                                "message": str(exc),
                                "detail": type(exc).__name__,
                            },
                        )
                        return
                    self._write_json(
                        HTTPStatus.OK,
                        {
                            "run_id": run.run_id,
                            "status": "accepted",
                            "client_action": profile.client_action,
                            "poll_url": f"/api/shortcut/results/{run.run_id}",
                            "panel_visibility": outer.panel_visibility,
                        },
                    )
                    return
                if parsed.path == "/api/panel/show":
                    self._write_json(HTTPStatus.OK, outer.service.show_panel(mode=str(body.get("mode", "")).strip() or None))
                    return
                if parsed.path == "/api/panel/hide":
                    self._write_json(HTTPStatus.OK, outer.service.hide_panel())
                    return
                if parsed.path == "/api/panel/toggle":
                    self._write_json(HTTPStatus.OK, outer.service.toggle_panel(mode=str(body.get("mode", "")).strip() or None))
                    return
                if parsed.path.startswith("/runs/") and parsed.path.endswith("/approve"):
                    run_id = parsed.path.split("/")[2]
                    run = outer.service.approve_run(run_id)
                    self._write_json(HTTPStatus.OK, {"run_id": run.run_id, "status": run.status.value})
                    return
                if parsed.path.startswith("/api/runs/") and parsed.path.endswith("/approve"):
                    run_id = parsed.path.split("/")[3]
                    run = outer.service.approve_run(run_id)
                    self._write_json(HTTPStatus.OK, {"run_id": run.run_id, "status": run.status.value})
                    return
                if parsed.path.startswith("/runs/") and parsed.path.endswith("/abort"):
                    run_id = parsed.path.split("/")[2]
                    run = outer.service.abort_run(run_id)
                    self._write_json(HTTPStatus.OK, {"run_id": run.run_id, "status": run.status.value})
                    return
                if parsed.path.startswith("/api/runs/") and parsed.path.endswith("/abort"):
                    run_id = parsed.path.split("/")[3]
                    run = outer.service.abort_run(run_id)
                    self._write_json(HTTPStatus.OK, {"run_id": run.run_id, "status": run.status.value})
                    return
                if parsed.path.startswith("/api/runs/") and parsed.path.endswith("/select-output"):
                    run_id = parsed.path.split("/")[3]
                    selected_text = str(body.get("text", "")) if "text" in body else None
                    try:
                        run = outer.service.select_run_output(
                            run_id,
                            output_key=str(body.get("output_key", "")).strip(),
                            selected_text=selected_text,
                        )
                    except ValueError as exc:
                        self._write_json(
                            HTTPStatus.BAD_REQUEST,
                            {"error": "selection_rejected", "message": str(exc)},
                        )
                        return
                    self._write_json(
                        HTTPStatus.OK,
                        {
                            "run_id": run.run_id,
                            "primary_output": run.primary_output,
                            "selected_output_label": run.selected_output_label,
                        },
                    )
                    return
                if parsed.path.startswith("/api/runs/") and parsed.path.endswith("/review-output"):
                    run_id = parsed.path.split("/")[3]
                    try:
                        run = outer.service.review_run_output(
                            run_id,
                            output_key=str(body.get("output_key", "")).strip(),
                            edited_text=str(body.get("text", "")),
                        )
                    except ValueError as exc:
                        self._write_json(
                            HTTPStatus.BAD_REQUEST,
                            {"error": "review_rejected", "message": str(exc)},
                        )
                        return
                    self._write_json(
                        HTTPStatus.OK,
                        {
                            "run_id": run.run_id,
                            "status": run.status.value,
                        },
                    )
                    return
                if parsed.path.startswith("/runs/") and parsed.path.endswith("/deny"):
                    run_id = parsed.path.split("/")[2]
                    run = outer.service.deny_run(run_id)
                    self._write_json(HTTPStatus.OK, {"run_id": run.run_id, "status": run.status.value})
                    return
                if parsed.path.startswith("/api/runs/") and parsed.path.endswith("/deny"):
                    run_id = parsed.path.split("/")[3]
                    run = outer.service.deny_run(run_id)
                    self._write_json(HTTPStatus.OK, {"run_id": run.run_id, "status": run.status.value})
                    return
                self._write_json(HTTPStatus.NOT_FOUND, {"error": "not found"})

            def log_message(self, format: str, *args: object) -> None:
                return None

            def _read_json_body(self) -> dict[str, Any]:
                length = int(self.headers.get("Content-Length", "0"))
                raw = self.rfile.read(length) if length else b"{}"
                return json.loads(raw.decode("utf-8") or "{}")

            def _write_json(self, status: HTTPStatus, payload: dict[str, Any]) -> None:
                body = json.dumps(payload).encode("utf-8")
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def _write_event_stream(self) -> None:
                import time

                self.send_response(HTTPStatus.OK)
                self.send_header("Content-Type", "text/event-stream")
                self.send_header("Cache-Control", "no-cache")
                self.send_header("Connection", "keep-alive")
                self.end_headers()

                last_payload = ""
                last_keepalive = time.monotonic()
                while True:
                    payload = json.dumps(serialize_panel_payload(outer.service))
                    if payload != last_payload:
                        try:
                            self.wfile.write(f"data: {payload}\n\n".encode("utf-8"))
                            self.wfile.flush()
                        except (BrokenPipeError, ConnectionResetError):
                            return
                        last_payload = payload
                        last_keepalive = time.monotonic()
                    elif time.monotonic() - last_keepalive >= 15:
                        try:
                            self.wfile.write(b": keepalive\n\n")
                            self.wfile.flush()
                        except (BrokenPipeError, ConnectionResetError):
                            return
                        last_keepalive = time.monotonic()
                    time.sleep(0.5)

            def _serve_static(self, name: str, *, content_type: str) -> None:
                if outer.static_dir is None:
                    self._write_json(HTTPStatus.NOT_FOUND, {"error": "static assets unavailable"})
                    return
                path = outer.static_dir / name
                if not path.exists():
                    self._write_json(HTTPStatus.NOT_FOUND, {"error": "asset not found"})
                    return
                body = path.read_bytes()
                self.send_response(HTTPStatus.OK)
                self.send_header("Content-Type", content_type)
                self.send_header("Cache-Control", "no-store, max-age=0")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

        return Handler

    def _ai_tools_thread_key(
        self,
        *,
        source: SourceMetadata,
        app_context: str | None,
        nudge: str | None,
        profile_name: str | None = None,
    ) -> str:
        profile = (profile_name or nudge or app_context or source.source_label or "default").strip().lower()
        app = (app_context or source.source_label or "default").strip().lower()
        safe_profile = "".join(char if char.isalnum() or char in {"-", "_"} else "-" for char in profile)
        safe_app = "".join(char if char.isalnum() or char in {"-", "_"} else "-" for char in app)
        return f"ai_tools:{safe_profile}:{safe_app}"

    def _resolve_shortcut_profile(self, app: str) -> ShortcutProfileConfig:
        normalized_app = app.strip().lower()
        fallback = self.shortcut_profiles[-1] if self.shortcut_profiles else default_shortcut_profiles()[-1]
        for profile in self.shortcut_profiles:
            patterns = profile.app_patterns or []
            for pattern in patterns:
                normalized_pattern = pattern.strip().lower()
                if normalized_pattern == "*":
                    fallback = profile
                    continue
                if normalized_pattern and normalized_pattern in normalized_app:
                    return profile
        return fallback

    def _shortcut_source_id(self, *, app: str, interaction: str) -> str:
        import time

        safe_app = "".join(char if char.isalnum() or char in {"-", "_"} else "-" for char in (app or "app").lower())
        safe_interaction = "".join(
            char if char.isalnum() or char in {"-", "_"} else "-" for char in (interaction or "shortcut").lower()
        )
        return f"ai-tools-{safe_app}-{safe_interaction}-{int(time.time())}"

    def _shortcut_result_payload(self, run: Any, *, client_action: str = "") -> dict[str, Any]:
        if run.status in {RunStatus.QUEUED, RunStatus.STARTING, RunStatus.RUNNING, RunStatus.APPROVAL_NEEDED}:
            return {"state": "pending", "retry_after_ms": self.shortcut_pending_retry_after_ms}

        if run.status is RunStatus.COMPLETED:
            if client_action == "wait_for_sidekick" and not self._run_has_output_selected(run):
                return {
                    "state": "review_pending",
                    "retry_after_ms": self.shortcut_review_retry_after_ms,
                    "message": "Review in sidekick, then Apply to source.",
                }
            output = str(getattr(run, "primary_output", "") or getattr(run, "response_text", ""))
            if output:
                return {"state": "ready", "output": output}
            return {"state": "failed", "message": "No output returned."}

        summary = str(getattr(run, "last_summary", "") or f"Sidekick finished with status: {run.status.value}")
        return {"state": "failed", "message": summary}

    def _run_has_output_selected(self, run: Any) -> bool:
        trace = getattr(run, "trace", []) or []
        return any(getattr(entry, "kind", "") == "output_selected" for entry in trace)
