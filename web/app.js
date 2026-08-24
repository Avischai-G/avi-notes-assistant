const $ = (selector) => document.querySelector(selector);
const transcript = $("#transcript");
const input = $("#input");
const send = $("#send");
const chips = $("#attachment-chips");
const drawer = $("#drawer");
const chatPane = $("#chat-pane");
const settingsPane = $("#settings-pane");
const automationChannels = $("#automation-channels");
const automationEditors = $("#automation-editors");
const systemPrompt = $("#system-prompt");
const toast = $("#toast");
const composerGrid = $("#composer-grid");
const TASK_CHANNEL_KEY = "avi-notes-task-channel";
const PAGE = 30;
const MAX_ATTACHMENT_BYTES = 15 * 1024 * 1024;

let channelId = null;
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
    const isImage = file.type.startsWith("image/");
    const isPdf = file.type === "application/pdf";
    if (!isImage && !isPdf) continue;
    const total = attachments.reduce((sum, item) => sum + item.size, 0);
    if (total + file.size > MAX_ATTACHMENT_BYTES) {
      addMessage("assistant", `“${file.name}” would push attachments past 15 MB — send it separately.`);
      continue;
    }
    if (!attachments.some((item) => item.name === file.name && item.size === file.size)) attachments.push(file);
  }
  renderChips();
  resize();
}

function readAsBase64(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result).split(",", 2)[1] || "");
    reader.onerror = () => reject(reader.error);
    reader.readAsDataURL(file);
  });
}

function emptyState() {
  if (activeAutomation) {
    return `<div class="empty-state"><h1>${esc(activeAutomation.name)}</h1><div>${esc(activeAutomation.schedule)} — run it from the channels menu, or just talk to it here.</div></div>`;
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

function setActiveChannel(href) {
  for (const link of drawer.querySelectorAll(".channel")) {
    link.classList.toggle("active", link.getAttribute("href") === href);
  }
}

async function showChat(automation) {
  activeAutomation = automation || null;
  settingsPane.hidden = true;
  chatPane.hidden = false;
  setActiveChannel(automation ? `#automation/${encodeURIComponent(automation.id)}` : "#chat");
  await loadChannel(automation ? automation.channel_id : await ensureChannel(TASK_CHANNEL_KEY));
  if (!drawer.open) input.focus();
}

async function showSettings() {
  activeAutomation = null;
  chatPane.hidden = true;
  settingsPane.hidden = false;
  setActiveChannel("#settings");
  const data = await apiJSON("/api/settings");
  systemPrompt.value = data.system_prompt || "";
  renderAutomationEditors();
}

async function route() {
  if (location.hash === "#settings") return showSettings();
  const match = location.hash.match(/^#automation\/(.+)$/);
  const automation = match
    && automations.find((item) => item.id === decodeURIComponent(match[1]));
  return showChat(automation || null);
}

/* ── Channels drawer ─────────────────────────────────────────────────── */
const CLOCK_ICON = '<svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/></svg>';
const PLAY_ICON = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="m8 5 11 7-11 7Z"/></svg>';

function renderChannels() {
  automationChannels.replaceChildren();
  for (const automation of automations) {
    const row = document.createElement("div");
    row.className = "channel-row";
    const link = document.createElement("a");
    link.className = "channel";
    link.href = `#automation/${encodeURIComponent(automation.id)}`;
    link.innerHTML = `${CLOCK_ICON}<span>${esc(automation.name)}</span>`;
    const run = document.createElement("button");
    run.type = "button";
    run.className = "icon-button";
    run.dataset.run = automation.id;
    run.setAttribute("aria-label", `Run ${automation.name} now`);
    run.innerHTML = PLAY_ICON;
    row.append(link, run);
    automationChannels.append(row);
  }
  setActiveChannel(location.hash || "#chat");
}

async function loadAutomations() {
  const data = await apiJSON("/api/automations");
  automations = data.automations || [];
  renderChannels();
}

function openDrawer() {
  drawer.showModal();
}

drawer.addEventListener("click", (event) => {
  // A modal <dialog> fills the viewport for hit-testing; only the sheet is the sheet.
  const inside = event.target.closest(".channels, .drawer-foot");
  if (!inside) drawer.close();
  else if (event.target.closest(".channel")) drawer.close();
});

drawer.addEventListener("click", async (event) => {
  const button = event.target.closest("[data-run]");
  if (!button) return;
  const automation = automations.find((item) => item.id === button.dataset.run);
  if (!automation) return;
  button.disabled = true;
  drawer.close();
  location.hash = `#automation/${encodeURIComponent(automation.id)}`;
  try {
    const result = await apiJSON(
      `/api/automations/${encodeURIComponent(automation.id)}/run`,
      { method: "POST" },
    );
    await loadChannel(automation.channel_id);
    if (result.controls) {
      const parent = [...transcript.querySelectorAll(".assistant-stack")].at(-1);
      if (parent) renderPlanControls(parent, result.controls);
    }
  } catch (error) {
    addMessage("assistant", `Error: ${error.message}`);
  } finally {
    button.disabled = false;
  }
});

$("#menu").addEventListener("click", openDrawer);

/* ── Settings: the chat prompt, and one prompt + trigger per automation ─ */
let toastTimer = 0;

function flash(message) {
  toast.textContent = message;
  toast.classList.add("show");
  window.clearTimeout(toastTimer);
  toastTimer = window.setTimeout(() => toast.classList.remove("show"), 1600);
}

function renderAutomationEditors() {
  automationEditors.replaceChildren();
  for (const automation of automations) {
    const card = document.createElement("article");
    card.className = "automation-card";
    card.dataset.id = automation.id;
    card.innerHTML = `
      <div class="card-head">
        <input class="field" data-field="name" value="${esc(automation.name)}" aria-label="Automation name">
        ${automation.built_in ? "" : `<button class="icon-button" type="button" data-delete="${esc(automation.id)}" aria-label="Delete ${esc(automation.name)}"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M3 6h18M8 6V4h8v2m-11 0 1 14h12l1-14"/></svg></button>`}
      </div>
      <label for="prompt-${esc(automation.id)}">Prompt</label>
      <textarea class="field custom-scrollbar" id="prompt-${esc(automation.id)}" data-field="prompt" rows="4" placeholder="What should it do?">${esc(automation.prompt || "")}</textarea>
      <label for="trigger-${esc(automation.id)}">Trigger</label>
      <input class="field" id="trigger-${esc(automation.id)}" data-field="schedule" value="${esc(automation.schedule || "")}" placeholder="daily at 21:00">`;
    automationEditors.append(card);
  }
}

systemPrompt.addEventListener("change", async () => {
  const prompt = systemPrompt.value.trim();
  if (!prompt) return flash("Instructions can't be empty");
  try {
    await apiJSON("/api/settings", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ system_prompt: prompt }),
    });
    flash("Saved");
  } catch (error) {
    flash(`Not saved: ${error.message}`);
  }
});

automationEditors.addEventListener("change", async (event) => {
  const field = event.target.closest("[data-field]");
  const card = field?.closest(".automation-card");
  if (!card) return;
  try {
    const saved = await apiJSON(`/api/automations/${encodeURIComponent(card.dataset.id)}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ [field.dataset.field]: field.value }),
    });
    automations = automations.map((item) => (item.id === saved.id ? saved : item));
    renderChannels();
    flash("Saved");
  } catch (error) {
    flash(`Not saved: ${error.message}`);
  }
});

automationEditors.addEventListener("click", async (event) => {
  const button = event.target.closest("[data-delete]");
  if (!button) return;
  button.disabled = true;
  try {
    await apiJSON(`/api/automations/${encodeURIComponent(button.dataset.delete)}`, { method: "DELETE" });
    await loadAutomations();
    renderAutomationEditors();
    flash("Deleted");
  } catch (error) {
    button.disabled = false;
    flash(`Not deleted: ${error.message}`);
  }
});

$("#add-automation").addEventListener("click", async () => {
  try {
    await apiJSON("/api/automations", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name: "New automation", prompt: "", schedule: "daily at 09:00" }),
    });
    await loadAutomations();
    renderAutomationEditors();
    automationEditors.querySelector(".automation-card:last-child .field")?.focus();
  } catch (error) {
    flash(`Not created: ${error.message}`);
  }
});

/* ── Theme: one control, three modes ─────────────────────────────────── */
const MODES = ["system", "light", "dark"];
const MODE_LABEL = { system: "follow system", light: "light", dark: "dark" };
const systemDark = matchMedia("(prefers-color-scheme: dark)");

function applyTheme(mode) {
  document.documentElement.dataset.themeMode = mode;
  document.documentElement.dataset.theme =
    mode === "system" ? (systemDark.matches ? "dark" : "light") : mode;
  $("#theme").setAttribute("aria-label", `Theme: ${MODE_LABEL[mode]}`);
  localStorage.setItem("agentonomy-theme", mode);
}

$("#theme").addEventListener("click", () => {
  const current = document.documentElement.dataset.themeMode || "system";
  applyTheme(MODES[(MODES.indexOf(current) + 1) % MODES.length]);
});
systemDark.addEventListener("change", () => {
  if (document.documentElement.dataset.themeMode === "system") applyTheme("system");
});

async function sendMessage() {
  if (streaming || !channelId) return;
  const text = input.value.trim();
  if (!text && !attachments.length) return;
  streaming = true;
  send.disabled = true;
  $(".empty-state")?.remove();
  let submitted = text || "Attached files";
  if (attachments.length) {
    submitted += `\n[Attached: ${attachments.map((file) => file.name).join(", ")}]`;
  }
  addMessage("user", submitted, null, { animate: true });
  input.value = "";
  resize();

  let filePayloads = [];
  try {
    filePayloads = await Promise.all(attachments.map(async (file) => ({
      name: file.name,
      type: file.type,
      data: await readAsBase64(file),
    })));
  } catch (error) {
    addMessage("assistant", `Could not read an attachment: ${error.message}`);
  }

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
    const response = await fetch(`/api/channels/${encodeURIComponent(channelId)}/chat`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        message: submitted,
        attachments: filePayloads,
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
/* Live voice session: transcripts stream into the home chat while the rest
   of the app stays fully usable. */
const liveToggle = $("#live-toggle");
let liveChannelId = null;
let liveUserBubble = null;
let liveAgentBubble = null;

function liveText(role, delta, replace = false) {
  if (channelId !== liveChannelId) return; // server persists it either way
  $(".empty-state")?.remove();
  let bubble = role === "user" ? liveUserBubble : liveAgentBubble;
  if (!bubble || !bubble.isConnected) {
    const built = buildMessage(role, "");
    built.row.classList.add("entering");
    transcript.append(built.row);
    bubble = built.bubble;
    bubble.dataset.liveText = "";
    if (role === "user") liveUserBubble = bubble;
    else liveAgentBubble = bubble;
  }
  // A finished transcription replaces the streamed deltas outright.
  bubble.dataset.liveText = replace ? delta : bubble.dataset.liveText + delta;
  if (role === "user") bubble.textContent = bubble.dataset.liveText;
  else bubble.innerHTML = markdown(bubble.dataset.liveText);
  bottom();
}

liveToggle.addEventListener("click", async () => {
  if (window.LiveSession.active) {
    window.LiveSession.stop();
    return;
  }
  liveToggle.disabled = true;
  try {
    liveChannelId = await ensureChannel(TASK_CHANNEL_KEY);
    await window.LiveSession.start(liveChannelId, {
      onUserText: (text, replace) => liveText("user", text, replace),
      onAgentText: (text, replace) => liveText("assistant", text, replace),
      onTurnComplete: () => { liveUserBubble = null; liveAgentBubble = null; },
      onInterrupted: () => { liveAgentBubble = null; },
      onError: (message) => addMessage("assistant", `Live error: ${message}`),
      onState: (on) => {
        liveToggle.classList.toggle("active", on);
        liveToggle.setAttribute(
          "aria-label",
          on ? "End live conversation" : "Start live conversation",
        );
        if (!on) { liveUserBubble = null; liveAgentBubble = null; }
      },
    });
  } catch (error) {
    addMessage("assistant", `Live error: ${error.message}`);
  } finally {
    liveToggle.disabled = false;
  }
});
window.addEventListener("hashchange", () => route().catch(showLoadError));

function showLoadError(error) {
  console.error(error);
  transcript.innerHTML = "<div class=\"empty-state\">Unable to load this chat.</div>";
  chatPane.hidden = false;
  settingsPane.hidden = true;
}

applyTheme(localStorage.getItem("agentonomy-theme") || "system");

(async () => {
  try {
    await loadAutomations();
    await route();
  } catch (error) {
    showLoadError(error);
  }
  resize();
})();
