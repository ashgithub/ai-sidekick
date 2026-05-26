const runSummaryEl = document.getElementById("run-summary");
const promptViewEl = document.getElementById("prompt-view");
const responseViewEl = document.getElementById("response-view");
const eventLogEl = document.getElementById("event-log");
const toolLogEl = document.getElementById("tool-log");
const approvalBoxEl = document.getElementById("approval-box");
const activeStatusEl = document.getElementById("active-status");
const sourceLineEl = document.getElementById("source-line");
const composerLabelEl = document.getElementById("composer-label");
const composerInputEl = document.getElementById("composer-input");
const refreshBtn = document.getElementById("refresh-btn");
const submitComposerBtn = document.getElementById("submit-composer-btn");
const newTaskBtn = document.getElementById("new-task-btn");
const phaseListEl = document.getElementById("phase-list");

let currentRun = null;
let composerIntent = "new";
let fallbackPoll = null;

async function fetchJson(url, options) {
  const response = await fetch(url, options);
  if (!response.ok) {
    throw new Error(`Request failed: ${response.status}`);
  }
  return await response.json();
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
  return run.last_summary || statusLabel(run.status);
}

function setComposerForRun(run) {
  if (!run) {
    composerIntent = "new";
    composerLabelEl.textContent = "Start new task";
    submitComposerBtn.textContent = "Start";
    return;
  }
  if (["queued", "starting", "running"].includes(run.status)) {
    composerIntent = "steer";
    composerLabelEl.textContent = "Steer this run";
    submitComposerBtn.textContent = "Steer";
    return;
  }
  if (run.thread_id) {
    composerIntent = "continue";
    composerLabelEl.textContent = "Continue this thread";
    submitComposerBtn.textContent = "Continue";
    return;
  }
  composerIntent = "new";
  composerLabelEl.textContent = "Start new task";
  submitComposerBtn.textContent = "Start";
}

function renderSummary(run) {
  runSummaryEl.innerHTML = "";

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
    turn_started: "Working",
    steered: "Steered",
    continued: "Follow-up started",
    first_response: "Response started",
    tool_started: `Tool started${tool}`,
    tool_completed: `Tool completed${tool}${duration}`,
    approval_started: "Approval review",
    approval_completed: "Approval review complete",
    not_found: "No source found",
    stale_source: "Source is stale",
    completed: "Completed",
    failed: "Failed",
  };
  return labels[entry.kind] || entry.label || entry.kind;
}

function renderPhaseList(run) {
  phaseListEl.innerHTML = "";
  const trace = Array.isArray(run.trace) ? run.trace : [];
  const visible = trace.filter((entry) => entry.kind !== "tool_completed" || entry.tool_name);
  if (!visible.length) {
    const item = document.createElement("li");
    item.textContent = "Waiting for Codex to report progress.";
    phaseListEl.appendChild(item);
    return;
  }

  visible.slice(-6).forEach((entry, index, entries) => {
    const item = document.createElement("li");
    if (index === entries.length - 1 && !["completed", "failed", "not_found", "stale_source"].includes(entry.kind)) {
      item.className = "current";
    }
    item.textContent = traceLabel(entry);
    phaseListEl.appendChild(item);
  });
}

function renderTrace(run) {
  const trace = Array.isArray(run.trace) ? run.trace : [];
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
  const trace = Array.isArray(run.trace) ? run.trace : [];
  const tools = trace.filter((entry) => entry.kind === "tool_started" || entry.kind === "tool_completed");
  if (!tools.length) {
    toolLogEl.textContent = "No tool calls yet.";
    return;
  }
  toolLogEl.textContent = tools.map((entry) => traceLabel(entry)).join("\n");
}

function renderApproval(run) {
  approvalBoxEl.innerHTML = "";
  if (!run.approval_needed) {
    approvalBoxEl.textContent = "No approval needed.";
    return;
  }

  const message = document.createElement("div");
  message.textContent = "Codex needs approval before continuing.";
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
  sourceLineEl.textContent = `${run.source.source_label} - ${run.thread_id || "Starting"}`;
  activeStatusEl.textContent = statusLabel(run.status);
  activeStatusEl.className = `status-pill ${statusClass(run.status)}`;
  renderSummary(run);
  renderPhaseList(run);
  responseViewEl.textContent = run.response_text || "No response yet.";
  promptViewEl.textContent = run.prompt || "No prompt yet.";
  renderTrace(run);
  renderTools(run);
  renderApproval(run);
  setComposerForRun(run);
}

function renderIdle() {
  currentRun = null;
  sourceLineEl.textContent = "Waiting for a shortcut";
  activeStatusEl.textContent = "Idle";
  activeStatusEl.className = "status-pill status-idle";
  runSummaryEl.textContent = "Waiting for a shortcut or task.";
  phaseListEl.innerHTML = "<li>No active invocation yet.</li>";
  responseViewEl.textContent = "No response yet.";
  promptViewEl.textContent = "No prompt yet.";
  eventLogEl.textContent = "No trace yet.";
  toolLogEl.textContent = "No tool calls yet.";
  approvalBoxEl.textContent = "No approval needed.";
  setComposerForRun(null);
}

function renderPayload(payload) {
  if (payload.run) {
    renderRun(payload.run);
  } else {
    renderIdle();
  }
}

async function refreshRuns() {
  const payload = await fetchJson("/api/current-run");
  renderPayload(payload);
}

async function submitComposer(intentOverride) {
  const prompt = composerInputEl.value.trim();
  if (!prompt) {
    return;
  }
  await fetchJson("/api/invoke", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      source_kind: "manual",
      source_label: "Sidekick",
      source_id: `sidekick-${Date.now()}`,
      prompt,
      intent: intentOverride || composerIntent,
    }),
  });
  composerInputEl.value = "";
  await refreshRuns();
}

async function approveRun(runId) {
  await fetchJson(`/api/runs/${runId}/approve`, { method: "POST", headers: { "Content-Type": "application/json" }, body: "{}" });
  await refreshRuns();
}

async function denyRun(runId) {
  await fetchJson(`/api/runs/${runId}/deny`, { method: "POST", headers: { "Content-Type": "application/json" }, body: "{}" });
  await refreshRuns();
}

function startEventStream() {
  if (!window.EventSource) {
    return false;
  }
  const events = new EventSource("/api/events");
  events.onmessage = (event) => {
    renderPayload(JSON.parse(event.data));
  };
  events.onerror = () => {
    events.close();
    if (!fallbackPoll) {
      fallbackPoll = setInterval(() => {
        refreshRuns().catch((error) => console.error(error));
      }, 3000);
    }
  };
  return true;
}

refreshBtn.addEventListener("click", refreshRuns);
submitComposerBtn.addEventListener("click", () => submitComposer());
newTaskBtn.addEventListener("click", () => submitComposer("new"));

refreshRuns().catch((error) => {
  console.error(error);
  runSummaryEl.textContent = "Failed to load panel state.";
});

if (!startEventStream()) {
  fallbackPoll = setInterval(() => {
    refreshRuns().catch((error) => console.error(error));
  }, 3000);
}
