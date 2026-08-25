const $ = (selector) => document.querySelector(selector);
const transcript = $("#transcript");
const input = $("#input");
const send = $("#send");
const chips = $("#attachment-chips");
const drawer = $("#drawer");
const editor = $("#editor");
const automationChannels = $("#automation-channels");
const toast = $("#toast");
const TASK_CHANNEL_KEY = "avi-notes-task-channel";
const JSON_HEADERS = { "Content-Type": "application/json" };
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
  // Only the text box grows, and it grows upward: attach, mic and send stay
  // pinned to the bottom corners however many lines are typed.
  input.style.height = "";
  const scrollHeight = input.value ? input.scrollHeight : 0;
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
    return `<div class="empty-state"><h1>${esc(activeAutomation.name)}</h1><div>${esc(activeAutomation.schedule)} — run or edit it from its ⋯ menu, or just talk to it here.</div></div>`;
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
  setActiveChannel(automation ? `#automation/${encodeURIComponent(automation.id)}` : "#chat");
  await loadChannel(automation ? automation.channel_id : await ensureChannel(TASK_CHANNEL_KEY));
  if (!drawer.open) input.focus();
}

async function route() {
  const match = location.hash.match(/^#automation\/(.+)$/);
  const automation = match
    && automations.find((item) => item.id === decodeURIComponent(match[1]));
  return showChat(automation || null);
}

/* ── Channels drawer ─────────────────────────────────────────────────── */
const CLOCK_ICON = '<svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/></svg>';
const DOTS_ICON = '<svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="5" cy="12" r="1.4"/><circle cx="12" cy="12" r="1.4"/><circle cx="19" cy="12" r="1.4"/></svg>';

function renderChannels() {
  automationChannels.replaceChildren();
  for (const automation of automations) {
    const id = esc(automation.id);
    const row = document.createElement("div");
    row.className = "channel-row";
    row.innerHTML = `<a class="channel" href="#automation/${encodeURIComponent(automation.id)}">`
      + `${CLOCK_ICON}<span>${esc(automation.name)}</span></a>`
      + `<button class="icon-button dots" type="button" data-menu="${id}" aria-expanded="false"`
      + ` aria-label="${esc(automation.name)} options">${DOTS_ICON}</button>`;
    const menu = document.createElement("div");
    menu.className = "row-menu";
    menu.dataset.menuFor = automation.id;
    menu.hidden = true;
    menu.innerHTML = `<button type="button" data-action="run" data-id="${id}">Run now</button>`
      + `<button type="button" data-action="edit" data-id="${id}">Edit</button>`
      + (automation.built_in ? "" : `<button type="button" data-action="delete" data-id="${id}">Delete</button>`);
    automationChannels.append(row, menu);
  }
  setActiveChannel(location.hash || "#chat");
}

async function loadAutomations() {
  const data = await apiJSON("/api/automations");
  automations = data.automations || [];
  renderChannels();
}

/* At most one row menu is open, and opening the drawer starts with none. */
function toggleMenu(id) {
  for (const menu of drawer.querySelectorAll(".row-menu")) {
    menu.hidden = !(menu.dataset.menuFor === id && menu.hidden);
  }
  for (const dots of drawer.querySelectorAll(".dots")) {
    const menu = drawer.querySelector(`.row-menu[data-menu-for="${dots.dataset.menu}"]`);
    dots.setAttribute("aria-expanded", String(Boolean(menu) && !menu.hidden));
  }
}

$("#menu").addEventListener("click", () => {
  toggleMenu(null);
  drawer.showModal();
});

drawer.addEventListener("click", (event) => {
  const dots = event.target.closest(".dots");
  if (dots) return toggleMenu(dots.dataset.menu);

  const action = event.target.closest("[data-action]");
  if (action) {
    drawer.close();
    return chooseAction(action.dataset.action, action.dataset.id);
  }
  if (event.target.closest("#add-automation")) {
    drawer.close();
    return addAutomation();
  }
  if (event.target.closest(".channel")) return drawer.close();
  // A modal <dialog> fills the viewport for hit-testing; outside the list is the backdrop.
  if (!event.target.closest(".channels")) drawer.close();
});

function chooseAction(action, id) {
  if (action === "edit-chat") return openChatEditor();
  const automation = automations.find((item) => item.id === id);
  if (!automation) return undefined;
  if (action === "edit") return openAutomationEditor(automation);
  if (action === "delete") return deleteAutomation(automation);
  return runAutomation(automation);
}

async function runAutomation(automation) {
  try {
    const result = await apiJSON(
      `/api/automations/${encodeURIComponent(automation.id)}/run`,
      { method: "POST" },
    );
    // replaceState rather than assigning the hash: hashchange would start a
    // second channel load that can land last and wipe the run's own controls.
    history.replaceState(null, "", `#automation/${encodeURIComponent(automation.id)}`);
    await showChat(automation);
    if (result.controls) {
      const parent = [...transcript.querySelectorAll(".assistant-stack")].at(-1);
      if (parent) renderPlanControls(parent, result.controls);
    }
  } catch (error) {
    addMessage("assistant", `Error: ${error.message}`);
  }
}

async function deleteAutomation(automation) {
  try {
    await apiJSON(`/api/automations/${encodeURIComponent(automation.id)}`, { method: "DELETE" });
    const wasOpen = activeAutomation?.id === automation.id;
    await loadAutomations();
    if (wasOpen) location.hash = "#chat";
    flash("Deleted");
  } catch (error) {
    flash(`Not deleted: ${error.message}`);
  }
}

async function addAutomation() {
  try {
    await apiJSON("/api/automations", {
      method: "POST",
      headers: JSON_HEADERS,
      body: JSON.stringify({ name: "New automation", prompt: "", frequency: "daily", hour: 9, minute: 0 }),
    });
    await loadAutomations();
    openAutomationEditor(automations.at(-1));
  } catch (error) {
    flash(`Not created: ${error.message}`);
  }
}

/* ── Editor: the one place a prompt or a trigger changes ─────────────── */
const editorTitle = $("#editor-title");
const editorName = $("#editor-name");
const editorPrompt = $("#editor-prompt");
const editorPromptLabel = $("#editor-prompt-label");
const editorTrigger = $("#editor-trigger");
const editorFrequency = $("#editor-frequency");
const editorWeekday = $("#editor-weekday");
const editorTime = $("#editor-time");
const editorMinute = $("#editor-minute");
const editorNext = $("#editor-next");
const editorDelete = $("#editor-delete");
let editing = null; // null while editing the chat's own instructions
let toastTimer = 0;

editorMinute.replaceChildren(...Array.from({ length: 12 }, (_, index) => {
  const option = document.createElement("option");
  option.value = String(index * 5);
  option.textContent = `:${String(index * 5).padStart(2, "0")}`;
  return option;
}));

function flash(message) {
  toast.textContent = message;
  toast.classList.add("show");
  window.clearTimeout(toastTimer);
  toastTimer = window.setTimeout(() => toast.classList.remove("show"), 1600);
}

const twoDigits = (value) => String(value ?? 0).padStart(2, "0");

async function openChatEditor() {
  editing = null;
  editor.dataset.kind = "chat";
  editorTitle.textContent = "Chat instructions";
  editorPromptLabel.textContent = "How the assistant behaves";
  editorPrompt.value = "";
  editor.showModal();
  try {
    editorPrompt.value = (await apiJSON("/api/settings")).system_prompt || "";
  } catch (error) {
    flash(`Could not load: ${error.message}`);
  }
}

function openAutomationEditor(automation) {
  if (!automation) return;
  editing = automation;
  editor.dataset.kind = "automation";
  editorTitle.textContent = automation.name;
  editorPromptLabel.textContent = "Prompt";
  editorName.value = automation.name;
  editorPrompt.value = automation.prompt || "";
  editorFrequency.value = automation.frequency || "daily";
  editorWeekday.value = String(automation.weekday ?? 0);
  editorTime.value = `${twoDigits(automation.hour ?? 9)}:${twoDigits(automation.minute)}`;
  editorMinute.value = String(automation.minute ?? 0);
  editorDelete.hidden = Boolean(automation.built_in);
  editorTrigger.dataset.frequency = editorFrequency.value;
  editorNext.textContent = automation.schedule || "";
  editor.showModal();
}

function triggerFromForm() {
  const frequency = editorFrequency.value;
  if (frequency === "hourly") return { frequency, minute: Number(editorMinute.value) };
  const [hour, minute] = (editorTime.value || "09:00").split(":").map(Number);
  return frequency === "weekly"
    ? { frequency, hour, minute, weekday: Number(editorWeekday.value) }
    : { frequency, hour, minute };
}

async function saveEditor() {
  if (!editing) {
    const prompt = editorPrompt.value.trim();
    if (!prompt) return flash("Instructions can't be empty");
    try {
      await apiJSON("/api/settings", {
        method: "PUT",
        headers: JSON_HEADERS,
        body: JSON.stringify({ system_prompt: prompt }),
      });
      return flash("Saved");
    } catch (error) {
      return flash(`Not saved: ${error.message}`);
    }
  }
  try {
    const saved = await apiJSON(`/api/automations/${encodeURIComponent(editing.id)}`, {
      method: "PATCH",
      headers: JSON_HEADERS,
      body: JSON.stringify({
        name: editorName.value.trim() || editing.name,
        prompt: editorPrompt.value,
        ...triggerFromForm(),
      }),
    });
    editing = saved;
    automations = automations.map((item) => (item.id === saved.id ? saved : item));
    if (activeAutomation?.id === saved.id) activeAutomation = saved;
    editorTitle.textContent = saved.name;
    editorNext.textContent = saved.schedule;
    renderChannels();
    return flash("Saved");
  } catch (error) {
    return flash(`Not saved: ${error.message}`);
  }
}

editor.addEventListener("change", () => {
  editorTrigger.dataset.frequency = editorFrequency.value;
  saveEditor();
});

editorDelete.addEventListener("click", () => {
  const target = editing;
  editor.close();
  if (target) deleteAutomation(target);
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
