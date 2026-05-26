"""Loopback-only HTTP ingress for local shortcuts and panel reads."""

from __future__ import annotations

import json
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse
from typing import Any

from .manual import manual_source_metadata
from .slack import SlackIngressPayload, build_slack_worker_prompt


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
    ) -> None:
        self.service = service
        self.host = host
        self.port = port
        self.static_dir = static_dir
        self.slack_prompt_file = slack_prompt_file
        self.slack_latest_message_max_age_minutes = slack_latest_message_max_age_minutes
        self.panel_visibility = panel_visibility
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
                    runs = [run.model_dump(mode="json") for run in outer.service.list_runs()]
                    self._write_json(HTTPStatus.OK, {"runs": runs})
                    return
                if parsed.path == "/api/current-run":
                    run = outer.service.current_run()
                    self._write_json(HTTPStatus.OK, {"run": run.model_dump(mode="json") if run else None})
                    return
                if parsed.path.startswith("/api/runs/"):
                    run_id = parsed.path.removeprefix("/api/runs/")
                    run = outer.service.get_run(run_id)
                    if run is None:
                        self._write_json(HTTPStatus.NOT_FOUND, {"error": "run not found"})
                        return
                    self._write_json(HTTPStatus.OK, run.model_dump(mode="json"))
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
                    run = outer.service.submit_run(
                        source=manual_source_metadata(),
                        prompt=prompt,
                    )
                    self._write_json(HTTPStatus.OK, {"run_id": run.run_id, "status": "accepted"})
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
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

        return Handler
