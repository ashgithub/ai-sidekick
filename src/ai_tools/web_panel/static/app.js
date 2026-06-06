const runSummaryEl = document.getElementById("run-summary");
const promptViewEl = document.getElementById("prompt-view");
const rawStreamEl = document.getElementById("raw-stream-view");
const eventLogEl = document.getElementById("event-log");
const toolLogEl = document.getElementById("tool-log");
const approvalBoxEl = document.getElementById("approval-box");
const activeStatusEl = document.getElementById("active-status");
const sourceLineEl = document.getElementById("source-line");
const abortBtn = document.getElementById("abort-btn");
const refreshBtn = document.getElementById("refresh-btn");
const closePanelBtn = document.getElementById("close-panel-btn");
const modeRewriteBtn = document.getElementById("mode-rewrite-btn");
const modeAskBtn = document.getElementById("mode-ask-btn");
const rewritePaneEl = document.getElementById("rewrite-pane");
const askPaneEl = document.getElementById("ask-pane");
const rewriteHelperEl = document.getElementById("rewrite-helper");
const versionTabsEl = document.getElementById("version-tabs");
const versionRewrittenBtn = document.getElementById("version-rewritten-btn");
const versionCorrectedBtn = document.getElementById("version-corrected-btn");
const selectedOutputTextareaEl = document.getElementById("selected-output-textarea");
const useOutputBtn = document.getElementById("use-output-btn");
const copyOutputBtn = document.getElementById("copy-output-btn");
const rewriteFeedbackEl = document.getElementById("rewrite-feedback");
const refineDrawerEl = document.getElementById("refine-drawer");
const refineInputEl = document.getElementById("refine-input");
const refineThreadModeEl = document.getElementById("refine-thread-mode");
const refineSubmitBtn = document.getElementById("refine-submit-btn");
const refineFeedbackEl = document.getElementById("refine-feedback");
const askInputEl = document.getElementById("ask-input");
const askSubmitBtn = document.getElementById("ask-submit-btn");
const askNewBtn = document.getElementById("ask-new-btn");
const askOutputViewEl = document.getElementById("ask-output-view");
const phaseListEl = document.getElementById("phase-list");

let currentRun = null;
let currentMode = "rewrite";
let fallbackPoll = null;
let eventStream = null;
let eventStreamReconnectTimer = null;
let selectedOutputKey = "rewritten";
let selectedOutputDirty = false;
let selectedOutputRunId = null;
let outputSelecting = false;
let askSubmitting = false;
let copyFeedbackTimer = null;
let applyFeedbackTimer = null;
let feedbackToken = 0;
let refineSubmitting = false;
let refineFeedbackTimer = null;
let lastAskQuestion = "";

async function fetchJson(url, options) {
  const response = await fetch(url, options);
  if (!response.ok) {
    throw new Error(`Request failed: ${response.status}`);
  }
  return await response.json();
}

function normalizeMode(mode) {
  return mode === "ask" ? "ask" : "rewrite";
}

function transferBlankModeText(nextMode) {
  if (nextMode === "ask" && askInputEl.value.trim() === "") {
    askInputEl.value = selectedOutputTextareaEl.value;
    return;
  }
  if (nextMode === "rewrite" && selectedOutputTextareaEl.value.trim() === "") {
    selectedOutputTextareaEl.value = askInputEl.value;
    selectedOutputDirty = selectedOutputTextareaEl.value.trim() !== "";
  }
}

function setMode(mode, options = {}) {
  const nextMode = normalizeMode(mode);
  if (options.transferBlank && nextMode !== currentMode) {
    transferBlankModeText(nextMode);
  }
  currentMode = nextMode;
  const askActive = currentMode === "ask";
  modeAskBtn.classList.toggle("active", askActive);
  modeRewriteBtn.classList.toggle("active", !askActive);
  modeAskBtn.setAttribute("aria-selected", String(askActive));
  modeRewriteBtn.setAttribute("aria-selected", String(!askActive));
  askPaneEl.hidden = !askActive;
  rewritePaneEl.hidden = askActive;
  if (options.persist) {
    fetchJson("/api/panel/show", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ mode: currentMode }),
    }).catch((error) => console.error(error));
  }
  renderModeContent();
}

function statusLabel(status) {
  const labels = {
    queued: "Queued",
    starting: "Starting",
    running: "Running",
    approval_needed: "Approval",
    not_found: "Needs source",
    stale_source: "Stale source",
    completed: "Done",
    cancelled: "Aborted",
    failed: "Failed",
  };
  return labels[status] || "Idle";
}

function statusClass(status) {
  const classes = {
    queued: "status-queued",
    starting: "status-starting",
    running: "status-running",
    approval_needed: "status-approval_needed",
    not_found: "status-not_found",
    stale_source: "status-stale_source",
    completed: "status-completed",
    cancelled: "status-cancelled",
    failed: "status-failed",
  };
  return classes[status] || "status-idle";
}

function summaryTitle(run) {
  if (run.status === "not_found") {
    return "No @codex message found";
  }
  if (run.status === "stale_source") {
    return "Stale @codex message";
  }
  if (run.status === "approval_needed") {
    return "Approval needed";
  }
  if (run.status === "cancelled") {
    return "Aborted";
  }
  return run.last_summary || statusLabel(run.status);
}

function appendInlineText(parent, text) {
  text.split(/(`[^`]+`)/g).filter(Boolean).forEach((part) => {
    if (part.startsWith("`") && part.endsWith("`") && part.length > 1) {
      const code = document.createElement("code");
      code.textContent = part.slice(1, -1);
      parent.appendChild(code);
      return;
    }
    parent.appendChild(document.createTextNode(part));
  });
}

function renderReadableText(container, text, placeholder) {
  container.innerHTML = "";
  const content = (text || "").trim();
  if (!content) {
    const empty = document.createElement("p");
    empty.className = "answer-placeholder";
    empty.textContent = placeholder;
    container.appendChild(empty);
    return;
  }

  let paragraphLines = [];
  let listEl = null;
  let codeLines = [];
  let inCode = false;

  function flushParagraph() {
    if (!paragraphLines.length) {
      return;
    }
    const paragraph = document.createElement("p");
    appendInlineText(paragraph, paragraphLines.join(" "));
    container.appendChild(paragraph);
    paragraphLines = [];
  }

  function closeList() {
    listEl = null;
  }

  function flushCode() {
    const pre = document.createElement("pre");
    pre.className = "answer-code";
    const code = document.createElement("code");
    code.textContent = codeLines.join("\n");
    pre.appendChild(code);
    container.appendChild(pre);
    codeLines = [];
  }

  content.split("\n").forEach((line) => {
    const trimmed = line.trim();
    if (trimmed.startsWith("```")) {
      flushParagraph();
      closeList();
      if (inCode) {
        flushCode();
      }
      inCode = !inCode;
      return;
    }
    if (inCode) {
      codeLines.push(line);
      return;
    }
    if (!trimmed) {
      flushParagraph();
      closeList();
      return;
    }

    const heading = trimmed.match(/^#{1,3}\s+(.+)$/);
    if (heading) {
      flushParagraph();
      closeList();
      const title = document.createElement("h3");
      appendInlineText(title, heading[1]);
      container.appendChild(title);
      return;
    }

    const bullet = trimmed.match(/^[-*]\s+(.+)$/);
    if (bullet) {
      flushParagraph();
      if (!listEl || listEl.tagName !== "UL") {
        listEl = document.createElement("ul");
        container.appendChild(listEl);
      }
      const item = document.createElement("li");
      appendInlineText(item, bullet[1]);
      listEl.appendChild(item);
      return;
    }

    const numbered = trimmed.match(/^\d+\.\s+(.+)$/);
    if (numbered) {
      flushParagraph();
      if (!listEl || listEl.tagName !== "OL") {
        listEl = document.createElement("ol");
        container.appendChild(listEl);
      }
      const item = document.createElement("li");
      appendInlineText(item, numbered[1]);
      listEl.appendChild(item);
      return;
    }

    closeList();
    paragraphLines.push(trimmed);
  });

  if (inCode) {
    flushCode();
  }
  flushParagraph();
}

async function copyText(text) {
  if (!text) {
    return false;
  }
  if (navigator.clipboard && navigator.clipboard.writeText) {
    await navigator.clipboard.writeText(text);
    return true;
  }
  const scratch = document.createElement("textarea");
  scratch.value = text;
  scratch.setAttribute("readonly", "readonly");
  scratch.style.position = "fixed";
  scratch.style.left = "-9999px";
  document.body.appendChild(scratch);
  scratch.select();
  document.execCommand("copy");
  document.body.removeChild(scratch);
  return true;
}

function setTemporaryFeedback(message, button, label, timerKey) {
  feedbackToken += 1;
  const token = feedbackToken;
  rewriteFeedbackEl.textContent = message;
  button.textContent = label;
  button.classList.add("success-state");
  if (timerKey === "copy" && copyFeedbackTimer) {
    clearTimeout(copyFeedbackTimer);
  }
  if (timerKey === "apply" && applyFeedbackTimer) {
    clearTimeout(applyFeedbackTimer);
  }
  const timer = setTimeout(() => {
    if (token === feedbackToken) {
      rewriteFeedbackEl.textContent = "";
    }
    button.classList.remove("success-state");
    button.textContent = timerKey === "copy" ? "Copy text" : selectedOutputChanged(currentRun) ? "Review edits" : "Apply to source";
  }, 1600);
  if (timerKey === "copy") {
    copyFeedbackTimer = timer;
  } else {
    applyFeedbackTimer = timer;
  }
}

async function copySelectedOutput() {
  const copied = await copyText(selectedOutputTextareaEl.value);
  if (copied) {
    setTemporaryFeedback("Copied to clipboard.", copyOutputBtn, "Copied", "copy");
  }
}

function selectedLabelForRun(run) {
  if (!run) {
    return "Rewritten";
  }
  return run.selected_output_label === "Corrected" ? "Corrected" : "Rewritten";
}

function outputText(run, key) {
  if (!run) {
    return "";
  }
  const structured = run.structured_output || {};
  if (key === "corrected") {
    return structured.corrected || "";
  }
  if (key === "rewritten") {
    return structured.rewritten || run.primary_output || run.response_text || "";
  }
  return run.primary_output || run.response_text || "";
}

function selectedOutputChanged(run) {
  if (!canSelectOutput(run)) {
    return false;
  }
  return selectedOutputTextareaEl.value !== outputText(run, selectedOutputKey);
}

function canSelectOutput(run) {
  return run && run.source && run.source.source_kind === "ai_tools" && run.status === "completed";
}

function canRefineRun(run) {
  return run && run.thread_id && run.source && run.source.source_kind === "ai_tools";
}

function renderVersionTabs(run) {
  const isTextPair = run && run.render_kind === "text_pair";
  versionTabsEl.hidden = !isTextPair;
  if (!isTextPair) {
    selectedOutputKey = "primary";
    return;
  }
  if (selectedOutputRunId !== run.run_id) {
    selectedOutputKey = selectedLabelForRun(run).toLowerCase();
    selectedOutputRunId = run.run_id;
    selectedOutputDirty = false;
  }
  versionRewrittenBtn.classList.toggle("active", selectedOutputKey === "rewritten");
  versionCorrectedBtn.classList.toggle("active", selectedOutputKey === "corrected");
  versionRewrittenBtn.setAttribute("aria-selected", String(selectedOutputKey === "rewritten"));
  versionCorrectedBtn.setAttribute("aria-selected", String(selectedOutputKey === "corrected"));
}

function renderRewritePane() {
  const run = currentRun;
  renderVersionTabs(run);
  const output = outputText(run, selectedOutputKey);
  const shouldReplaceText = !selectedOutputDirty || selectedOutputRunId !== (run && run.run_id);
  if (shouldReplaceText) {
    selectedOutputTextareaEl.value = output;
  }
  const canUse = canSelectOutput(run) && selectedOutputTextareaEl.value.trim() !== "";
  useOutputBtn.disabled = !canUse || outputSelecting;
  useOutputBtn.textContent = selectedOutputChanged(run) ? "Review edits" : "Apply to source";
  copyOutputBtn.disabled = selectedOutputTextareaEl.value.trim() === "" || outputSelecting;
  refineDrawerEl.hidden = !canRefineRun(run);
  refineSubmitBtn.disabled = refineSubmitting || !refineInputEl.value.trim();
  if (!run) {
    rewriteHelperEl.textContent = "Select text in an app, run the shortcut, then choose the version to use.";
    selectedOutputTextareaEl.placeholder = "Output will appear here.";
    return;
  }
  if (run.status === "running" || run.status === "starting" || run.status === "queued") {
    rewriteHelperEl.textContent = "Working on the selected text.";
    selectedOutputTextareaEl.placeholder = "Writing output...";
    return;
  }
  rewriteHelperEl.textContent = run.render_kind === "text_pair"
    ? "Switch versions, edit the text, then apply it back to the source app."
    : "Review the output, edit if needed, then apply it back to the source app.";
}

function refinementPrompt(feedback, draft) {
  return [
    "Revise the current draft using the feedback below.",
    "Keep the same output format as the current sidekick run.",
    "",
    "Feedback:",
    feedback,
    "",
    "Current draft:",
    draft || "(No draft text yet.)",
  ].join("\n");
}

function setRefineFeedback(message) {
  refineFeedbackEl.textContent = message;
  refineSubmitBtn.textContent = "Sent";
  refineSubmitBtn.classList.add("success-state");
  if (refineFeedbackTimer) {
    clearTimeout(refineFeedbackTimer);
  }
  refineFeedbackTimer = setTimeout(() => {
    refineFeedbackEl.textContent = "";
    refineSubmitBtn.textContent = "Revise with instruction";
    refineSubmitBtn.classList.remove("success-state");
  }, 1600);
}

async function submitRefinement() {
  if (!canRefineRun(currentRun) || refineSubmitting) {
    return;
  }
  const feedback = refineInputEl.value.trim();
  if (!feedback) {
    return;
  }
  refineSubmitting = true;
  refineSubmitBtn.disabled = true;
  try {
    await fetchJson("/api/invoke", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        source_kind: "manual",
        source_label: "Refine",
        source_id: `refine-${Date.now()}`,
        prompt: refinementPrompt(feedback, selectedOutputTextareaEl.value),
        intent: refineThreadModeEl.value === "new" ? "new" : "auto",
      }),
    });
    refineInputEl.value = "";
    selectedOutputDirty = false;
    setRefineFeedback("Revision requested.");
    await refreshRuns();
  } finally {
    refineSubmitting = false;
    renderRewritePane();
  }
}

function isAskRun(run) {
  return run && run.source && (run.source.source_label === "Ask" || run.panel_mode === "ask");
}

function renderAskPane() {
  const shouldShowAnswer = isAskRun(currentRun);
  const answer = shouldShowAnswer ? currentRun.primary_output || currentRun.response_text || "" : "";
  const question = lastAskQuestion || (shouldShowAnswer ? currentRun.display_input_text || currentRun.prompt || "" : "");
  if (askInputEl.value.trim() === "" && question.trim() !== "") {
    askInputEl.value = question;
  }
  renderReadableText(askOutputViewEl, answer, shouldShowAnswer && currentRun.status !== "completed" ? "Working..." : "No answer yet.");
}

function renderModeContent() {
  if (currentMode === "ask") {
    renderAskPane();
    return;
  }
  renderRewritePane();
}

async function selectOutput() {
  if (!canSelectOutput(currentRun) || outputSelecting) {
    return;
  }
  const text = selectedOutputTextareaEl.value;
  if (!text.trim()) {
    return;
  }
  outputSelecting = true;
  renderRewritePane();
  try {
    if (selectedOutputChanged(currentRun)) {
      await fetchJson(`/api/runs/${currentRun.run_id}/review-output`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ output_key: selectedOutputKey, text }),
      });
      rewriteFeedbackEl.textContent = "Reviewing changes.";
      selectedOutputDirty = false;
      await refreshRuns();
      return;
    }
    await fetchJson(`/api/runs/${currentRun.run_id}/select-output`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ output_key: selectedOutputKey, text }),
    });
    await copyText(text);
    setTemporaryFeedback("Applied to source.", useOutputBtn, "Applied", "apply");
    selectedOutputDirty = false;
    await refreshRuns();
  } finally {
    outputSelecting = false;
    renderRewritePane();
  }
}

async function submitAsk() {
  if (askSubmitting) {
    return;
  }
  const prompt = askInputEl.value.trim();
  if (!prompt) {
    return;
  }
  askSubmitting = true;
  askSubmitBtn.disabled = true;
  askNewBtn.disabled = true;
  try {
    await fetchJson("/api/invoke", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        source_kind: "manual",
        source_label: "Ask",
        source_id: `ask-${Date.now()}`,
        prompt,
        intent: "new",
      }),
    });
    lastAskQuestion = prompt;
    askInputEl.value = lastAskQuestion;
    await refreshRuns();
  } finally {
    askSubmitting = false;
    askSubmitBtn.disabled = false;
    askNewBtn.disabled = false;
  }
}

async function closePanel() {
  closePanelBtn.disabled = true;
  try {
    await fetchJson("/api/panel/hide", { method: "POST", headers: { "Content-Type": "application/json" }, body: "{}" });
  } finally {
    closePanelBtn.disabled = false;
  }
}

function canAbort(run) {
  return run && ["queued", "starting", "running", "approval_needed"].includes(run.status);
}

function renderSummary(run) {
  runSummaryEl.innerHTML = "";
  if (!run) {
    runSummaryEl.textContent = currentMode === "ask" ? "Ask a question." : "Ready.";
    return;
  }

  const title = document.createElement("div");
  title.className = "summary-title";
  title.textContent = summaryTitle(run);
  runSummaryEl.appendChild(title);

  const meta = document.createElement("div");
  meta.className = "summary-meta";
  meta.textContent = `${run.source.source_label} · ${statusLabel(run.status)}`;
  runSummaryEl.appendChild(meta);
}

function traceLabel(entry) {
  const tool = entry.tool_name ? `: ${entry.tool_name}` : "";
  const duration = entry.duration_ms === null || entry.duration_ms === undefined ? "" : ` (${entry.duration_ms}ms)`;
  const labels = {
    accepted: "Queued",
    codex_started: "Codex ready",
    thread_started: "Thread ready",
    thread_reused: "Thread ready",
    turn_started: "Working",
    steered: "Steered",
    continued: "Follow-up started",
    first_response: "Response started",
    tool_started: `Tool started${tool}`,
    tool_completed: `Tool completed${tool}${duration}`,
    approval_started: "Approval review",
    approval_completed: "Approval review complete",
    output_selected: "Output selected",
    not_found: "No source found",
    stale_source: "Source is stale",
    completed: "Completed",
    cancelled: "Aborted",
    failed: "Failed",
  };
  return labels[entry.kind] || entry.label || entry.kind;
}

function renderPhaseList(run) {
  phaseListEl.innerHTML = "";
  const trace = run && Array.isArray(run.trace) ? run.trace : [];
  const visible = trace.filter((entry) => entry.kind !== "tool_completed" || entry.tool_name);
  if (!visible.length) {
    const item = document.createElement("li");
    item.textContent = "No activity yet.";
    phaseListEl.appendChild(item);
    return;
  }

  visible.slice(-6).forEach((entry, index, entries) => {
    const item = document.createElement("li");
    if (index === entries.length - 1 && !["completed", "failed", "cancelled", "not_found", "stale_source"].includes(entry.kind)) {
      item.className = "current";
    }
    item.textContent = traceLabel(entry);
    phaseListEl.appendChild(item);
  });
}

function renderTrace(run) {
  const trace = run && Array.isArray(run.trace) ? run.trace : [];
  if (!trace.length) {
    eventLogEl.textContent = "No trace yet.";
    return;
  }
  eventLogEl.textContent = trace.map((entry) => {
    const duration = entry.duration_ms === null || entry.duration_ms === undefined ? "" : ` ${entry.duration_ms}ms`;
    const tool = entry.tool_name ? ` ${entry.tool_name}` : "";
    const status = entry.status ? ` ${entry.status}` : "";
    return `[${entry.kind}]${tool}${status}${duration} ${entry.label}`;
  }).join("\n");
}

function renderTools(run) {
  const trace = run && Array.isArray(run.trace) ? run.trace : [];
  const tools = trace.filter((entry) => entry.kind === "tool_started" || entry.kind === "tool_completed");
  if (!tools.length) {
    toolLogEl.textContent = "No tool calls yet.";
    return;
  }
  toolLogEl.textContent = tools.map((entry) => traceLabel(entry)).join("\n");
}

function renderApproval(run) {
  approvalBoxEl.innerHTML = "";
  approvalBoxEl.hidden = !(run && run.approval_needed);
  if (!run || !run.approval_needed) {
    return;
  }

  const message = document.createElement("div");
  message.textContent = "Approval needed before Codex can continue.";
  approvalBoxEl.appendChild(message);

  const actions = document.createElement("div");
  actions.className = "approval-actions";
  const approve = document.createElement("button");
  approve.type = "button";
  approve.textContent = "Approve";
  approve.addEventListener("click", () => approveRun(run.run_id));
  const deny = document.createElement("button");
  deny.type = "button";
  deny.className = "secondary";
  deny.textContent = "Deny";
  deny.addEventListener("click", () => denyRun(run.run_id));
  actions.appendChild(approve);
  actions.appendChild(deny);
  approvalBoxEl.appendChild(actions);
}

function renderRun(run) {
  currentRun = run;
  sourceLineEl.textContent = run ? `${run.source.source_label} - ${run.thread_id || "Starting"}` : "Waiting for a shortcut";
  activeStatusEl.textContent = run ? statusLabel(run.status) : "Idle";
  activeStatusEl.className = `status-pill ${run ? statusClass(run.status) : "status-idle"}`;
  abortBtn.hidden = !canAbort(run);
  abortBtn.disabled = !canAbort(run);
  promptViewEl.textContent = run && run.prompt ? run.prompt : "No prompt yet.";
  rawStreamEl.textContent = run && run.raw_response_text ? run.raw_response_text : "No raw output yet.";
  renderSummary(run);
  renderPhaseList(run);
  renderTrace(run);
  renderTools(run);
  renderApproval(run);
  renderModeContent();
}

function renderPayload(payload) {
  const payloadMode = payload.run && payload.run.panel_mode ? payload.run.panel_mode : payload.panel_mode;
  setMode(payloadMode || currentMode);
  renderRun(payload.run || null);
}

async function refreshRuns() {
  const payload = await fetchJson("/api/current-run");
  renderPayload(payload);
}

async function approveRun(runId) {
  await fetchJson(`/api/runs/${runId}/approve`, { method: "POST", headers: { "Content-Type": "application/json" }, body: "{}" });
  await refreshRuns();
}

async function denyRun(runId) {
  await fetchJson(`/api/runs/${runId}/deny`, { method: "POST", headers: { "Content-Type": "application/json" }, body: "{}" });
  await refreshRuns();
}

async function abortRun(runId) {
  if (!runId) {
    return;
  }
  abortBtn.disabled = true;
  await fetchJson(`/api/runs/${runId}/abort`, { method: "POST", headers: { "Content-Type": "application/json" }, body: "{}" });
  await refreshRuns();
}

function startFallbackPolling() {
  if (fallbackPoll) {
    return;
  }
  fallbackPoll = setInterval(() => {
    refreshRuns().catch((error) => console.error(error));
  }, 3000);
}

function stopFallbackPolling() {
  if (!fallbackPoll) {
    return;
  }
  clearInterval(fallbackPoll);
  fallbackPoll = null;
}

function scheduleEventStreamReconnect() {
  if (eventStreamReconnectTimer) {
    return;
  }
  eventStreamReconnectTimer = setTimeout(startEventStream, 1000);
}

function startEventStream() {
  if (!window.EventSource) {
    return false;
  }
  if (eventStream && eventStream.readyState !== EventSource.CLOSED) {
    return true;
  }
  eventStreamReconnectTimer = null;
  const events = new EventSource("/api/events");
  eventStream = events;
  events.onopen = () => {
    stopFallbackPolling();
  };
  events.onmessage = (event) => {
    renderPayload(JSON.parse(event.data));
  };
  events.onerror = () => {
    events.close();
    if (eventStream === events) {
      eventStream = null;
    }
    startFallbackPolling();
    scheduleEventStreamReconnect();
  };
  return true;
}

modeRewriteBtn.addEventListener("click", () => setMode("rewrite", { persist: true, transferBlank: true }));
modeAskBtn.addEventListener("click", () => setMode("ask", { persist: true, transferBlank: true }));
versionRewrittenBtn.addEventListener("click", () => {
  selectedOutputKey = "rewritten";
  selectedOutputDirty = false;
  renderRewritePane();
});
versionCorrectedBtn.addEventListener("click", () => {
  selectedOutputKey = "corrected";
  selectedOutputDirty = false;
  renderRewritePane();
});
selectedOutputTextareaEl.addEventListener("input", () => {
  selectedOutputDirty = selectedOutputChanged(currentRun);
  renderRewritePane();
});
refineInputEl.addEventListener("input", renderRewritePane);
refreshBtn.addEventListener("click", refreshRuns);
closePanelBtn.addEventListener("click", () => closePanel().catch((error) => console.error(error)));
abortBtn.addEventListener("click", () => abortRun(currentRun && currentRun.run_id));
useOutputBtn.addEventListener("click", () => selectOutput().catch((error) => console.error(error)));
copyOutputBtn.addEventListener("click", () => copySelectedOutput().catch((error) => console.error(error)));
refineSubmitBtn.addEventListener("click", () => submitRefinement().catch((error) => console.error(error)));
askSubmitBtn.addEventListener("click", () => submitAsk().catch((error) => console.error(error)));
askNewBtn.addEventListener("click", () => {
  askInputEl.value = "";
  lastAskQuestion = "";
  renderReadableText(askOutputViewEl, "", "No answer yet.");
  askInputEl.focus();
});

refreshRuns().catch((error) => {
  console.error(error);
  runSummaryEl.textContent = "Failed to load panel state.";
});

if (!startEventStream()) {
  startFallbackPolling();
}
