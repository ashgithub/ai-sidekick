local log = hs.logger.new('TextProcessor', 'debug')
require("hs.ipc")

-- Paths
local dir = os.getenv("HOME") .. "/work/code/python/ai_tools"
local scriptPath = dir .. "/clients/multi_tool_client.py"
local sidekick_client_script = dir .. "/scripts/run_app.sh"
local web_panel_config_script = dir .. "/scripts/codex_web_panel_config_json.sh"
local web_panel_start_script = dir .. "/scripts/start_web_panel_daemon.sh"
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
    cancelled = "Cancelled in AI Tools for %s.",
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
        invoke = base_url .. "/api/invoke",
        ai_tools = base_url .. "/api/ai-tools",
        runs = base_url .. "/api/runs",
        show = base_url .. "/api/panel/show",
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

local function restore_clipboard_later(originalClipboard)
    hs.timer.doAfter(0.5, function()
        hs.pasteboard.setContents(originalClipboard)
    end)
end

local function paste_ai_tools_output(trigger_app, config, originalClipboard, output)
    hs.pasteboard.setContents(output)
    if trigger_app then
        trigger_app:activate()
    end
    hs.timer.usleep(200000)
    config.paste()
    restore_clipboard_later(originalClipboard)
end

local function run_ai_tools_cli_fallback(trigger_app, appName, config, originalClipboard, text, nudge_arg)
    local source_label = (appName and appName ~= "") and appName or "AI Tools"
    local sidekick_command = string.format(
        "cd %s && %s --source-kind ai_tools --app %q --source-label %q --source-id %q%s --wait --no-show <<'EOF'\n%s\nEOF",
        dir,
        sidekick_client_script,
        appName,
        source_label,
        "ai-tools-" .. tostring(os.time()),
        nudge_arg,
        text
    )

    local task = hs.task.new("/bin/zsh",
        function(exitCode, stdOut, stdErr)
            log.d("--- AI Tools sidekick output ---")
            log.d("Exit Code: " .. tostring(exitCode))
            log.d("stdout:\n" .. (stdOut or "[No stdout]"))
            log.d("stderr:\n" .. (stdErr or "[No stderr]"))

            if exitCode == nil then
                show_status("cancelled", appName)
                if originalClipboard then
                    hs.pasteboard.setContents(originalClipboard)
                end
                return
            end

            if exitCode ~= 0 then
                local stderr_text = (stdErr or ""):gsub("%s+$", "")
                local first_line = stderr_text:match("([^\n]+)") or "Unknown error"
                show_status("error", appName, "Sidekick failed: " .. first_line, true)
                if originalClipboard then
                    hs.pasteboard.setContents(originalClipboard)
                end
                return
            end

            if not stdOut or stdOut == "" then
                show_status("cancelled", appName)
                if originalClipboard then
                    hs.pasteboard.setContents(originalClipboard)
                end
                return
            end

            paste_ai_tools_output(trigger_app, config, originalClipboard, stdOut)
        end,
        { "-c", sidekick_command }
    )
    task:start()
end

local function poll_ai_tools_result(urls, run_id, trigger_app, appName, config, originalClipboard, attempt)
    local poll_attempt = attempt or 1
    if poll_attempt > 600 then
        show_status("error", appName, "Timed out waiting for sidekick result.", true)
        if originalClipboard then
            hs.pasteboard.setContents(originalClipboard)
        end
        return
    end

    hs.http.asyncGet(urls.runs .. "/" .. run_id, {}, function(status, body, headers)
        if status ~= 200 then
            hs.timer.doAfter(0.2, function()
                poll_ai_tools_result(urls, run_id, trigger_app, appName, config, originalClipboard, poll_attempt + 1)
            end)
            return
        end

        local run = hs.json.decode(body or "{}") or {}
        local run_status = run["status"] or ""
        local terminal_statuses = {
            completed = true,
            failed = true,
            not_found = true,
            stale_source = true,
            cancelled = true,
        }
        if not terminal_statuses[run_status] then
            hs.timer.doAfter(0.2, function()
                poll_ai_tools_result(urls, run_id, trigger_app, appName, config, originalClipboard, poll_attempt + 1)
            end)
            return
        end

        if run_status ~= "completed" then
            show_status("error", appName, "Sidekick finished with status: " .. run_status, true)
            if originalClipboard then
                hs.pasteboard.setContents(originalClipboard)
            end
            return
        end

        local output = run["primary_output"] or run["response_text"] or ""
        if output == "" then
            show_status("cancelled", appName)
            if originalClipboard then
                hs.pasteboard.setContents(originalClipboard)
            end
            return
        end
        paste_ai_tools_output(trigger_app, config, originalClipboard, output)
    end)
end

local function run_has_output_selected(run)
    local trace = run["trace"] or {}
    for _, entry in ipairs(trace) do
        if entry["kind"] == "output_selected" then
            return true
        end
    end
    return false
end

local function wait_for_ai_tools_user_selection(urls, run_id, trigger_app, appName, config, originalClipboard, attempt)
    local poll_attempt = attempt or 1
    if poll_attempt > 3600 then
        show_status("error", appName, "Timed out waiting for sidekick review.", true)
        if originalClipboard then
            hs.pasteboard.setContents(originalClipboard)
        end
        return
    end

    hs.http.asyncGet(urls.runs .. "/" .. run_id, {}, function(status, body, headers)
        if status ~= 200 then
            hs.timer.doAfter(0.5, function()
                wait_for_ai_tools_user_selection(urls, run_id, trigger_app, appName, config, originalClipboard, poll_attempt + 1)
            end)
            return
        end

        local run = hs.json.decode(body or "{}") or {}
        local run_status = run["status"] or ""
        if run_status == "completed" and run_has_output_selected(run) then
            local output = run["primary_output"] or run["response_text"] or ""
            if output == "" then
                show_status("cancelled", appName)
                if originalClipboard then
                    hs.pasteboard.setContents(originalClipboard)
                end
                return
            end
            paste_ai_tools_output(trigger_app, config, originalClipboard, output)
            return
        end

        if run_status == "failed" or run_status == "not_found" or run_status == "stale_source" or run_status == "cancelled" then
            show_status("error", appName, "Sidekick finished with status: " .. run_status, true)
            if originalClipboard then
                hs.pasteboard.setContents(originalClipboard)
            end
            return
        end

        if run_status == "completed" and poll_attempt == 1 then
            show_status("queued", appName, "Review in sidekick, edit if needed, then Apply to source.")
        end
        hs.timer.doAfter(0.5, function()
            wait_for_ai_tools_user_selection(urls, run_id, trigger_app, appName, config, originalClipboard, poll_attempt + 1)
        end)
    end)
end

local function should_wait_for_sidekick_selection(app_bucket)
    return app_bucket == "slack"
end

local function submit_ai_tools_direct(urls, trigger_app, appName, config, originalClipboard, text, nudge, wait_for_selection)
    local source_label = (appName and appName ~= "") and appName or "AI Tools"
    local payload = {
        ["source_kind"] = "ai_tools",
        ["source_label"] = source_label,
        ["source_id"] = "ai-tools-" .. tostring(os.time()),
        ["text"] = text,
        ["app_context"] = appName,
        ["nudge"] = nudge,
        ["intent"] = "reuse",
    }

    show_status("queued", appName)
    hs.http.asyncPost(urls.show, "{}", { ["Content-Type"] = "application/json" }, function() end)
    hs.http.asyncPost(urls.ai_tools, hs.json.encode(payload), { ["Content-Type"] = "application/json" }, function(status, body, headers)
        if status ~= 200 then
            log.e("Direct AI Tools submit failed; falling back to CLI. status=" .. tostring(status) .. " body=" .. tostring(body))
            if wait_for_selection then
                show_status("error", appName, "Sidekick submit failed; not auto-submitting Slack text.", true)
                if originalClipboard then
                    hs.pasteboard.setContents(originalClipboard)
                end
                return
            end
            local nudge_arg = ""
            if nudge == "explain" then
                nudge_arg = " --nudge explain"
            elseif nudge then
                nudge_arg = " --nudge " .. nudge
            end
            run_ai_tools_cli_fallback(trigger_app, appName, config, originalClipboard, text, nudge_arg)
            return
        end
        local response = hs.json.decode(body or "{}") or {}
        local run_id = response["run_id"]
        if not run_id or run_id == "" then
            show_status("error", appName, "Sidekick did not return a run id.", true)
            if originalClipboard then
                hs.pasteboard.setContents(originalClipboard)
            end
            return
        end
        if wait_for_selection then
            wait_for_ai_tools_user_selection(urls, run_id, trigger_app, appName, config, originalClipboard, 1)
        else
            poll_ai_tools_result(urls, run_id, trigger_app, appName, config, originalClipboard, 1)
        end
    end)
end

local function open_ai_tools_ask_mode(appName, originalClipboard)
    local urls = sidekick_urls()
    if originalClipboard then
        hs.pasteboard.setContents(originalClipboard)
    end
    hs.http.asyncGet(urls.ready, {}, function(status, body, headers)
        if status ~= 200 then
            hs.alert.show("Codex sidekick is not running\nStart: " .. web_panel_start_script .. " --restart", 6)
            log.e("AI Tools sidekick bridge unavailable for Ask mode: status=" .. tostring(status) .. " body=" .. tostring(body))
            return
        end
        local payload = hs.json.encode({ ["mode"] = "ask" })
        hs.http.asyncPost(urls.show, payload, { ["Content-Type"] = "application/json" }, function(show_status_code, show_body, show_headers)
            if show_status_code ~= 200 then
                show_status("error", appName, "Could not open Ask mode.", true)
                log.e("Ask mode panel show failed: status=" .. tostring(show_status_code) .. " body=" .. tostring(show_body))
                return
            end
            show_status("queued", appName, "Ask in the sidekick.")
        end)
    end)
end

local function run_processing(trigger_app, appName, config, scriptMode, windowArgs)
    -- Save original clipboard
    local originalClipboard = hs.pasteboard.getContents()

    -- Copy selected text
    config.copy()

    local text = hs.pasteboard.getContents()
    if not text or text == "" then
        open_ai_tools_ask_mode(appName, originalClipboard)
        return
    end

    if text:find("EOF") then
        show_status("error", appName, "Text contains EOF. Cannot safely use heredoc.", true)
        return
    end

    if ai_tools_sidekick_enabled then
        local urls = sidekick_urls()
        hs.http.asyncGet(urls.ready, {}, function(status, body, headers)
            if status ~= 200 then
                hs.alert.show("Codex sidekick is not running\nStart: " .. web_panel_start_script .. " --restart", 6)
                log.e("AI Tools sidekick bridge unavailable: status=" .. tostring(status) .. " body=" .. tostring(body))
                if originalClipboard then
                    hs.pasteboard.setContents(originalClipboard)
                end
                return
            end

            local app_bucket = normalize_app_bucket(appName)
            local nudge = nil
            if app_bucket == "iterm2" or app_bucket == "ghostty" then
                nudge = "explain"
            end
            submit_ai_tools_direct(
                urls,
                trigger_app,
                appName,
                config,
                originalClipboard,
                text,
                nudge,
                should_wait_for_sidekick_selection(app_bucket)
            )
        end)
        return
    end

    local heredoc = string.format(
        "cd %s && /opt/homebrew/bin/uv run %s %s %s <<'EOF'\n%s\nEOF",
        dir, scriptPath, scriptMode, windowArgs, text
    )
    show_status("processing", appName)

    local task = hs.task.new("/bin/zsh",
        function(exitCode, stdOut, stdErr)
            log.d("--- Python Output ---")
            log.d("Exit Code: " .. tostring(exitCode))
            log.d("stdout:\n" .. (stdOut or "[No stdout]"))
            log.d("stderr:\n" .. (stdErr or "[No stderr]"))

            if exitCode == nil then
                show_status("cancelled", appName)
                return
            end

            if exitCode ~= 0 then
                local stderr_text = (stdErr or ""):gsub("%s+$", "")
                local first_line = stderr_text:match("([^\n]+)") or "Unknown error"
                log.e("Model/tool execution failed script=" .. scriptPath)
                log.e("stderr:\n" .. (stderr_text ~= "" and stderr_text or "[No stderr]"))
                show_status("error", appName, "Model/tool failed: " .. first_line, true)
                return
            end

            if not stdOut or stdOut == "" then
                show_status("cancelled", appName)
                return
            end

            hs.pasteboard.setContents(stdOut)

            if trigger_app then
                trigger_app:activate()
            end
            hs.timer.usleep(200000)

            config.paste()

            -- Restore clipboard
            hs.timer.doAfter(0.5, function()
                hs.pasteboard.setContents(originalClipboard)
            end)
        end,
        { "-c", heredoc }
    )

    task:start()
end

function processAppText()
    local trigger_window = hs.window.focusedWindow()
    local trigger_app = (trigger_window and trigger_window:application()) or hs.application.frontmostApplication()
    local appName = trigger_app and trigger_app:name() or ""
    local config = app_configs[appName] or app_configs["default"]
    local scriptMode = string.format("--app %q", appName)
    local windowArgs = build_window_args(trigger_window, trigger_app)

    hs.timer.doAfter(0.2, function()
        run_processing(trigger_app, appName, config, scriptMode, windowArgs)
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
