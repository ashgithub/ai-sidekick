local log = hs.logger.new("SlackCodexWorkflow", "debug")

local workflow_dir = os.getenv("HOME") .. "/work/code/python/ai_tools/slack_codex_workflow"
local prompt_file = workflow_dir .. "/prompts/codex_worker.md"
local codex_bin = os.getenv("CODEX_BIN") or "/opt/homebrew/bin/codex"
local hotkey_mods = { "ctrl", "alt", "cmd" }
local hotkey_key = "right"
local active_tasks = {}

local function append_spike_log(message)
    local path = "/tmp/slack_codex_workflow_hammerspoon.log"
    local file = io.open(path, "a")
    if file then
        file:write(os.date("%Y-%m-%dT%H:%M:%S%z") .. " " .. message .. "\n")
        file:close()
    end
end

local function submit_codex_app_prompt_from_clipboard()
    append_spike_log("submit handler invoked")
    hs.application.launchOrFocus("Codex")
    hs.timer.doAfter(1.0, function()
        append_spike_log("creating new chat")
        hs.eventtap.keyStroke({ "cmd" }, "n")
        hs.timer.doAfter(1.2, function()
            append_spike_log("pasting prompt")
            hs.eventtap.keyStroke({ "cmd" }, "v")
            hs.timer.doAfter(0.5, function()
                append_spike_log("submitting prompt")
                hs.eventtap.keyStroke({ "cmd" }, "return")
            end)
        end)
    end)
end

_G.slackCodexSubmitPromptFromClipboard = submit_codex_app_prompt_from_clipboard

local function read_file(path)
    local file = io.open(path, "r")
    if not file then
        return nil
    end

    local contents = file:read("*a")
    file:close()
    return contents
end

local function now_iso()
    return os.date("%Y-%m-%dT%H:%M:%S%z")
end

local function frontmost_context()
    local window = hs.window.focusedWindow()
    local app = (window and window:application()) or hs.application.frontmostApplication()

    return {
        app_name = app and app:name() or "",
        bundle_id = app and app:bundleID() or "",
        window_title = window and window:title() or "",
        captured_at = now_iso(),
    }
end

local function build_payload(context, copied_text)
    local selection_state = "present"
    if copied_text == nil or copied_text == "" then
        selection_state = "empty"
    end

    local lines = {
        "Slack Codex hotkey task",
        "",
        "Captured by: Hammerspoon",
        "Captured at: " .. context.captured_at,
        "Source app: " .. context.app_name,
        "Bundle id: " .. context.bundle_id,
        "Window title: " .. context.window_title,
        "Captured text capture mode: none",
        "Captured text selection: " .. selection_state,
        "",
        "Captured text:",
        copied_text or "",
        "",
        "Instructions:",
        "Use Slack app only. Fail immediately if the Slack connector is unavailable.",
        "Start every Slack message you send or edit with [from codex :bot:].",
        "Keep the wand status message and do not use reactions.",
        "Search Slack for Ashish's newest @codex message from the last five minutes.",
        "Use the found @codex message and thread as the source task and audit trail.",
        "If no recent @codex message is found, stop with the not-found message from the worker prompt.",
        "Do not use the old queue channel.",
        "Complete the requested work, reply in the original Slack conversation when appropriate, and update the source status thread reply.",
    }

    return table.concat(lines, "\n")
end

local function build_full_prompt(payload)
    local worker_prompt = read_file(prompt_file)
    if not worker_prompt then
        return nil, "worker prompt not found: " .. prompt_file
    end

    return worker_prompt .. "\n\n## Captured Hotkey Payload\n\n" .. payload .. "\n", nil
end

local function launch_codex_app_worker(payload)
    local full_prompt, err = build_full_prompt(payload)
    if not full_prompt then
        hs.alert.show("Codex Slack worker prompt missing", 4)
        log.e(err)
        return
    end

    if not hs.pasteboard.setContents(full_prompt) then
        hs.alert.show("Codex Slack worker failed to prepare prompt", 4)
        log.e("Failed to write Codex worker prompt to clipboard")
        return
    end

    local task

    task = hs.task.new(codex_bin, function(exit_code, stdout, stderr)
        active_tasks[task] = nil

        if exit_code == 0 then
            log.i("Codex.app workspace opened")
            if stdout and stdout ~= "" then
                log.d(stdout)
            end
            return
        end

        local detail = stderr
        if not detail or detail == "" then
            detail = stdout or "unknown error"
        end
        hs.alert.show("Codex.app worker launch failed", 4)
        log.e("Codex.app worker launch failed: " .. tostring(detail))
    end, { "app", workflow_dir })

    active_tasks[task] = task

    if task:start() then
        hs.alert.show("Opening Codex Slack worker", 2)
        log.i("Codex.app worker handoff started")
        hs.timer.doAfter(1.5, submit_codex_app_prompt_from_clipboard)
        return
    end

    active_tasks[task] = nil
    hs.alert.show("Codex.app worker failed to start", 4)
    log.e("Codex.app worker failed to start")
end

local function run_slack_codex_workflow()
    local context = frontmost_context()
    local app_name_lower = string.lower(context.app_name or "")

    if not string.find(app_name_lower, "slack", 1, true) then
        hs.alert.show("Focus Slack before using Codex workflow", 3)
        return
    end

    hs.alert.show("Looking for recent @codex task", 1.5)

    local copied_text = ""
    local payload = build_payload(context, copied_text)
    launch_codex_app_worker(payload)
end

hs.hotkey.bind(hotkey_mods, hotkey_key, run_slack_codex_workflow)
hs.urlevent.bind("slackCodexSubmitPrompt", submit_codex_app_prompt_from_clipboard)
hs.alert.show("Slack Codex workflow loaded", 2)
log.i("Loaded Slack Codex workflow hotkey: ctrl+alt+cmd+right")
