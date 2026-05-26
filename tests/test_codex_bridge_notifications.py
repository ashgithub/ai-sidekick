from ai_tools.codex_bridge.notifications import MacOSNotifier


def test_run_started_notification_points_to_panel(monkeypatch) -> None:
    calls: list[list[str]] = []

    monkeypatch.setenv("AI_TOOLS_WEB_PANEL_PORT", "8876")
    monkeypatch.setattr("ai_tools.codex_bridge.notifications.subprocess.run", lambda command, check: calls.append(command))

    MacOSNotifier().run_started("Run started", "A Codex task is now running.")

    assert calls
    assert "http://127.0.0.1:8876/" in calls[0][-1]
