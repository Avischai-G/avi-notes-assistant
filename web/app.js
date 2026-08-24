const $ = (selector) => document.querySelector(selector);
const transcript = $("#transcript");
const input = $("#input");
const send = $("#send");
const chips = $("#attachment-chips");
const taskNav = $("#nav-task-chat");
const lifeNav = $("#nav-life-chat");
const automationNav = $("#automation-nav");
const surfaceHeader = $("#surface-header");
const surfaceTitle = $("#surface-title");
const surfaceSchedule = $("#surface-schedule");
const runNow = $("#run-now");
const composerGrid = $("#composer-grid");
const TASK_CHANNEL_KEY = "avi-notes-task-channel";
const LIFE_CHANNEL_KEY = "avi-notes-life-channel";
const PAGE = 30;

let channelId = null;
let chatEndpoint = "chat";
let attachments = [];
let streaming = false;
let automations = [];
let activeAutomation = null;
let nextBefore = 0;

const esc = (value) => String(value ?? "").replace(
  /[&<>"']/g,
  (character) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[character],
);

function markdown(source) {
  let html = esc(source);
  html = html
    .replace(/```([\s\S]*?)```/g, "<pre><code>$1</code></pre>")
    .replace(/`([^`]+)`/g, "<code>$1</code>")
    .replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>")
    .replace(/\*([^*]+)\*/g, "<em>$1</em>");
  return html.split(/\n\n+/).map((block) => {
    const lines = block.split("\n");
    if (lines.length && lines.every((line) => /^[-*] /.test(line))) {
      return `<ul>${lines.map((line) => `<li>${line.slice(2)}</li>`).join("")}</ul>`;
    }
    return `<p>${block.replace(/\n/g, "<br>")}</p>`;
  }).join("");
}

function bottom() {
  transcript.scrollTop = transcript.scrollHeight;
}

function assistantStack(row) {
  let stack = row.querySelector(".assistant-stack");
  if (!stack) {
    stack = document.createElement("div");
    stack.className = "assistant-stack";
    row.append(stack);
  }
  return stack;
}

function buildMessage(role, content) {
  const row = document.createElement("div");
  row.className = `message-row ${role}`;
  const parent = role === "assistant" ? assistantStack(row) : row;
  const bubble = document.createElement("div");
  bubble.className = "message-bubble";
  if (role === "assistant") {
    bubble.classList.add("markdown");
    bubble.innerHTML = markdown(content);
  } else {
    bubble.textContent = content;
  }
  parent.append(bubble);
  return { row, bubble, parent };
}

function addMessage(role, content, controls = null, { animate = false } = {}) {
  const built = buildMessage(role, content);
  if (animate) built.row.classList.add("entering");
  transcript.append(built.row);
  if (controls) renderPlanControls(built.parent, controls);
  bottom();
  return built;
}

async function apiJSON(url, options = {}) {
  const response = await fetch(url, options);
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(data.detail || `${response.status} ${response.statusText}`);
  return data;
}

function renderPlanControls(parent, controls) {
  if (!Array.isArray(controls) || controls.length !== 2) return;
  if (controls.some((control) => !["A", "B"].includes(control.id))) return;
  parent.querySelector(".plan-controls")?.remove();
  const group = document.createElement("div");
  group.className = "plan-controls";
  group.setAttribute("role", "group");
  group.setAttribute("aria-label", "Choose tomorrow's plan");
  for (const control of controls) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "plan-control";
    button.textContent = control.label;
    button.addEventListener("click", async () => {
      const buttons = [...group.querySelectorAll("button")];
      buttons.forEach((item) => { item.disabled = true; });
      try {
        const data = await apiJSON("/api/automations/nightly-plan/pick", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ plan: control.id }),
        });
        group.remove();
        addMessage("assistant", data.text, null, { animate: true });
      } catch (error) {
        buttons.forEach((item) => { item.disabled = false; });
        addMessage("assistant", `Error: ${error.message}`);
      }
    });
    group.append(button);
  }
  parent.append(group);
  bottom();
}

function resize() {
  composerGrid.dataset.expanded = "false";
  input.style.height = "";
  // An empty composer is always the collapsed single line; only typed content
  // needs measuring. One line is 48px; past ~56 is a wrapped second line.
  const scrollHeight = input.value ? input.scrollHeight : 0;
  composerGrid.dataset.expanded = String(scrollHeight > 56);
  if (input.value) input.style.height = `${Math.min(scrollHeight, 180)}px`;
  input.classList.toggle("capped", scrollHeight > 180);
  send.disabled = streaming || (!input.value.trim() && !attachments.length);
}

function renderChips() {
  chips.innerHTML = attachments.map(
    (file, index) => `<span class="attachment-chip">${esc(file.name)}<button type="button" data-remove="${index}" aria-label="Remove ${esc(file.name)}">×</button></span>`,
  ).join("");
}

function addFiles(files) {
  for (const file of files) {
    if (!attachments.some((item) => item.name === file.name && item.size === file.size)) attachments.push(file);
  }
  renderChips();
  resize();
}

function emptyState() {
  if (activeAutomation) {
    return `<div class="empty-state"><h1>${esc(activeAutomation.name)}</h1><div>Run it here or continue its conversation.</div></div>`;
  }
  if (chatEndpoint === "life") {
    return "<div class=\"empty-state\"><h1>What’s on your mind?</h1><div>Ask about your board or anything else — I can search the web and dig into things for you.</div></div>";
  }
  return "<div class=\"empty-state\"><h1>What should I remember?</h1><div>Talk naturally — I’ll write it down and keep the defaults clear.</div></div>";
}

/* The chat surface is a window of the newest PAGE messages; older history
   loads 30 at a time from the top without moving what's on screen. */
function syncLoadMore() {
  const existing = transcript.querySelector(".load-more-row");
  if (nextBefore > 0 && !existing) {
    const row = document.createElement("div");
    row.className = "load-more-row";
    const button = document.createElement("button");
    button.type = "button";
    button.className = "load-more";
    button.textContent = "Load earlier messages";
    button.addEventListener("click", loadEarlier);
    row.append(button);
    transcript.prepend(row);
  } else if (nextBefore <= 0 && existing) {
    existing.remove();
  }
}

async function loadEarlier() {
  const button = transcript.querySelector(".load-more");
  if (!button || button.disabled || !channelId) return;
  button.disabled = true;
  try {
    const data = await apiJSON(
      `/api/channels/${encodeURIComponent(channelId)}?limit=${PAGE}&before=${nextBefore}`,
    );
    nextBefore = data.start || 0;
    const anchor = transcript.querySelector(".load-more-row");
    const previousHeight = transcript.scrollHeight;
    const rows = (data.messages || []).map((message) => buildMessage(message.role, message.content).row);
    anchor.after(...rows);
    syncLoadMore();
    transcript.scrollTop += transcript.scrollHeight - previousHeight;
  } catch (error) {
    addMessage("assistant", `Error: ${error.message}`);
  } finally {
    const remaining = transcript.querySelector(".load-more");
    if (remaining) remaining.disabled = false;
  }
}

async function loadChannel(id) {
  channelId = id;
  const data = await apiJSON(`/api/channels/${encodeURIComponent(id)}?limit=${PAGE}`);
  transcript.replaceChildren();
  nextBefore = data.start || 0;
  for (const message of data.messages || []) addMessage(message.role, message.content);
  if (!(data.messages || []).length) {
    transcript.innerHTML = emptyState();
  } else {
    syncLoadMore();
    bottom();
  }
}

async function ensureChannel(storageKey) {
  let id = localStorage.getItem(storageKey);
  if (!id) {
    const created = await apiJSON("/api/channels/init", { method: "POST" });
    id = created.channel_id;
    localStorage.setItem(storageKey, id);
  }
  return id;
}

function setActiveNav(target) {
  for (const link of document.querySelectorAll(".product-nav a")) link.classList.remove("active");
  target?.classList.add("active");
}

async function showTaskChat() {
  activeAutomation = null;
  chatEndpoint = "chat";
  surfaceHeader.hidden = true;
  setActiveNav(taskNav);
  await loadChannel(await ensureChannel(TASK_CHANNEL_KEY));
  input.focus();
}

async function showLifeChat() {
  activeAutomation = null;
  chatEndpoint = "life";
  surfaceHeader.hidden = true;
  setActiveNav(lifeNav);
  await loadChannel(await ensureChannel(LIFE_CHANNEL_KEY));
  input.focus();
}

async function showAutomation(automation, link) {
  activeAutomation = automation;
  chatEndpoint = "chat";
  surfaceTitle.textContent = automation.name;
  surfaceSchedule.textContent = automation.schedule;
  runNow.setAttribute("aria-label", `Run ${automation.name} now`);
  surfaceHeader.hidden = false;
  setActiveNav(link);
  await loadChannel(automation.channel_id);
  input.focus();
}

async function route() {
  if (location.hash === "#life-chat") return showLifeChat();
  const match = location.hash.match(/^#automation\/(.+)$/);
  if (match) {
    const automation = automations.find((item) => item.id === decodeURIComponent(match[1]));
    const link = [...document.querySelectorAll(".nav-automation")].find(
      (item) => item.dataset.automationId === automation?.id,
    );
    if (automation) return showAutomation(automation, link);
  }
  return showTaskChat();
}

async function loadAutomations() {
  const data = await apiJSON("/api/automations");
  automations = data.automations || [];
  automationNav.replaceChildren();
  for (const automation of automations) {
    const link = document.createElement("a");
    link.className = "nav-automation";
    link.href = `#automation/${encodeURIComponent(automation.id)}`;
    link.dataset.automationId = automation.id;
    link.textContent = automation.name;
    automationNav.append(link);
  }
}

async function sendMessage() {
  if (streaming || !channelId) return;
  const text = input.value.trim();
  if (!text && !attachments.length) return;
  streaming = true;
  send.disabled = true;
  $(".empty-state")?.remove();
  const submitted = text || "Attached files";
  addMessage("user", submitted, null, { animate: true });
  input.value = "";
  resize();

  const row = document.createElement("div");
  row.className = "message-row assistant entering";
  const parent = assistantStack(row);
  const bubble = document.createElement("div");
  bubble.className = "message-bubble markdown";
  parent.append(bubble);
  transcript.append(row);
  const bar = document.createElement("div");
  bar.className = "working-bar";
  bar.innerHTML = "<span class=\"ball\"></span><span>Working</span>";
  transcript.append(bar);
  bottom();

  let full = "";
  try {
    const response = await fetch(`/api/channels/${encodeURIComponent(channelId)}/${chatEndpoint}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        message: submitted,
        attachments: attachments.map((file) => ({ name: file.name, type: file.type, size: file.size })),
      }),
    });
    if (!response.ok || !response.body) throw new Error(`${response.status} ${response.statusText}`);
    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    for (;;) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      let cut;
      while ((cut = buffer.indexOf("\n\n")) >= 0) {
        const block = buffer.slice(0, cut);
        buffer = buffer.slice(cut + 2);
        const line = block.split("\n").find((item) => item.startsWith("data:"));
        if (!line) continue;
        const data = JSON.parse(line.slice(5));
        if (data.text) full += data.text;
        if (data.error) full += `\n\n${data.error}`;
        if (data.controls) renderPlanControls(parent, data.controls);
        bubble.innerHTML = markdown(full);
        bottom();
      }
    }
  } catch (error) {
    bubble.textContent = `Error: ${error.message}`;
  }
  bar.classList.add("complete");
  window.setTimeout(() => bar.remove(), 320);
  attachments = [];
  renderChips();
  streaming = false;
  resize();
  input.focus();
}

runNow.addEventListener("click", async () => {
  if (!activeAutomation) return;
  runNow.disabled = true;
  try {
    const result = await apiJSON(`/api/automations/${encodeURIComponent(activeAutomation.id)}/run`, { method: "POST" });
    await loadChannel(activeAutomation.channel_id);
    if (result.controls) {
      const parent = [...transcript.querySelectorAll(".assistant-stack")].at(-1);
      if (parent) renderPlanControls(parent, result.controls);
    }
  } catch (error) {
    addMessage("assistant", `Error: ${error.message}`);
  } finally {
    runNow.disabled = false;
    runNow.focus();
  }
});

$("#attach").addEventListener("click", () => $("#file-input").click());
$("#file-input").addEventListener("change", (event) => addFiles(event.target.files));
chips.addEventListener("click", (event) => {
  const button = event.target.closest("[data-remove]");
  if (!button) return;
  attachments.splice(Number(button.dataset.remove), 1);
  renderChips();
  resize();
});
input.addEventListener("input", resize);
input.addEventListener("keydown", (event) => {
  if (event.key === "Enter" && !event.shiftKey) {
    event.preventDefault();
    if (input.value.trim() || attachments.length) sendMessage();
  }
});
send.addEventListener("click", sendMessage);
input.addEventListener("paste", (event) => {
  const files = [...(event.clipboardData?.files || [])];
  if (files.length) {
    event.preventDefault();
    addFiles(files);
  }
});
document.addEventListener("dragover", (event) => event.preventDefault());
document.addEventListener("drop", (event) => {
  event.preventDefault();
  addFiles(event.dataTransfer.files);
});
$("#theme").addEventListener("click", () => {
  const next = document.documentElement.dataset.theme === "dark" ? "light" : "dark";
  document.documentElement.dataset.theme = next;
  localStorage.setItem("agentonomy-theme", next);
});
taskNav.addEventListener("click", () => {
  if (location.hash === "#task-chat") route();
});
lifeNav.addEventListener("click", () => {
  if (location.hash === "#life-chat") route();
});
window.addEventListener("hashchange", () => route().catch(showLoadError));

function showLoadError(error) {
  console.error(error);
  transcript.innerHTML = "<div class=\"empty-state\">Unable to load this chat.</div>";
}

(async () => {
  try {
    await loadAutomations();
    await route();
  } catch (error) {
    showLoadError(error);
  }
  resize();
})();
