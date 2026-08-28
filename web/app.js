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
const DEVICE_TIMEZONE = Intl.DateTimeFormat().resolvedOptions().timeZone;
const WEEKDAY_NAMES = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"];
const pad2 = (value) => String(value ?? 0).padStart(2, "0");

// A schedule set in another timezone displays in this device's clock,
// derived from its next real firing so DST can never make it lie.
function localTrigger(automation) {
  if (!automation.next_run_at || !automation.timezone
      || automation.timezone === DEVICE_TIMEZONE) return null;
  const next = new Date(automation.next_run_at * 1000);
  return {
    hour: next.getHours(),
    minute: next.getMinutes(),
    weekday: (next.getDay() + 6) % 7,
  };
}

// Under a converted time, one quiet line says where the schedule was set.
function scheduleOrigin(automation) {
  return localTrigger(automation)
    ? `Set as ${automation.schedule} in ${automation.timezone}`
    : "";
}

function scheduleLabel(automation) {
  const local = localTrigger(automation);
  if (!local) return automation.schedule || "";
  if (automation.frequency === "hourly") return `Hourly at :${pad2(local.minute)}`;
  const time = `${pad2(local.hour)}:${pad2(local.minute)}`;
  if (automation.frequency === "weekly") {
    return `Weekly on ${WEEKDAY_NAMES[local.weekday]} at ${time}`;
  }
  return `Daily at ${time}`;
}
// The Gemini API key lives ONLY in this device's local storage: it rides each
// request as a header, is never written server-side, and is never displayed.
const GEMINI_KEY_STORAGE = "agentonomy-gemini-key";
const deviceKey = () => localStorage.getItem(GEMINI_KEY_STORAGE) || "";
const GEMINI_MODEL_STORAGE = "agentonomy-gemini-model";
const deviceModel = () => localStorage.getItem(GEMINI_MODEL_STORAGE) || "";
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

const CLIP_PATH = "m21.44 11.05-9.19 9.19a6 6 0 0 1-8.49-8.49l9.19-9.19a4 4 0 0 1 5.66 5.66l-9.2 9.19a2 2 0 0 1-2.82-2.83l8.49-8.48";

function attachmentChips(names) {
  const rowEl = document.createElement("div");
  rowEl.className = "bubble-attachments";
  for (const name of names) {
    const chip = document.createElement("span");
    chip.className = "bubble-attachment";
    chip.innerHTML = `<svg viewBox="0 0 24 24" aria-hidden="true"><path d="${CLIP_PATH}"/></svg>`;
    const label = document.createElement("span");
    label.textContent = name;
    chip.append(label);
    rowEl.append(chip);
  }
  return rowEl;
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
    // A sent file shows as a small chip above the words, not as bracket text.
    const attached = content.match(/\n?\[Attached: ([^\]]+)\]\s*$/);
    if (attached) {
      bubble.append(attachmentChips(attached[1].split(", ")));
      const text = content.slice(0, attached.index).trim();
      if (text) {
        const words = document.createElement("div");
        words.textContent = text;
        bubble.append(words);
      }
    } else {
      bubble.textContent = content;
    }
  }
  parent.append(bubble);
  return { row, bubble, parent };
}

function addMessage(role, content, { animate = false } = {}) {
  const built = buildMessage(role, content);
  if (animate) built.row.classList.add("entering");
  transcript.append(built.row);
  bottom();
  return built;
}

async function apiJSON(url, options = {}) {
  const response = await fetch(url, options);
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(data.detail || `${response.status} ${response.statusText}`);
  return data;
}

function resize() {
  // Up to three lines the text sits between the buttons; past that it takes
  // the full width above them and stays there until the text is back down
  // to a single line. The line count is always measured at the narrow
  // width, so widening the box can never flip the layout by itself.
  const grid = $("#composer-grid");
  const wasTall = grid.classList.contains("tall");
  input.style.height = "";
  grid.classList.remove("tall");
  const styles = getComputedStyle(input);
  const padding = parseFloat(styles.paddingTop) + parseFloat(styles.paddingBottom);
  const lines = input.value
    ? Math.round((input.scrollHeight - padding) / parseFloat(styles.lineHeight))
    : 1;
  grid.classList.toggle("tall", wasTall ? lines > 1 : lines > 3);
  const scrollHeight = input.value ? input.scrollHeight : 0;
  if (input.value) input.style.height = `${Math.min(scrollHeight, 180)}px`;
  input.classList.toggle("capped", scrollHeight > 180);
  send.disabled = streaming || (!input.value.trim() && !attachments.length);
}

function renderChips() {
  chips.innerHTML = attachments.map(
    (file, index) => `<span class="attachment-chip">`
      + `<svg viewBox="0 0 24 24" aria-hidden="true"><path d="${CLIP_PATH}"/></svg>`
      + `<span class="attachment-name">${esc(file.name)}</span>`
      + `<button type="button" data-remove="${index}" aria-label="Remove ${esc(file.name)}">×</button></span>`,
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
    const origin = scheduleOrigin(activeAutomation);
  return `<div class="empty-state"><h1>${esc(activeAutomation.name)}</h1><div>${esc(scheduleLabel(activeAutomation))} — run or edit it from its ⋯ menu, or just talk to it here.</div>${origin ? `<div class="schedule-origin">${esc(origin)}</div>` : ""}</div>`;
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
  document.body.classList.toggle("automation-view", Boolean(automation));
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
      + `<button type="button" data-action="delete" data-id="${id}">Delete</button>`;
    automationChannels.append(row, menu);
  }
  setActiveChannel(location.hash || "#chat");
}

async function loadAutomations() {
  const data = await apiJSON("/api/automations");
  automations = data.automations || [];
  renderChannels();
}

/* At most one row menu is open, and opening the drawer starts with none.
   An open menu floats beside its ⋯ button, so it takes the button's offset. */
function toggleMenu(id, dots) {
  for (const menu of drawer.querySelectorAll(".row-menu")) {
    menu.hidden = !(menu.dataset.menuFor === id && menu.hidden);
    if (!menu.hidden && dots) {
      menu.style.top = `${dots.offsetTop + dots.offsetHeight + 4}px`;
    }
  }
  for (const dots of drawer.querySelectorAll(".dots")) {
    const menu = drawer.querySelector(`.row-menu[data-menu-for="${dots.dataset.menu}"]`);
    dots.setAttribute("aria-expanded", String(Boolean(menu) && !menu.hidden));
  }
}

/* ── The phone's back button closes the top layer, never jumps screens. ──
   Opening a drawer, dialog, or settings section arms one history entry;
   pressing back closes just that layer. Closing by button only updates the
   stack — no history juggling, so there is nothing to race. */
const uiLayers = [];
let backArmed = false;
function armBack() {
  if (backArmed) return;
  history.pushState({ uiSentinel: true }, "");
  backArmed = true;
}
function openLayer(kind, close) {
  uiLayers.push({ kind, close });
  armBack();
}
function dropLayer(kind) {
  const index = uiLayers.findLastIndex((layer) => layer.kind === kind);
  if (index !== -1) uiLayers.splice(index, 1);
}
window.addEventListener("popstate", () => {
  backArmed = false;
  const layer = uiLayers.pop();
  if (layer) {
    layer.close();
    if (uiLayers.length) armBack();
  }
});

$("#drawer-close").addEventListener("click", () => drawer.close());
$("#drawer-close-x").addEventListener("click", () => drawer.close());
$("#menu").addEventListener("click", () => {
  toggleMenu(null);
  drawer.showModal();
  openLayer("drawer", () => drawer.close());
});
drawer.addEventListener("close", () => dropLayer("drawer"));
editor.addEventListener("close", () => dropLayer("editor"));

drawer.addEventListener("click", (event) => {
  const dots = event.target.closest(".dots");
  if (dots) return toggleMenu(dots.dataset.menu, dots);
  // Clicking anywhere else closes an open ⋯ menu.
  if (!event.target.closest(".row-menu")) toggleMenu(null);

  const action = event.target.closest("[data-action]");
  if (action) {
    drawer.close();
    return chooseAction(action.dataset.action, action.dataset.id);
  }
  if (event.target.closest("#add-automation")) {
    drawer.close();
    return openNewAutomationEditor();
  }
  if (event.target.closest(".channel")) return drawer.close();
  // A modal <dialog> fills the viewport for hit-testing; outside the list is the backdrop.
  if (!event.target.closest(".channels")) drawer.close();
});

// Esc closes an open ⋯ menu first; the drawer itself on the next press.
drawer.addEventListener("cancel", (event) => {
  if (drawer.querySelector(".row-menu:not([hidden])")) {
    event.preventDefault();
    toggleMenu(null);
  }
});

function chooseAction(action, id) {
  if (action === "edit-chat") return openChatEditor();
  if (action === "clear-chat") return clearChat();
  const automation = automations.find((item) => item.id === id);
  if (!automation) return undefined;
  if (action === "edit") return openAutomationEditor(automation);
  if (action === "delete") return deleteAutomation(automation);
  return runAutomation(automation);
}

async function runAutomation(automation) {
  // The run happens in the background: the answer lands in the automation's
  // own channel without pulling the user away from where they are.
  flash(`Running ${automation.name}…`);
  try {
    const result = await apiJSON(
      `/api/automations/${encodeURIComponent(automation.id)}/run`,
      { method: "POST", headers: deviceKey() ? { "X-Gemini-Key": deviceKey() } : {} },
    );
    const answer = (result.chunks || []).join("").split("\n", 1)[0];
    flash(`${automation.name} ran${answer ? ` — ${answer.slice(0, 60)}` : ""}`);
    // Already looking at that channel: refresh it so the answer appears.
    if (activeAutomation?.id === automation.id) await showChat(automation);
  } catch (error) {
    flash(`${automation.name} failed: ${error.message}`);
  }
}

async function clearChat() {
  try {
    const id = await ensureChannel(TASK_CHANNEL_KEY);
    await apiJSON(`/api/channels/${encodeURIComponent(id)}`, {
      method: "DELETE",
      headers: deviceKey() ? { "X-Gemini-Key": deviceKey() } : {},
    });
    history.replaceState(null, "", "#chat");
    await showChat(null);
    flash("Chat deleted");
  } catch (error) {
    flash(`Error: ${error.message}`);
  }
}

async function deleteAutomation(automation) {
  // One mis-tap must not destroy an automation and its prompt for good.
  if (!confirm(`Delete "${automation.name}"? Its prompt and schedule are gone for good.`)) return;
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

/* Nothing is created until Save: the config comes first, and closing the
   editor on a draft leaves the board exactly as it was. */
function openNewAutomationEditor() {
  editorMode = "new";
  editing = null;
  editor.dataset.kind = "automation";
  editorTitle.textContent = "New automation";
  editorPromptLabel.textContent = "Prompt";
  editorName.value = "";
  editorPrompt.value = "";
  editorFrequency.value = "daily";
  editorWeekday.value = "0";
  editorTime.value = "09:00";
  editorMinute.value = "0";
  editorDelete.hidden = true;
  editorNext.textContent = "";
  syncEditor();
  editor.showModal();
  openLayer("editor", () => editor.close());
  editorName.focus();
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
const editorSave = $("#editor-save");
const editorRequired = $("#editor-required");
let editorMode = "chat"; // "chat" | "automation" | "new"
let editing = null;
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

/* Save stays out of reach until the editor holds everything it needs. */
function syncEditor() {
  editorTrigger.dataset.frequency = editorFrequency.value;
  const missing = [];
  if (editorMode !== "chat" && !editorName.value.trim()) missing.push("a name");
  if (!editorPrompt.value.trim()) missing.push("a prompt");
  editorSave.disabled = missing.length > 0;
  editorRequired.textContent = missing.length
    ? `Needs ${missing.join(" and ")} before it can be saved.`
    : "";
}

async function openChatEditor() {
  editorMode = "chat";
  editing = null;
  editor.dataset.kind = "chat";
  editorTitle.textContent = "Chat instructions";
  editorPromptLabel.textContent = "How the assistant behaves";
  editorPrompt.value = "";
  editorDelete.hidden = true;
  editorNext.textContent = "";
  syncEditor();
  editor.showModal();
  openLayer("editor", () => editor.close());
  try {
    editorPrompt.value = (await apiJSON("/api/settings")).system_prompt || "";
  } catch (error) {
    flash(`Could not load: ${error.message}`);
  }
  syncEditor();
}

function openAutomationEditor(automation) {
  if (!automation) return;
  editorMode = "automation";
  editing = automation;
  editor.dataset.kind = "automation";
  editorTitle.textContent = automation.name;
  editorPromptLabel.textContent = "Prompt";
  editorName.value = automation.name;
  editorPrompt.value = automation.prompt || "";
  editorFrequency.value = automation.frequency || "daily";
  const local = localTrigger(automation);
  editorWeekday.value = String(local ? local.weekday : (automation.weekday ?? 0));
  editorTime.value = local
    ? `${twoDigits(local.hour)}:${twoDigits(local.minute)}`
    : `${twoDigits(automation.hour ?? 9)}:${twoDigits(automation.minute)}`;
  editorMinute.value = String(local ? local.minute : (automation.minute ?? 0));
  editorDelete.hidden = false;
  const origin = scheduleOrigin(automation);
  editorNext.textContent = scheduleLabel(automation) + (origin ? ` — ${origin}` : "");
  syncEditor();
  editor.showModal();
  openLayer("editor", () => editor.close());
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
  if (editorSave.disabled) return;
  editorSave.disabled = true;
  try {
    if (editorMode === "chat") {
      await apiJSON("/api/settings", {
        method: "PUT",
        headers: JSON_HEADERS,
        body: JSON.stringify({ system_prompt: editorPrompt.value.trim() }),
      });
    } else {
      const body = JSON.stringify({
        name: editorName.value.trim(),
        prompt: editorPrompt.value.trim(),
        timezone: DEVICE_TIMEZONE,
        ...triggerFromForm(),
      });
      const saved = editorMode === "new"
        ? await apiJSON("/api/automations", { method: "POST", headers: JSON_HEADERS, body })
        : await apiJSON(`/api/automations/${encodeURIComponent(editing.id)}`, {
          method: "PATCH", headers: JSON_HEADERS, body,
        });
      await loadAutomations();
      if (activeAutomation?.id === saved.id) {
        activeAutomation = automations.find((item) => item.id === saved.id) || activeAutomation;
      }
    }
    editor.close();
    flash("Saved");
  } catch (error) {
    flash(`Not saved: ${error.message}`);
  } finally {
    syncEditor();
  }
}

editor.addEventListener("change", syncEditor);
editor.addEventListener("input", syncEditor);
editorSave.addEventListener("click", saveEditor);

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
  addMessage("user", submitted, { animate: true });
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
  // The message owns its files now: an empty composer, ready for the next one.
  attachments = [];
  renderChips();
  $("#file-input").value = "";

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
    const chatHeaders = { "Content-Type": "application/json" };
    if (deviceKey()) chatHeaders["X-Gemini-Key"] = deviceKey();
    if (deviceModel()) chatHeaders["X-Gemini-Model"] = deviceModel();
    const response = await fetch(`/api/channels/${encodeURIComponent(channelId)}/chat`, {
      method: "POST",
      headers: chatHeaders,
      body: JSON.stringify({
        message: submitted,
        attachments: filePayloads,
        timezone: Intl.DateTimeFormat().resolvedOptions().timeZone,
      }),
    });
    if (!response.ok || !response.body) {
      let detail = `${response.status} ${response.statusText}`;
      try { detail = (await response.json()).detail || detail; } catch {}
      throw new Error(detail);
    }
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
        bubble.innerHTML = markdown(full);
        bottom();
      }
    }
  } catch (error) {
    bubble.textContent = `Error: ${error.message}`;
  }
  bar.classList.add("complete");
  window.setTimeout(() => bar.remove(), 320);
  streaming = false;
  resize();
  input.focus();
}

$("#attach").addEventListener("click", () => $("#file-input").click());
$("#file-input").addEventListener("change", (event) => {
  addFiles(event.target.files);
  event.target.value = "";
});
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
/* Live voice session: pure voice — nothing is written into the chat except
   the tasks the agent hands to the organizer, which appear as normal turns.
   The rest of the app stays fully usable while it runs. */
const liveToggle = $("#live-toggle");
let liveChannelId = null;

liveToggle.addEventListener("click", async () => {
  if (window.LiveSession.active) {
    window.LiveSession.stop();
    return;
  }
  liveToggle.disabled = true;
  liveToggle.classList.add("connecting");
  try {
    liveChannelId = await ensureChannel(TASK_CHANNEL_KEY);
    await window.LiveSession.start(liveChannelId, {
      apiKey: deviceKey() || undefined,
      model: deviceModel() || undefined,
      onChatUpdated: async () => {
        // The voice agent dropped a task into the chat; refresh if visible.
        if (channelId === liveChannelId) await loadChannel(liveChannelId);
      },
      onNavigate: (target) => {
        if (target === "settings") $("#open-settings").click();
        else if (target === "chat" || target === "home") location.hash = "#chat";
        else location.hash = `#automation/${encodeURIComponent(target)}`;
      },
      onError: (message) => flash(`Live error: ${message}`),
      onState: (on) => {
        liveToggle.classList.remove("connecting");
        liveToggle.classList.toggle("active", on);
        liveToggle.setAttribute(
          "aria-label",
          on ? "End live conversation" : "Start live conversation",
        );
      },
    });
  } catch (error) {
    flash(`Live error: ${error.message}`);
  } finally {
    liveToggle.classList.remove("connecting");
    liveToggle.disabled = false;
  }
});

/* Settings: the evaluator's Gemini API key plus the live voice and accent. */
const settingsEditor = $("#settings-editor");

/* On desktop the dialog floats over a dimmed backdrop, and clicking that
   backdrop closes it; Esc already comes free with <dialog>. On mobile the
   dialog IS the whole screen, so a stray tap on empty space must never
   close the page — only the buttons do. */
for (const modal of [editor, settingsEditor]) {
  modal.addEventListener("click", (event) => {
    if (matchMedia("(max-width: 759px)").matches) return;
    if (event.target === modal) modal.close();
  });
}
const settingsVoice = $("#settings-voice");
const settingsLivePrompt = $("#settings-live-prompt");
const settingsApiKey = $("#settings-api-key");
const settingsModel = $("#settings-model");
const settingsMemory = $("#settings-memory");
const settingsLiveLanguages = $("#settings-live-languages");
const settingsNotionToken = $("#settings-notion-token");
// A stored Notion secret is shown as dots — a stand-in, never the secret
// itself: the server never sends it back. Typing replaces it.
const NOTION_TOKEN_MASK = "\u2022".repeat(24);
const settingsHub = $("#settings-hub");
const settingsBack = $("#settings-back");
const settingsFoot = $("#settings-foot");
const settingsTitle = $("#settings-title");
const SETTINGS_SECTIONS = {
  memory: "Agent memory",
  model: "Model setup",
  live: "Live agent",
  notifications: "Notifications",
  notion: "Notion integration",
};

const pushState = $("#push-state");

function urlB64ToUint8(value) {
  const padded = value + "=".repeat((4 - (value.length % 4)) % 4);
  const raw = atob(padded.replace(/-/g, "+").replace(/_/g, "/"));
  return Uint8Array.from(raw, (ch) => ch.charCodeAt(0));
}

async function subscribeToPush() {
  const registration = await navigator.serviceWorker.ready;
  const { key } = await apiJSON("/api/push/key");
  const subscription = await registration.pushManager.subscribe({
    userVisibleOnly: true,
    applicationServerKey: urlB64ToUint8(key),
  });
  await apiJSON("/api/push/subscribe", {
    method: "POST",
    headers: JSON_HEADERS,
    body: JSON.stringify(subscription.toJSON()),
  });
}

// The one button is a truthful toggle: it reads "Enable" until a
// subscription really exists, then turns into the red off switch.
const enablePush = $("#enable-push");
const PUSH_OFF_KEY = "agentonomy-push-off";

function pushUI(on) {
  enablePush.textContent = on ? "Turn off on this device" : "Enable on this device";
  enablePush.classList.toggle("primary", !on);
  enablePush.classList.toggle("danger", on);
  enablePush.dataset.on = on ? "1" : "";
  pushState.textContent = on
    ? "On: due reminders notify this device."
    : "When a reminder is due, this device gets a notification from the app itself — even when it is closed.";
}

enablePush.addEventListener("click", async () => {
  if (!("Notification" in window) || !("serviceWorker" in navigator)) {
    pushState.textContent = "This browser does not support notifications.";
    return;
  }
  if (enablePush.dataset.on) {
    try {
      const registration = await navigator.serviceWorker.ready;
      const subscription = await registration.pushManager.getSubscription();
      if (subscription) {
        await apiJSON("/api/push/unsubscribe", {
          method: "POST",
          headers: JSON_HEADERS,
          body: JSON.stringify({ endpoint: subscription.endpoint }),
        });
        await subscription.unsubscribe();
      }
      localStorage.setItem(PUSH_OFF_KEY, "1");
      pushUI(false);
      flash("Notifications off on this device");
    } catch (error) {
      pushState.textContent = `Could not turn off: ${error.message}`;
    }
    return;
  }
  try {
    const permission = await Notification.requestPermission();
    if (permission !== "granted") {
      pushState.textContent = "Notifications are blocked for this app — allow them in the browser's site settings.";
      return;
    }
    await subscribeToPush();
    localStorage.removeItem(PUSH_OFF_KEY);
    pushUI(true);
    flash("Reminder notifications enabled");
  } catch (error) {
    pushState.textContent = `Could not enable: ${error.message}`;
  }
});

// A device that already granted permission quietly renews its subscription,
// so a new deployment or an expired subscription never loses the channel —
// unless the user turned this device off, which stays off. "On" is only
// claimed once the renewal actually succeeded.
if ("Notification" in window && Notification.permission === "granted"
    && !localStorage.getItem(PUSH_OFF_KEY)) {
  subscribeToPush()
    .then(() => pushUI(true))
    .catch(() => { pushState.textContent = "Could not renew notifications — tap Enable again."; });
}

function showSettingsSection(name) {
  settingsHub.hidden = Boolean(name);
  for (const section of document.querySelectorAll(".settings-section")) {
    section.hidden = section.dataset.section !== name;
  }
  settingsTitle.textContent = name ? SETTINGS_SECTIONS[name] : "Settings";
  // Notifications has nothing to save: its buttons act immediately.
  settingsFoot.hidden = !name || name === "notifications";
  // Remove key lives with the key: Model setup only, and only when one is stored.
  settingsRemoveKey.hidden = name !== "model" || !deviceKey();
}

settingsHub.addEventListener("click", (event) => {
  const button = event.target.closest("[data-section]");
  if (!button) return;
  showSettingsSection(button.dataset.section);
  openLayer("settings-section", () => showSettingsSection(null));
});
settingsBack.addEventListener("click", () => {
  // In a section, Go back returns to the hub; on the hub it leaves Settings.
  if (settingsHub.hidden) {
    showSettingsSection(null);
    dropLayer("settings-section");
  } else {
    settingsEditor.close();
  }
});
settingsEditor.addEventListener("close", () => {
  dropLayer("settings-section");
  dropLayer("settings");
});
const settingsNotionId = $("#settings-notion-id");
const settingsApiKeyState = $("#settings-api-key-state");
const settingsRemoveKey = $("#settings-remove-key");
const NO_KEY_HINT = "No key on this device — the app runs on the server's own credentials.";
const KEY_REQUIRED_HINT = "No key on this device — paste your Gemini API key to use the app.";
const KEY_SET_HINT = "Saved on this device only, shown masked. Clearing the field and saving removes it.";

// The saved key stays visible (masked) in the field, but can't be copied out.
settingsApiKey.addEventListener("copy", (event) => event.preventDefault());
settingsApiKey.addEventListener("cut", (event) => event.preventDefault());
settingsNotionToken.addEventListener("copy", (event) => event.preventDefault());
settingsNotionToken.addEventListener("cut", (event) => event.preventDefault());
settingsNotionToken.addEventListener("focus", () => {
  // Tapping into the dots clears them so typing starts clean.
  if (settingsNotionToken.value.includes("\u2022")) settingsNotionToken.value = "";
});
settingsNotionToken.addEventListener("blur", () => {
  // Left empty with a secret stored: the dots come back, nothing changed.
  if (!settingsNotionToken.value && settingsNotionToken.dataset.stored === "1") {
    settingsNotionToken.value = NOTION_TOKEN_MASK;
  }
});

$("#open-settings").addEventListener("click", async () => {
  // The dialog appears at once; its fields arrive when the server answers.
  drawer.close();
  settingsEditor.classList.add("loading");
  settingsEditor.showModal();
  openLayer("settings", () => settingsEditor.close());
  try {
    const settings = await apiJSON("/api/settings");
    settingsVoice.replaceChildren(
      new Option("Default", ""),
      ...settings.voices.map((voice) => new Option(voice, voice)),
    );
    settingsVoice.value = settings.voice_name || "";
    settingsLivePrompt.value = settings.live_prompt || "";
    settingsLiveLanguages.value = settings.live_languages || "";
    settingsApiKey.value = deviceKey();
    settingsApiKeyState.textContent = deviceKey()
      ? KEY_SET_HINT
      : (settings.require_key ? KEY_REQUIRED_HINT : NO_KEY_HINT);
    settingsModel.value = deviceModel();
    settingsModel.placeholder = settings.default_model || "";
    settingsMemory.value = settings.memory || "";
    settingsNotionId.value = settings.notion_database_id || "";
    settingsNotionToken.value = settings.notion_token_set ? NOTION_TOKEN_MASK : "";
    settingsNotionToken.dataset.stored = settings.notion_token_set ? "1" : "";
    $("#settings-notion-token-state").textContent = settings.notion_token_set
      ? "Notion is connected. Type over the dots to switch to another secret."
      : "Not connected — paste the integration secret from notion.so/my-integrations.";
    showSettingsSection(null);
    settingsEditor.classList.remove("loading");
  } catch (error) {
    settingsEditor.close();
    flash(`Could not load settings: ${error.message}`);
  }
});

$("#settings-save").addEventListener("click", async () => {
  // The fields are the state: what you see when you hit Save is what is saved.
  const typedKey = settingsApiKey.value.trim();
  if (typedKey) localStorage.setItem(GEMINI_KEY_STORAGE, typedKey);
  else localStorage.removeItem(GEMINI_KEY_STORAGE);
  const typedModel = settingsModel.value.trim();
  if (typedModel) localStorage.setItem(GEMINI_MODEL_STORAGE, typedModel);
  else localStorage.removeItem(GEMINI_MODEL_STORAGE);
  try {
    const payload = {
      memory: settingsMemory.value,
      notion_database_id: settingsNotionId.value,
      voice_name: settingsVoice.value,
      language_code: "",
      live_languages: settingsLiveLanguages.value,
      live_prompt: settingsLivePrompt.value,
    };
    const typedNotionToken = settingsNotionToken.value.trim();
    if (typedNotionToken && !typedNotionToken.includes("\u2022")) {
      payload.notion_token = typedNotionToken;
    }
    await apiJSON("/api/settings", {
      method: "PUT",
      headers: JSON_HEADERS,
      body: JSON.stringify(payload),
    });
    if (typedNotionToken && !typedNotionToken.includes("\u2022")) {
      settingsNotionToken.value = NOTION_TOKEN_MASK;
      settingsNotionToken.dataset.stored = "1";
    }
    settingsEditor.close();
    flash(typedKey ? "Saved — key stays on this device" : "Settings saved");
  } catch (error) {
    flash(`Error: ${error.message}`);
  }
});

$("#settings-check-key").addEventListener("click", async () => {
  const button = $("#settings-check-key");
  const key = settingsApiKey.value.trim() || deviceKey();
  if (!key) {
    settingsApiKeyState.textContent = "Paste a key first, then check it.";
    return;
  }
  button.disabled = true;
  settingsApiKeyState.textContent = "Checking — asking the model for one word…";
  try {
    const headers = { "X-Gemini-Key": key };
    const model = settingsModel.value.trim() || deviceModel();
    if (model) headers["X-Gemini-Model"] = model;
    const result = await apiJSON("/api/key-check", { method: "POST", headers });
    settingsApiKeyState.textContent = result.ok
      ? `Key works — ${result.model} answered.`
      : `Check failed: ${result.reason}`;
  } catch (error) {
    settingsApiKeyState.textContent = `Check failed: ${error.message}`;
  }
  button.disabled = false;
});

settingsRemoveKey.addEventListener("click", () => {
  localStorage.removeItem(GEMINI_KEY_STORAGE);
  settingsApiKey.value = "";
  settingsRemoveKey.hidden = true;
  settingsApiKeyState.textContent = NO_KEY_HINT;
  flash("Key removed from this device");
});
window.addEventListener("hashchange", () => route().catch(showLoadError));

function showLoadError(error) {
  console.error(error);
  transcript.innerHTML = "<div class=\"empty-state\">Unable to load this chat.</div>";
}

/* Installable app: register the shell worker and, when the browser offers
   installation, grow an "Install app" row at the bottom of the drawer. */
if ("serviceWorker" in navigator) {
  navigator.serviceWorker.register("/sw.js").catch(() => {});
}
window.addEventListener("beforeinstallprompt", (event) => {
  event.preventDefault();
  if (document.querySelector("#install-app")) return;
  const row = document.createElement("button");
  row.type = "button";
  row.className = "channel";
  row.id = "install-app";
  row.innerHTML = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 3v12"/><path d="m7 10 5 5 5-5"/><path d="M5 21h14"/></svg><span>Install app</span>';
  row.addEventListener("click", async () => {
    drawer.close();
    event.prompt();
    const choice = await event.userChoice;
    if (choice.outcome === "accepted") row.remove();
  });
  // Directly above Settings, which keeps the drawer's last word.
  drawer.querySelector("#open-settings").before(row);
});

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
