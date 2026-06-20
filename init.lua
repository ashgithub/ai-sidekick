local log = hs.logger.new('TextProcessor', 'debug')
require("hs.ipc")

-- Paths
local dir = os.getenv("HOME") .. "/work/code/python/ai_tools"
local web_panel_config_script = dir .. "/scripts/internal/config-json.sh"
local web_panel_start_script = dir .. "/bin/sidekick"
local ai_tools_sidekick_enabled = true
-- local scriptMode = "-m proof"
local default_window_width = 900
local default_window_height = 800
local show_screen_debug_alert = false
local status_alert_debounce_seconds = 0.25
local last_status_at = 0
local status_alert_durations = {
    cancelled = 1.8,
}
local active_shortcut_token = 0

local terminal_config = {  -- Shared config for terminal-like apps (iTerm2, Ghostty, Code)
    copy = function()
        -- Enter iTerm2 copy mode with Cmd+Shift+C
        hs.eventtap.keyStroke({"cmd", "shift"}, "c")
        hs.timer.usleep(100000)
        
        -- In copy mode, use Shift+V to select entire line
        hs.eventtap.keyStroke({"shift"}, "v")
        hs.timer.usleep(100000)
        
        -- Press y to yank (copy) selection to system clipboard and exit copy mode
        hs.eventtap.keyStrokes("y")
        hs.timer.usleep(300000)
    end,
    paste = function()
        -- Send Escape first to ensure you're in normal mode
        hs.eventtap.keyStroke({}, "escape")
        hs.timer.usleep(50000)
        
        -- Use vi command: go to start, delete to end, enter insert mode
        hs.eventtap.keyStrokes("0d$i")
        hs.timer.usleep(50000)
        
        -- Paste from clipboard
        hs.eventtap.keyStroke({"cmd"}, "v")
        hs.timer.usleep(200000)
        hs.timer.usleep(200000)
        hs.eventtap.keyStroke({"cmd"}, "return")
        
        -- Exit insert mode
        --hs.eventtap.keyStroke({}, "escape")
        --hs.timer.usleep(50000)
    end
}

local app_configs = {
    ["Slack"] = {
        copy = function()
            hs.eventtap.keyStroke({"cmd"}, "a")
            hs.timer.usleep(300000)
            hs.eventtap.keyStroke({"cmd"}, "c")
            hs.timer.usleep(300000)
        end,
        paste = function()
            hs.eventtap.keyStroke({"cmd"}, "a")
            hs.timer.usleep(200000)
            hs.eventtap.keyStroke({"cmd"}, "v")
            hs.timer.usleep(200000)
            hs.eventtap.keyStroke({"cmd"}, "return")
        end
    },
    ["iTerm2"] = terminal_config,
    ["Ghostty"] = terminal_config,
    ["Code"] = terminal_config,
    ["default"] = {
        copy = function()
            hs.eventtap.keyStroke({"cmd"}, "c")
            hs.timer.usleep(300000)
        end,
        paste = function()
            hs.eventtap.keyStroke({"cmd"}, "v")
            hs.timer.usleep(200000)
        end
    }
}

local status_messages = {
    processing = "Processing message from %s...",
    queued = "Queued in Codex sidekick for %s.",
    cancelled = "Cancelled in AI Sidekick for %s.",
    error = "Error while processing %s: %s",
}

local status_sounds = {
    slack = {
        processing = "Ping",
        cancelled = "Tink",
        error = "Sosumi",
    },
    iterm2 = {
        processing = "Bottle",
        cancelled = "Tink",
        error = "Sosumi",
    },
    ghostty = {
        processing = "Bottle",
        cancelled = "Tink",
        error = "Sosumi",
    },
    code = {
        processing = "Bottle",
        cancelled = "Tink",
        error = "Sosumi",
    },
    default = {
        processing = "Bottle",
        queued = "Ping",
        cancelled = "Tink",
        error = "Sosumi",
    }
}

local function load_web_panel_config()
    local output, ok = hs.execute(web_panel_config_script, true)
    if ok and output and output ~= "" then
        local parsed = hs.json.decode(output)
        if parsed then
            return parsed
        end
    end
    return {
        server = { port = 8765 },
        panel = { visibility = "always" },
    }
end

local function sidekick_urls()
    local config = load_web_panel_config()
    local port = tostring((config.server and config.server.port) or "8765")
    local base_url = "http://127.0.0.1:" .. port
    return {
        ready = base_url .. "/readyz",
        shortcut = base_url .. "/api/shortcut",
        shortcut_results = base_url .. "/api/shortcut/results/",
        panel_visibility = (config.panel and config.panel.visibility) or "always",
    }
end

local function normalize_app_bucket(app_name)
    local lowered = (app_name or ""):lower()
    if lowered:match("slack") then
        return "slack"
    end
    if lowered:match("iterm2") then
        return "iterm2"
    end
    if lowered:match("ghostty") then
        return "ghostty"
    end
    if lowered:match("^code$") or lowered:match("visual studio code") then
        return "code"
    end
    return "default"
end

local function play_status_sound(app_name, stage)
    local bucket = normalize_app_bucket(app_name)
    local bucket_sounds = status_sounds[bucket] or status_sounds.default
    local sound_name = bucket_sounds[stage] or status_sounds.default[stage]
    if not sound_name then
        return
    end
    local sound = hs.sound.getByName(sound_name)
    if sound then
        sound:play()
    end
end

local function show_status(stage, app_name, detail, is_error)
    local template = status_messages[stage] or "%s"
    local app_label = (app_name and app_name ~= "") and app_name or "current app"
    local message
    if stage == "error" then
        message = string.format(template, app_label, detail or "Unknown error")
    else
        message = string.format(template, app_label)
        if detail and detail ~= "" then
            message = message .. " " .. detail
        end
    end

    local now = hs.timer.secondsSinceEpoch()
    if now - last_status_at < status_alert_debounce_seconds then
        hs.timer.usleep(math.floor(status_alert_debounce_seconds * 1000000))
    end
    last_status_at = hs.timer.secondsSinceEpoch()

    local duration = status_alert_durations[stage] or (is_error and 4 or 1.8)
    hs.alert.show(message, duration)
    play_status_sound(app_name, stage)
    if is_error then
        log.e(message)
    else
        log.i(message)
    end
end

local function clamp(value, min_value, max_value)
    if value < min_value then
        return min_value
    end
    if value > max_value then
        return max_value
    end
    return value
end

local function log_screen_strategy(strategy, screen)
    local screen_name = (screen and screen:name()) or "unknown"
    log.i(string.format("Window target strategy=%s screen=%s", strategy, screen_name))
    if show_screen_debug_alert then
        hs.alert.show(string.format("Screen target: %s (%s)", strategy, screen_name), 1)
    end
end

local function resolve_target_screen(trigger_window, trigger_app)
    if trigger_window then
        local window_screen = trigger_window:screen()
        if window_screen then
            return window_screen, "focusedWindow"
        end
    end

    if trigger_app then
        local main_window = trigger_app:mainWindow()
        if main_window then
            local main_screen = main_window:screen()
            if main_screen then
                return main_screen, "mainWindow"
            end
        end
    end

    local mouse_screen = hs.mouse.getCurrentScreen()
    if mouse_screen then
        return mouse_screen, "mouse"
    end

    local primary = hs.screen.primaryScreen()
    return primary, "primary"
end

local function build_window_args(trigger_window, trigger_app)
    local screen, strategy = resolve_target_screen(trigger_window, trigger_app)
    log_screen_strategy(strategy, screen)
    if not screen then
        return string.format("--window-width %d --window-height %d", default_window_width, default_window_height)
    end

    local frame = screen:frame()
    local max_x = frame.x + math.max(0, frame.w - default_window_width)
    local max_y = frame.y + math.max(0, frame.h - default_window_height)
    local centered_x = frame.x + ((frame.w - default_window_width) / 2)
    local centered_y = frame.y + ((frame.h - default_window_height) / 2)
    local window_x = math.floor(clamp(centered_x, frame.x, max_x))
    local window_y = math.floor(clamp(centered_y, frame.y, max_y))

    return string.format(
        "--window-width %d --window-height %d --window-x %d --window-y %d",
        default_window_width, default_window_height, window_x, window_y
    )
end

local function next_shortcut_token()
    active_shortcut_token = active_shortcut_token + 1
    return active_shortcut_token
end

local function is_active_shortcut(shortcut_token)
    return shortcut_token == active_shortcut_token
end

local function is_connection_failure(status)
    local code = tonumber(status)
    return code == nil or code <= 0
end

local function restore_clipboard_later(originalClipboard, shortcut_token)
    hs.timer.doAfter(0.5, function()
        if shortcut_token and not is_active_shortcut(shortcut_token) then
            return
        end
        if originalClipboard then
            hs.pasteboard.setContents(originalClipboard)
        end
    end)
end

local function paste_ai_tools_output(trigger_app, config, originalClipboard, output, shortcut_token)
    hs.pasteboard.setContents(output)
    if trigger_app then
        trigger_app:activate()
    end
    hs.timer.usleep(200000)
    config.paste()
    restore_clipboard_later(originalClipboard, shortcut_token)
end

local function restore_clipboard_now(originalClipboard, shortcut_token)
    if shortcut_token and not is_active_shortcut(shortcut_token) then
        return
    end
    if originalClipboard then
        hs.pasteboard.setContents(originalClipboard)
    end
end

local function shortcut_result_url(urls, response)
    local poll_url = response["poll_url"]
    if poll_url and poll_url ~= "" then
        if poll_url:match("^http") then
            return poll_url
        end
        local base = urls.shortcut:gsub("/api/shortcut$", "")
        return base .. poll_url
    end
    local run_id = response["run_id"]
    if run_id and run_id ~= "" then
        return urls.shortcut_results .. run_id
    end
    return nil
end

local function poll_shortcut_result(url, trigger_app, appName, config, originalClipboard, shortcut_token, review_notice_shown)
    hs.http.asyncGet(url, {}, function(status, body, headers)
        if not is_active_shortcut(shortcut_token) then
            return
        end

        if status ~= 200 then
            log.i("Sidekick result polling stopped for " .. tostring(appName) .. ": status=" .. tostring(status) .. " body=" .. tostring(body))
            restore_clipboard_now(originalClipboard, shortcut_token)
            return
        end

        local result = hs.json.decode(body or "{}") or {}
        local state = result["state"] or ""
        if state == "ready" then
            local output = result["output"] or ""
            if output == "" then
                show_status("cancelled", appName)
                restore_clipboard_now(originalClipboard, shortcut_token)
                return
            end
            paste_ai_tools_output(trigger_app, config, originalClipboard, output, shortcut_token)
            return
        end

        if state == "pending" or state == "review_pending" then
            local notice_shown = review_notice_shown
            if state == "review_pending" and not notice_shown then
                local message = result["message"] or "Review in sidekick, then Apply to source."
                show_status("queued", appName, message)
                notice_shown = true
            end
            local retry_after_ms = tonumber(result["retry_after_ms"] or 200) or 200
            hs.timer.doAfter(retry_after_ms / 1000, function()
                if not is_active_shortcut(shortcut_token) then
                    return
                end
                poll_shortcut_result(url, trigger_app, appName, config, originalClipboard, shortcut_token, notice_shown)
            end)
            return
        end

        local message = result["message"] or "Sidekick shortcut failed."
        show_status("error", appName, message, true)
        restore_clipboard_now(originalClipboard, shortcut_token)
    end)
end

local function submit_shortcut(urls, trigger_app, appName, config, originalClipboard, text, shortcut_token)
    local payload = {
        ["app"] = appName,
        ["text"] = text,
        ["interaction"] = "replace-selection",
    }

    show_status("queued", appName)
    hs.http.asyncPost(urls.shortcut, hs.json.encode(payload), { ["Content-Type"] = "application/json" }, function(status, body, headers)
        if not is_active_shortcut(shortcut_token) then
            return
        end

        if status ~= 200 then
            if is_connection_failure(status) then
                log.i("Sidekick shortcut submit stopped for " .. tostring(appName) .. ": status=" .. tostring(status))
            else
                show_status("error", appName, "Codex sidekick did not accept the shortcut.", true)
            end
            log.e("Shortcut submit failed: status=" .. tostring(status) .. " body=" .. tostring(body))
            restore_clipboard_now(originalClipboard, shortcut_token)
            return
        end

        local response = hs.json.decode(body or "{}") or {}
        local client_action = response["client_action"] or ""
        if client_action == "show_sidekick" then
            show_status("queued", appName, "Ask in the sidekick.")
            restore_clipboard_now(originalClipboard, shortcut_token)
            return
        end

        local result_url = shortcut_result_url(urls, response)
        if not result_url then
            show_status("error", appName, "Sidekick did not return a shortcut result URL.", true)
            restore_clipboard_now(originalClipboard, shortcut_token)
            return
        end
        if client_action == "wait_for_sidekick" then
            result_url = result_url .. "?client_action=wait_for_sidekick"
        end
        poll_shortcut_result(result_url, trigger_app, appName, config, originalClipboard, shortcut_token)
    end)
end

local function run_processing(trigger_app, appName, config, shortcut_token)
    -- Save original clipboard
    local originalClipboard = hs.pasteboard.getContents()

    -- Copy selected text
    config.copy()

    local text = hs.pasteboard.getContents()

    if ai_tools_sidekick_enabled then
        local urls = sidekick_urls()
        hs.http.asyncGet(urls.ready, {}, function(status, body, headers)
            if not is_active_shortcut(shortcut_token) then
                return
            end

            if status ~= 200 then
                hs.alert.show("Codex sidekick is not running\nStart: " .. web_panel_start_script .. " --restart", 6)
                log.e("AI Sidekick bridge unavailable: status=" .. tostring(status) .. " body=" .. tostring(body))
                restore_clipboard_now(originalClipboard, shortcut_token)
                return
            end

            submit_shortcut(urls, trigger_app, appName, config, originalClipboard, text or "", shortcut_token)
        end)
        return
    end
    show_status("error", appName, "Codex sidekick shortcut is disabled.", true)
    restore_clipboard_now(originalClipboard, shortcut_token)
end

function processAppText()
    local trigger_window = hs.window.focusedWindow()
    local trigger_app = (trigger_window and trigger_window:application()) or hs.application.frontmostApplication()
    local appName = trigger_app and trigger_app:name() or ""
    local config = app_configs[appName] or app_configs["default"]
    local shortcut_token = next_shortcut_token()

    hs.timer.doAfter(0.2, function()
        run_processing(trigger_app, appName, config, shortcut_token)
    end)
end

local function build_codex_work_test_payload(appName, windowTitle, capturedText)
    local timestamp = os.date("%Y-%m-%d %H:%M:%S %Z")
    local text = capturedText or ""

    return table.concat({
        "Codex task test",
        "",
        "Source app: " .. (appName or ""),
        "Source window: " .. (windowTitle or ""),
        "Captured at: " .. timestamp,
        "",
        "Captured text:",
        text,
        "",
        "Instruction:",
        "This is a Hammerspoon hotkey capture test. Confirm whether the captured text has enough context to become a Codex work item.",
    }, "\n")
end

function testCodexSlackTaskCapture()
    local trigger_window = hs.window.focusedWindow()
    local trigger_app = (trigger_window and trigger_window:application()) or hs.application.frontmostApplication()
    local appName = trigger_app and trigger_app:name() or ""
    local windowTitle = trigger_window and trigger_window:title() or ""
    local config = app_configs[appName] or app_configs["default"]
    local originalClipboard = hs.pasteboard.getContents()

    show_status("processing", appName, "Capturing Codex task test payload...")
    config.copy()

    hs.timer.doAfter(0.3, function()
        local capturedText = hs.pasteboard.getContents()
        if not capturedText or capturedText == "" then
            if originalClipboard then
                hs.pasteboard.setContents(originalClipboard)
            end
            show_status("error", appName, "No text was copied for Codex task test.", true)
            return
        end

        local payload = build_codex_work_test_payload(appName, windowTitle, capturedText)
        hs.pasteboard.setContents(payload)
        hs.alert.show("Codex task test payload copied to clipboard", 2)
        log.i("Codex task test payload copied from " .. appName)
    end)
end

 function urlDecode(str)
    str = str:gsub('+', ' ')  -- Convert '+' to space
    str = str:gsub('%%(%x%x)', function(hex)
        return string.char(tonumber(hex, 16))
    end)
    return str
end

-- Hotkey binding
hs.hotkey.bind({ "ctrl", "alt", "cmd" }, "\\", processAppText)

hs.alert.show("Text processor loaded – Ctrl+Alt+Cmd+\\", 3)

local slack_codex_workflow = os.getenv("HOME") .. "/work/code/python/ai_tools/slack_codex_workflow/hammerspoon/slack_codex_workflow.lua"
if hs.fs.attributes(slack_codex_workflow) then
    dofile(slack_codex_workflow)
end

hs.urlevent.bind("alert", function(eventName, params)
    local message = urlDecode(params["msg"] )or "Hello from Shortcuts!"
    log.d("alert" .. message)
    hs.alert.show(message, 2)
    hs.sound.getByName("Blow"):play()
end)

hs.urlevent.bind("apply_ai_tools_output", function(eventName, params)
    local appName = urlDecode(params["app"]) or ""
    local config = app_configs[appName] or app_configs["default"]
    local target_app = nil
    if appName ~= "" then
        target_app = hs.application.find(appName)
        if not target_app then
            hs.application.launchOrFocus(appName)
            hs.timer.usleep(300000)
            target_app = hs.application.find(appName)
        end
    end
    if target_app then
        target_app:activate()
    end
    hs.timer.usleep(200000)
    config.paste()
end)
