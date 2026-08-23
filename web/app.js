const $ = (selector) => document.querySelector(selector);
const transcript = $("#transcript");
const input = $("#input");
const send = $("#send");
const chips = $("#attachment-chips");
const taskNav = $("#nav-task-chat");
const automationNav = $("#automation-nav");
const surfaceHeader = $("#surface-header");
const surfaceTitle = $("#surface-title");
const surfaceSchedule = $("#surface-schedule");
const runNow = $("#run-now");
const composerGrid = $("#composer-grid");
const TASK_CHANNEL_KEY = "avi-notes-task-channel";

let channelId = null;
let attachments = [];
let streaming = false;
let automations = [];
let activeAutomation = null;

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
  return html.split(/\n\n+/).map((paragraph) => `<p>${paragraph.replace(/\n/g, "<br>")}</p>`).join("");
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

function addMessage(role, content, controls = null) {
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
  transcript.append(row);
  if (controls) renderPlanControls(parent, controls);
  bottom();
  return { row, bubble, parent };
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
        addMessage("assistant", data.text);
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
  input.style.height = "auto";
  const scrollHeight = input.scrollHeight;
  composerGrid.dataset.expanded = String(scrollHeight > 48);
  input.style.height = `${Math.min(scrollHeight, 180)}px`;
  input.classList.toggle("capped", input.scrollHeight > 180);
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
  return "<div class=\"empty-state\"><h1>What should I remember?</h1><div>Talk naturally — I’ll write it down and keep the defaults clear.</div></div>";
}

async function loadChannel(id) {
  channelId = id;
  const data = await apiJSON(`/api/channels/${encodeURIComponent(id)}`);
  transcript.replaceChildren();
  for (const message of data.messages || []) addMessage(message.role, message.content);
  if (!data.messages?.length) transcript.innerHTML = emptyState();
}

async function taskChannel() {
  let id = localStorage.getItem(TASK_CHANNEL_KEY);
  if (!id) {
    const created = await apiJSON("/api/channels/init", { method: "POST" });
    id = created.channel_id;
    localStorage.setItem(TASK_CHANNEL_KEY, id);
  }
  return id;
}

function setActiveNav(target) {
  for (const link of document.querySelectorAll(".product-nav a")) link.classList.remove("active");
  target?.classList.add("active");
}

async function showTaskChat() {
  activeAutomation = null;
  surfaceHeader.hidden = true;
  setActiveNav(taskNav);
  await loadChannel(await taskChannel());
  input.focus();
}

async function showAutomation(automation, link) {
  activeAutomation = automation;
  surfaceTitle.textContent = automation.name;
  surfaceSchedule.textContent = automation.schedule;
  runNow.setAttribute("aria-label", `Run ${automation.name} now`);
  surfaceHeader.hidden = false;
  setActiveNav(link);
  await loadChannel(automation.channel_id);
  input.focus();
}

async function route() {
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
  addMessage("user", submitted);
  input.value = "";
  resize();

  const row = document.createElement("div");
  row.className = "message-row assistant";
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
    const response = await fetch(`/api/channels/${encodeURIComponent(channelId)}/chat`, {
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
