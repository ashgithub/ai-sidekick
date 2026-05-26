"""Minimal JSON-RPC protocol helpers for Codex app-server."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import threading
from pathlib import Path
from typing import Any, Callable


NotificationHandler = Callable[[dict[str, Any]], None]
ServerRequestHandler = Callable[[dict[str, Any]], None]


def resolve_codex_command() -> list[str]:
    codex_bin = os.environ.get("CODEX_BIN")
    if not codex_bin:
        codex_bin = shutil.which("codex")
    if not codex_bin:
        codex_bin = "/opt/homebrew/bin/codex"
    return [codex_bin, "app-server", "--listen", "stdio://"]


class JsonRpcProtocol:
    def __init__(self, *, client_name: str, client_version: str) -> None:
        self.client_name = client_name
        self.client_version = client_version
        self.on_notification: NotificationHandler | None = None
        self.on_server_request: ServerRequestHandler | None = None
        self._next_id = 1
        self._responses: dict[int | str, dict[str, Any]] = {}
        self._condition = threading.Condition()

    def build_initialize_request(self) -> str:
        return self.build_request(
            "initialize",
            {
                "clientInfo": {"name": self.client_name, "version": self.client_version},
                "capabilities": {"experimentalApi": False},
            },
        )

    def build_initialized_notification(self) -> str:
        return json.dumps({"method": "initialized"})

    def build_request(self, method: str, params: dict[str, Any]) -> str:
        request_id = self._next_id
        self._next_id += 1
        return json.dumps({"id": request_id, "method": method, "params": params})

    def build_response(self, request_id: int | str, payload: dict[str, Any]) -> str:
        return json.dumps({"id": request_id, "result": payload})

    def peek_last_request_id(self) -> int:
        return self._next_id - 1

    def handle_incoming_line(self, line: str) -> None:
        payload = json.loads(line)
        if "id" in payload and "result" in payload and "method" not in payload:
            with self._condition:
                self._responses[payload["id"]] = payload["result"]
                self._condition.notify_all()
            return
        if "method" in payload and "id" in payload:
            if self.on_server_request is not None:
                self.on_server_request(payload)
            return
        if "method" in payload:
            if self.on_notification is not None:
                self.on_notification(payload)

    def take_response(self, request_id: int | str) -> dict[str, Any] | None:
        with self._condition:
            return self._responses.pop(request_id, None)

    def wait_for_response(self, request_id: int | str, *, timeout: float) -> dict[str, Any]:
        with self._condition:
            if request_id not in self._responses:
                self._condition.wait_for(lambda: request_id in self._responses, timeout=timeout)
            if request_id not in self._responses:
                raise TimeoutError(f"Timed out waiting for JSON-RPC response {request_id}")
            return self._responses.pop(request_id)


class CodexAppServerClient:
    """Subprocess-backed Codex app-server client using stdio JSONL."""

    def __init__(
        self,
        *,
        cwd: Path,
        protocol: JsonRpcProtocol | None = None,
        command: list[str] | None = None,
    ) -> None:
        self.cwd = cwd
        self.protocol = protocol or JsonRpcProtocol(
            client_name="ai-tools-web-panel",
            client_version="0.1.0",
        )
        self.command = command or resolve_codex_command()
        self.protocol.on_notification = self._ignore_notification
        self.process: subprocess.Popen[str] | None = None
        self._reader_thread: threading.Thread | None = None
        self._write_lock = threading.Lock()

    def _ignore_notification(self, payload: dict[str, Any]) -> None:
        return None

    def set_notification_handler(self, handler: NotificationHandler) -> None:
        self.protocol.on_notification = handler

    def set_server_request_handler(self, handler: ServerRequestHandler) -> None:
        self.protocol.on_server_request = handler

    def ensure_started(self) -> None:
        if self.process and self.process.poll() is None:
            return
        self.process = subprocess.Popen(
            self.command,
            cwd=str(self.cwd),
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
        )
        self._reader_thread = threading.Thread(target=self._read_loop, daemon=True)
        self._reader_thread.start()
        self._write_line(self.protocol.build_initialize_request())
        self.protocol.wait_for_response(self.protocol.peek_last_request_id(), timeout=10)
        self._write_line(self.protocol.build_initialized_notification())

    def validate_command(self) -> tuple[bool, str]:
        executable = self.command[0] if self.command else ""
        resolved = shutil.which(executable) if executable else None
        path = Path(resolved or executable) if executable else None
        if path is not None and path.is_file() and os.access(path, os.X_OK):
            return True, f"codex command is executable: {path}"
        return False, f"codex command is not executable: {executable or '<empty>'}"

    def thread_start(self, params: dict[str, Any]) -> dict[str, Any]:
        return self._request("thread/start", params)

    def turn_start(self, params: dict[str, Any]) -> dict[str, Any]:
        return self._request("turn/start", params)

    def turn_steer(self, params: dict[str, Any]) -> dict[str, Any]:
        return self._request("turn/steer", params)

    def reply_to_server_request(self, request_id: str, payload: object) -> None:
        self._write_line(self.protocol.build_response(request_id, payload if isinstance(payload, dict) else {}))

    def _request(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        self.ensure_started()
        request = self.protocol.build_request(method, params)
        request_id = self.protocol.peek_last_request_id()
        self._write_line(request)
        return self.protocol.wait_for_response(request_id, timeout=60)

    def _write_line(self, payload: str) -> None:
        if self.process is None or self.process.stdin is None:
            raise RuntimeError("Codex app-server process is not running")
        with self._write_lock:
            self.process.stdin.write(payload + "\n")
            self.process.stdin.flush()

    def _read_loop(self) -> None:
        if self.process is None or self.process.stdout is None:
            return
        for line in self.process.stdout:
            stripped = line.strip()
            if stripped:
                self.protocol.handle_incoming_line(stripped)
