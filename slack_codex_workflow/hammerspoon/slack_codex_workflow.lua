local log = hs.logger.new("SlackCodexWorkflow", "debug")

local function script_dir()
    local source = debug.getinfo(1, "S").source
    if not source or source:sub(1, 1) ~= "@" then
        return nil
    end
    return source:sub(2):match("(.*/)")
end

local this_script_dir = script_dir() or (os.getenv("HOME") .. "/work/code/python/ai-sidekick/slack_codex_workflow/hammerspoon/")
local repo_root = this_script_dir:gsub("/slack_codex_workflow/hammerspoon/$", "")
local manual_daemon_script = repo_root .. "/bin/sidekick"
local config_script = repo_root .. "/scripts/internal/config-json.sh"
local config_load_failed = false

local function load_config()
    local output, ok = hs.execute(config_script, true)
    if ok and output and output ~= "" then
        local parsed = hs.json.decode(output)
        if parsed then
            return parsed
        end
    end
    config_load_failed = true
    return {
        server = { port = 8765 },
        panel = {
            visibility = "manual",
            open_command = "scripts/internal/panel-show.sh",
            toggle_command = "scripts/internal/panel-toggle.sh",
            open_hotkey = { mods = {}, key = "f5" },
        },
    }
end

local config = load_config()
local panel_port = tostring((config.server and config.server.port) or "8765")
local panel_visibility = (config.panel and config.panel.visibility) or "manual"
local panel_open_command = (config.panel and config.panel.open_command) or "scripts/internal/panel-show.sh"
local panel_toggle_command = (config.panel and config.panel.toggle_command) or "scripts/internal/panel-toggle.sh"
local open_panel_script = repo_root .. "/" .. panel_open_command
local toggle_panel_script = repo_root .. "/" .. panel_toggle_command
local panel_open_hotkey = (config.panel and config.panel.open_hotkey) or {}
local panel_open_hotkey_mods = panel_open_hotkey.mods or {}
local panel_open_hotkey_key = panel_open_hotkey.key or "f5"
local ready_url = "http://127.0.0.1:" .. panel_port .. "/readyz"
local ingest_url = "http://127.0.0.1:" .. panel_port .. "/ingest/slack"
local hotkey_mods = { "ctrl", "alt", "cmd" }
local hotkey_key = "right"

local function show_lines(lines, duration)
    hs.alert.show(table.concat(lines, "\n"), duration)
end

local function open_panel()
    local task = hs.task.new(open_panel_script, function(exit_code, stdout, stderr)
        if exit_code ~= 0 then
            show_lines({
                "Could not open Codex sidekick",
                "Check bridge or run: " .. open_panel_script,
            }, 5)
            log.e("Open panel failed: " .. tostring(stderr or stdout or "unknown error"))
        end
    end)
    if not task:start() then
        show_lines({
            "Could not open Codex sidekick",
            "Check bridge or run: " .. open_panel_script,
        }, 5)
        log.e("Open panel task failed to start")
    end
end

local function toggle_panel()
    local task = hs.task.new(toggle_panel_script, function(exit_code, stdout, stderr)
        if exit_code ~= 0 then
            show_lines({
                "Could not toggle Codex sidekick",
                "Check bridge or run: " .. manual_daemon_script .. " --restart",
            }, 5)
            log.e("Toggle panel failed: " .. tostring(stderr or stdout or "unknown error"))
        end
    end)
    if not task:start() then
        show_lines({
            "Could not toggle Codex sidekick",
            "Check bridge or run: " .. manual_daemon_script .. " --restart",
        }, 5)
        log.e("Toggle panel task failed to start")
    end
end

local function now_iso()
    return os.date("%Y-%m-%dT%H:%M:%S%z")
end

local function frontmost_context()
    local window = hs.window.focusedWindow()
    local app = (window and window:application()) or hs.application.frontmostApplication()

    return {
        app_name = app and app:name() or "",
        captured_at = now_iso(),
    }
end

local function build_payload(context)
    local lines = {
        "Slack Codex hotkey task",
        "",
        "Request time: " .. context.captured_at,
        "Task resolver: latest @codex message from Ashish",
    }

    return table.concat(lines, "\n")
end

local function show_bridge_start_error(detail)
    local message = "Codex bridge is not running"
    local start_hint = "Start: " .. manual_daemon_script .. " --restart"
    show_lines({ message, start_hint }, 6)
    log.e(message .. " | " .. start_hint .. " | " .. tostring(detail or "local bridge unavailable"))
end

local function submit_local_bridge_request(payload)
    local source_id = "slack-" .. tostring(os.time())
    local request_body = hs.json.encode({
        source_id = source_id,
        source_label = "Slack",
        prompt = payload,
    })

    hs.http.asyncPost(ingest_url, request_body, { ["Content-Type"] = "application/json" }, function(status, body, headers)
        if status == 200 then
            hs.alert.show("Queued Codex task", 1.5)
            log.i("Queued Slack task in local bridge")
            local response = hs.json.decode(body or "{}") or {}
            if (response.panel_visibility or panel_visibility) == "always" then
                open_panel()
            end
            return
        end

        show_bridge_start_error("POST " .. ingest_url .. " failed with status " .. tostring(status) .. " body=" .. tostring(body))
    end)
end

local function queue_local_bridge_request(payload)
    hs.http.asyncGet(ready_url, {}, function(status, body, headers)
        if status == 200 then
            submit_local_bridge_request(payload)
            return
        end

        show_bridge_start_error("GET " .. ready_url .. " failed with status " .. tostring(status) .. " body=" .. tostring(body))
    end)
end

local function run_slack_codex_workflow()
    local context = frontmost_context()
    local app_name_lower = string.lower(context.app_name or "")

    if not string.find(app_name_lower, "slack", 1, true) then
        hs.alert.show("Focus Slack before using Codex workflow", 3)
        return
    end

    hs.alert.show("Checking Codex bridge...", 1.2)

    local payload = build_payload(context)
    queue_local_bridge_request(payload)
end

hs.hotkey.bind(hotkey_mods, hotkey_key, run_slack_codex_workflow)
hs.hotkey.bind(panel_open_hotkey_mods, panel_open_hotkey_key, toggle_panel)
if config_load_failed then
    show_lines({
        "Codex shortcuts loaded with fallback config",
        "Slack: ctrl+alt+cmd+right | Toggle panel: " .. string.upper(panel_open_hotkey_key),
        "Bridge starts manually",
    }, 4)
else
    show_lines({
        "Codex shortcuts loaded",
        "Slack: ctrl+alt+cmd+right | Toggle panel: " .. string.upper(panel_open_hotkey_key),
        "Bridge starts manually",
    }, 4)
end
log.i("Loaded Codex shortcuts: slack=ctrl+alt+cmd+right panel_toggle=" .. panel_open_hotkey_key)
