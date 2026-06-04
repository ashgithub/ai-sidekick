import json
from io import StringIO
import subprocess

from ai_tools.codex_bridge.protocol import CodexAppServerClient, JsonRpcProtocol, resolve_codex_command


def test_send_request_returns_incrementing_id_and_json_payload() -> None:
    protocol = JsonRpcProtocol(client_name="ai-tools-web-panel", client_version="0.1.0")

    first = protocol.build_request("thread/start", {"cwd": "/tmp/demo"})
    second = protocol.build_request("turn/start", {"threadId": "t1", "input": []})

    first_payload = json.loads(first)
    second_payload = json.loads(second)

    assert first_payload["id"] == 1
    assert first_payload["method"] == "thread/start"
    assert first_payload["params"]["cwd"] == "/tmp/demo"
    assert second_payload["id"] == 2


def test_initialize_and_initialized_messages_match_expected_shape() -> None:
    protocol = JsonRpcProtocol(client_name="ai-tools-web-panel", client_version="0.1.0")

    initialize = json.loads(protocol.build_initialize_request())
    initialized = json.loads(protocol.build_initialized_notification())

    assert initialize["method"] == "initialize"
    assert initialize["params"]["clientInfo"] == {
        "name": "ai-tools-web-panel",
        "version": "0.1.0",
    }
    assert initialized == {"method": "initialized"}


def test_turn_interrupt_request_shape_matches_codex_app_server_schema() -> None:
    protocol = JsonRpcProtocol(client_name="ai-tools-web-panel", client_version="0.1.0")

    payload = json.loads(protocol.build_request("turn/interrupt", {"threadId": "thread-1", "turnId": "turn-1"}))

    assert payload == {
        "id": 1,
        "method": "turn/interrupt",
        "params": {"threadId": "thread-1", "turnId": "turn-1"},
    }


def test_handle_incoming_routes_response_notification_and_server_request() -> None:
    protocol = JsonRpcProtocol(client_name="ai-tools-web-panel", client_version="0.1.0")
    seen: list[tuple[str, dict]] = []

    protocol.on_notification = lambda payload: seen.append(("notification", payload))
    protocol.on_server_request = lambda payload: seen.append(("server_request", payload))

    protocol.build_request("thread/start", {})
    protocol.handle_incoming_line(json.dumps({"id": 1, "result": {"thread": {"id": "abc"}}}))
    protocol.handle_incoming_line(json.dumps({"method": "turn/started", "params": {"turnId": "t1"}}))
    protocol.handle_incoming_line(
        json.dumps(
            {
                "id": "approval-1",
                "method": "item/commandExecution/requestApproval",
                "params": {"command": ["ls"], "cwd": "/tmp/demo"},
            }
        )
    )

    assert protocol.take_response(1) == {"thread": {"id": "abc"}}
    assert seen == [
        ("notification", {"method": "turn/started", "params": {"turnId": "t1"}}),
        (
            "server_request",
            {
                "id": "approval-1",
                "method": "item/commandExecution/requestApproval",
                "params": {"command": ["ls"], "cwd": "/tmp/demo"},
            },
        ),
    ]


def test_resolve_codex_command_uses_env_then_path_then_homebrew(monkeypatch) -> None:
    monkeypatch.setenv("CODEX_BIN", "/custom/codex")
    monkeypatch.setattr("ai_tools.codex_bridge.protocol.shutil.which", lambda name: None)
    assert resolve_codex_command() == ["/custom/codex", "app-server", "--listen", "stdio://"]

    monkeypatch.delenv("CODEX_BIN", raising=False)
    monkeypatch.setattr("ai_tools.codex_bridge.protocol.shutil.which", lambda name: "/usr/local/bin/codex")
    assert resolve_codex_command() == ["/usr/local/bin/codex", "app-server", "--listen", "stdio://"]

    monkeypatch.setattr("ai_tools.codex_bridge.protocol.shutil.which", lambda name: None)
    assert resolve_codex_command() == ["/opt/homebrew/bin/codex", "app-server", "--listen", "stdio://"]


def test_client_drains_and_keeps_recent_stderr_lines(tmp_path) -> None:
    client = CodexAppServerClient(cwd=tmp_path, command=["codex"])
    client.process = subprocess.Popen.__new__(subprocess.Popen)
    client.process.stderr = StringIO("first warning\nsecond warning\n")

    client._read_stderr_loop()

    assert client.recent_stderr() == ["first warning", "second warning"]
