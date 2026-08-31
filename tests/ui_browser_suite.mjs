import assert from "node:assert/strict";
import fs from "node:fs/promises";
import path from "node:path";
import { chromium } from "playwright-core";


const baseURL = process.env.UI_BASE_URL || "http://127.0.0.1:8764";
const expectedRevision = process.env.UI_EXPECTED_BUILD_REVISION || "avi-notes-assistant-rc4-ui";
const chromePath = process.env.CHROME_PATH
  || "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome";
const evidenceDirectory = path.resolve(
  process.env.UI_EVIDENCE_DIR || "evidence/browser",
);
const checks = [];
const diagnostics = [];


function pass(name, detail = "") {
  checks.push({ name, status: "PASS", detail });
}


function fail(name, error) {
  checks.push({ name, status: "FAIL", detail: String(error?.message || error) });
}


async function check(name, action) {
  try {
    const detail = await action();
    pass(name, detail || "");
  } catch (error) {
    fail(name, error);
    throw error;
  }
}


async function assertExpectedServer() {
  const response = await fetch(`${baseURL}/api/health`);
  const contentType = response.headers.get("content-type") || "unknown content type";
  if (response.status !== 200 || !contentType.includes("application/json")) {
    throw new Error(
      `${baseURL} is not the expected app: GET /api/health returned ${response.status} (${contentType}). Free its port and start the documented browser-test server.`,
    );
  }
  const health = await response.json();
  assert.equal(health.build_revision, expectedRevision, `port serves ${health.build_revision}, expected ${expectedRevision}`);
  assert.equal(health.model, "gemini-3.7-flash");
  assert.equal(health.location, "global");
  assert.equal(health.framework, "Google ADK");
  assert.equal(health.firestore_mode, "local");
}


async function accessibleName(page) {
  return page.evaluate(() => {
    const element = document.activeElement;
    if (!element) return "";
    const labelledBy = element.getAttribute("aria-labelledby");
    if (labelledBy) {
      return labelledBy.split(/\s+/).map((id) => document.getElementById(id)?.textContent || "").join(" ").trim();
    }
    return (
      element.getAttribute("aria-label")
      || element.getAttribute("title")
      || element.textContent
      || element.getAttribute("placeholder")
      || ""
    ).trim();
  });
}


async function tabUntil(page, expected, maximum = 40) {
  for (let index = 0; index < maximum; index += 1) {
    await page.keyboard.press("Tab");
    const name = await accessibleName(page);
    if (expected.test(name)) return name;
  }
  throw new Error(`Tab did not reach ${expected}`);
}


async function resetTabOrder(page) {
  await page.evaluate(() => {
    document.activeElement?.blur();
    document.body.tabIndex = -1;
    document.body.focus();
  });
}


async function assertAccessibleControls(page, label) {
  const unnamed = await page.evaluate(() => {
    const selector = "button,a,input,textarea,select,[role=button]";
    const visible = (element) => {
      const style = getComputedStyle(element);
      const box = element.getBoundingClientRect();
      return style.display !== "none" && style.visibility !== "hidden" && box.width > 0 && box.height > 0;
    };
    const name = (element) => {
      const labelledBy = element.getAttribute("aria-labelledby");
      if (labelledBy) {
        const text = labelledBy.split(/\s+/).map((id) => document.getElementById(id)?.textContent || "").join(" ").trim();
        if (text) return text;
      }
      return (
        element.getAttribute("aria-label")
        || element.getAttribute("title")
        || element.textContent
        || element.getAttribute("alt")
        || element.getAttribute("placeholder")
        || ""
      ).trim();
    };
    return [...document.querySelectorAll(selector)]
      .filter(visible)
      .filter((element) => !name(element))
      .map((element) => `${element.tagName.toLowerCase()}#${element.id}.${element.className}`);
  });
  assert.deepEqual(unnamed, [], `${label} has unnamed visible controls`);
}


async function until(check, message, timeout = 15000) {
  for (let waited = 0; waited < timeout; waited += 250) {
    if (await check()) return;
    await new Promise((resolve) => setTimeout(resolve, 250));
  }
  throw new Error(message);
}


async function openDrawer(page) {
  await page.locator("#menu").click();
  await page.waitForFunction(() => {
    const element = document.getElementById("drawer");
    return element.open && element.getBoundingClientRect().left > -0.5;
  });
}


async function closedDrawer(page) {
  await page.waitForFunction(() => !document.getElementById("drawer").open);
}


async function openEditor(page) {
  await page.waitForFunction(() => document.getElementById("editor").open);
}


async function closedEditor(page) {
  await page.waitForFunction(() => !document.getElementById("editor").open);
}


/* Every prompt and trigger is edited through a row's ⋯ menu; there is no
   settings surface left to navigate to. */
async function exerciseEditorSurface(page, theme, mobile, functional) {
  const label = `${theme} ${mobile ? "mobile" : "desktop"}`;
  const shot = `${theme}-${mobile ? "mobile" : "desktop"}`;
  // The chat may already hold messages from the surface run before this one,
  // so wait on the channel list rather than on an empty transcript.
  await page.goto(`${baseURL}/`, { waitUntil: "networkidle" });
  await page.waitForSelector('#automation-channels [data-menu="organize-tasks"]', { state: "attached" });

  // Chat can be edited or deleted: there is nothing to run without something typed.
  await openDrawer(page);
  await page.locator('[data-menu="chat"]').click();
  assert.deepEqual(
    await page.locator('.row-menu[data-menu-for="chat"] button').allInnerTexts(),
    ["Edit instructions", "Delete chat"],
  );
  await page.locator('[data-action="edit-chat"]').click();
  await openEditor(page);
  assert.equal(await page.locator("#editor").getAttribute("data-kind"), "chat");
  await page.waitForFunction(() => document.getElementById("editor-prompt").value.length > 0);
  assert.equal(await page.locator("#editor-name").isVisible(), false);
  assert.equal(await page.locator("#editor-trigger").isVisible(), false);
  await assertAccessibleControls(page, `chat editor ${label}`);
  await page.screenshot({ path: path.join(evidenceDirectory, `${shot}-editor-chat.png`) });
  await page.keyboard.press("Escape");
  await closedEditor(page);

  // An automation carries a prompt and a trigger; every one can be deleted.
  await openDrawer(page);
  await page.locator('[data-menu="organize-tasks"]').click();
  assert.deepEqual(
    await page.locator('.row-menu[data-menu-for="organize-tasks"] button').allInnerTexts(),
    ["Run now", "Edit", "Delete"],
  );
  await page.locator('[data-action="edit"][data-id="organize-tasks"]').click();
  await openEditor(page);
  assert.equal(await page.locator("#editor-frequency").inputValue(), "weekly");
  assert.equal(await page.locator("#editor-time").inputValue(), "09:00");
  assert.equal((await page.locator("#editor-next").innerText()).trim(), "Weekly on Sunday at 09:00");
  assert.equal(await page.locator("#editor-time").isVisible(), true);
  assert.equal(await page.locator("#editor-weekday").isVisible(), true);
  assert.equal(await page.locator("#editor-minute").isVisible(), false);
  assert.equal(await page.locator("#editor-delete").isVisible(), true);
  assert.equal(await page.locator("#editor-save").isDisabled(), false);
  const layout = await page.evaluate(() => ({
    scrollWidth: document.documentElement.scrollWidth,
    width: innerWidth,
  }));
  assert.ok(layout.scrollWidth <= layout.width, "editor overflows horizontally");
  await assertAccessibleControls(page, `automation editor ${label}`);
  await page.screenshot({ path: path.join(evidenceDirectory, `${shot}-editor-automation.png`) });
  await page.keyboard.press("Escape");
  await closedEditor(page);

  if (!functional) return;

  const automationCount = () =>
    page.evaluate(() => document.querySelectorAll("#automation-channels .channel").length);
  const listed = async () =>
    (await (await page.request.get(`${baseURL}/api/automations`)).json()).automations;

  // "+ New automation" opens the config first and saves nothing on its own.
  await openDrawer(page);
  await page.locator("#add-automation").click();
  await openEditor(page);
  assert.equal(await page.locator("#editor-title").innerText(), "New automation");
  assert.equal(await page.locator("#editor-name").inputValue(), "");
  assert.equal(await page.locator("#editor-delete").isVisible(), false);
  assert.equal(await page.locator("#editor-save").isDisabled(), true);
  assert.match(await page.locator("#editor-required").innerText(), /needs a name and a prompt/i);

  // A name alone is not enough, and the "when" control follows the frequency.
  await page.locator("#editor-name").fill("Draft brief");
  assert.equal(await page.locator("#editor-save").isDisabled(), true);
  await page.locator("#editor-frequency").selectOption("weekly");
  await page.waitForFunction(() => document.getElementById("editor-trigger").dataset.frequency === "weekly");
  assert.equal(await page.locator("#editor-weekday").isVisible(), true);
  assert.equal(await page.locator("#editor-minute").isVisible(), false);
  await page.locator("#editor-frequency").selectOption("hourly");
  await page.waitForFunction(() => document.getElementById("editor-trigger").dataset.frequency === "hourly");
  assert.equal(await page.locator("#editor-minute").isVisible(), true);
  assert.equal(await page.locator("#editor-time").isVisible(), false);

  // Abandoning the draft leaves the board exactly as it was.
  await page.keyboard.press("Escape");
  await closedEditor(page);
  assert.equal(await automationCount(), 1);
  assert.deepEqual((await listed()).map((item) => item.id), ["organize-tasks"]);

  // Filled in and saved, it appears as a channel with the trigger it was given.
  await openDrawer(page);
  await page.locator("#add-automation").click();
  await openEditor(page);
  await page.locator("#editor-name").fill("Draft brief");
  await page.locator("#editor-prompt").fill("Summarise the day.");
  await page.locator("#editor-frequency").selectOption("weekly");
  await page.locator("#editor-weekday").selectOption("2");
  await page.locator("#editor-time").fill("18:15");
  await page.waitForFunction(() => !document.getElementById("editor-save").disabled);
  await page.locator("#editor-save").click();
  await closedEditor(page);
  await page.waitForFunction(
    () => document.querySelectorAll("#automation-channels .channel").length === 2,
  );
  const saved = (await listed()).find((item) => item.name === "Draft brief");
  assert.equal(saved.schedule, "Weekly on Wednesday at 18:15");
  assert.equal(saved.prompt, "Summarise the day.");

  // Its ⋯ offers the same three actions as every automation.
  await openDrawer(page);
  await page.locator(`[data-menu="${saved.id}"]`).click();
  assert.deepEqual(
    await page.locator(`.row-menu[data-menu-for="${saved.id}"] button`).allInnerTexts(),
    ["Run now", "Edit", "Delete"],
  );
  await page.locator(`[data-action="edit"][data-id="${saved.id}"]`).click();
  await openEditor(page);
  assert.equal(await page.locator("#editor-name").inputValue(), "Draft brief");
  assert.equal(await page.locator("#editor-frequency").inputValue(), "weekly");
  assert.equal(await page.locator("#editor-weekday").inputValue(), "2");
  assert.equal(await page.locator("#editor-time").inputValue(), "18:15");

  // The editor's own Delete removes it; the close button just closes.
  await page.locator("#editor-delete").click();
  await closedEditor(page);
  await page.waitForFunction(
    () => document.querySelectorAll("#automation-channels .channel").length === 1,
  );
  assert.deepEqual((await listed()).map((item) => item.id), ["organize-tasks"]);

  await openDrawer(page);
  await page.locator('[data-menu="chat"]').click();
  await page.locator('[data-action="edit-chat"]').click();
  await openEditor(page);
  await page.getByRole("button", { name: "Close editor" }).click();
  await closedEditor(page);

  // One control, three modes, each showing the icon for the mode it is in.
  const themeState = async () => page.evaluate(() => ({
    mode: document.documentElement.dataset.themeMode,
    theme: document.documentElement.dataset.theme,
    label: document.getElementById("theme").getAttribute("aria-label"),
    icon: [...document.querySelectorAll("#theme svg")]
      .filter((svg) => getComputedStyle(svg).display !== "none")
      .map((svg) => svg.getAttribute("class"))
      .join(),
  }));
  const cycle = [];
  for (let step = 0; step < 4; step += 1) {
    cycle.push(await themeState());
    if (step < 3) await page.locator("#theme").click(); // ends on the theme it began with
  }
  assert.deepEqual(cycle.map((item) => item.mode), ["dark", "system", "light", "dark"]);
  assert.deepEqual(
    cycle.map((item) => item.icon),
    ["mode-dark", "mode-system", "mode-light", "mode-dark"],
  );
  assert.match(cycle[1].label, /system/i);
  assert.equal(cycle[2].theme, "light");
  assert.equal(await page.evaluate(() => localStorage.getItem("agentonomy-theme")), "dark");
}


async function computedTaskStyles(page) {
  return page.evaluate(() => {
    const style = (selector) => getComputedStyle(document.querySelector(selector));
    const rect = (selector) => document.querySelector(selector).getBoundingClientRect();
    const shell = style(".composer-shell");
    const input = style(".composer-input");
    const attach = rect(".attach-button");
    const send = rect(".send-button");
    return {
      theme: document.documentElement.dataset.theme,
      paneBackground: style(".chat-pane").backgroundColor,
      shellBackground: shell.backgroundColor,
      shellBorderRadius: shell.borderRadius,
      shellPadding: shell.padding,
      shellBoxShadow: shell.boxShadow,
      shellBackdrop: shell.backdropFilter || shell.webkitBackdropFilter,
      shellWidth: rect(".composer-shell").width,
      inputFontSize: input.fontSize,
      inputLineHeight: input.lineHeight,
      inputMinHeight: input.minHeight,
      inputMaxHeight: input.maxHeight,
      inputPadding: input.padding,
      attach: [attach.width, attach.height],
      send: [send.width, send.height],
      viewport: [innerWidth, innerHeight],
      scrollWidth: document.documentElement.scrollWidth,
    };
  });
}


function expectedRGB(theme, dark, light) {
  return theme === "dark" ? dark : light;
}


async function exerciseTaskSurface(page, theme, mobile, functional) {
  await page.goto(`${baseURL}/`, { waitUntil: "networkidle" });
  await page.waitForSelector(".empty-state");
  assert.equal(await page.locator("html").getAttribute("data-theme"), theme);
  // The brand A mark stands in for the letter A; the startup screen must be
  // gone once the first screen has loaded.
  assert.equal((await page.locator(".wordmark").innerText()).trim(), "gentonomy Tasks");
  assert.equal(await page.locator(".wordmark-a").count(), 1);
  await page.waitForSelector("#splash", { state: "detached" });
  assert.equal(await page.getByText("Recent chats", { exact: false }).count(), 0);

  // The only permanent chrome is the top bar; channels live behind the menu.
  assert.equal(await page.locator("#drawer").evaluate((element) => element.open), false);
  await openDrawer(page);
  const drawer = await page.locator("#drawer").evaluate((element) => ({
    width: element.getBoundingClientRect().width,
    viewport: innerWidth,
  }));
  const expectedWidth = mobile ? drawer.viewport : drawer.viewport / 3;
  assert.ok(
    Math.abs(drawer.width - expectedWidth) < 1,
    `drawer is ${drawer.width}px wide, expected ${expectedWidth}px`,
  );
  // #install-app only exists when the browser offers installation, so it is
  // excluded rather than asserted either way.
  assert.deepEqual(
    (await page.locator("#drawer .channel:not(#install-app)").allInnerTexts()).map((item) => item.trim()),
    ["Chat", "Organize tasks", "New automation", "Settings"],
  );
  assert.equal(await page.locator("#drawer .dots").count(), 2);
  assert.equal(await page.locator("#drawer .row-menu:not([hidden])").count(), 0);
  await assertAccessibleControls(page, `drawer ${theme} ${mobile ? "mobile" : "desktop"}`);
  await page.screenshot({
    path: path.join(evidenceDirectory, `${theme}-${mobile ? "mobile" : "desktop"}-drawer.png`),
  });
  await page.keyboard.press("Escape");
  await closedDrawer(page);

  const styles = await computedTaskStyles(page);
  assert.equal(styles.paneBackground, expectedRGB(theme, "rgb(18, 18, 18)", "rgb(237, 237, 237)"));
  assert.equal(styles.shellBackground, expectedRGB(theme, "rgb(45, 45, 45)", "rgb(201, 201, 201)"));
  assert.equal(styles.shellBorderRadius, mobile ? "22px" : "28px");
  assert.equal(styles.shellPadding, mobile ? "8px" : "12px");
  assert.equal(styles.shellBackdrop, "none");
  assert.match(
    styles.shellBoxShadow,
    theme === "dark" ? /0px 22px 70px/ : /0px 18px 50px/,
  );
  assert.ok(styles.shellWidth <= 1060.01);
  assert.equal(styles.inputFontSize, "16px");
  assert.equal(styles.inputLineHeight, "22.4px");
  assert.equal(styles.inputMinHeight, mobile ? "40px" : "48px");
  assert.equal(styles.inputMaxHeight, "180px");
  assert.equal(styles.inputPadding, mobile ? "8px 4px" : "12px 4px 10px");
  assert.deepEqual(styles.attach, mobile ? [36, 36] : [44, 44]);
  assert.deepEqual(styles.send, mobile ? [40, 40] : [48, 48]);
  assert.ok(styles.scrollWidth <= styles.viewport[0], "task page overflows horizontally");

  await page.evaluate(() => document.activeElement?.blur());
  await page.waitForTimeout(250); // let the border-color transition settle
  const beforeFocus = await page.locator(".composer-shell").evaluate((element) => ({
    border: getComputedStyle(element).borderColor,
    rect: element.getBoundingClientRect().toJSON(),
  }));
  await page.locator("#input").focus();
  await page.waitForTimeout(250);
  const afterFocus = await page.locator(".composer-shell").evaluate((element) => ({
    border: getComputedStyle(element).borderColor,
    rect: element.getBoundingClientRect().toJSON(),
  }));
  assert.equal(beforeFocus.border, expectedRGB(theme, "rgba(255, 255, 255, 0.06)", "rgba(0, 0, 0, 0.06)"));
  assert.equal(afterFocus.border, expectedRGB(theme, "rgba(255, 255, 255, 0.16)", "rgba(0, 0, 0, 0.16)"));
  assert.deepEqual(afterFocus.rect, beforeFocus.rect, "focus changed composer geometry");

  // Attach, mic and send sit in the bottom corners and stay there however many
  // lines are typed: only the text box grows, and it grows upward.
  const corners = () => page.evaluate(() => {
    const at = (selector) => {
      const box = document.querySelector(selector).getBoundingClientRect();
      return [Math.round(box.left), Math.round(innerHeight - box.bottom)];
    };
    return {
      attach: at(".attach-button"),
      live: at(".live-toggle"),
      send: at(".send-button"),
      inputBottom: Math.round(innerHeight - document.querySelector("#input").getBoundingClientRect().bottom),
    };
  });
  const oneLine = await corners();
  await page.locator("#input").fill("A long synthetic sentence that wraps across multiple lines. ".repeat(30));
  const grown = await page.locator("#input").evaluate((element) => ({
    height: element.getBoundingClientRect().height,
    overflowY: getComputedStyle(element).overflowY,
  }));
  assert.ok(grown.height > 48, "the text box did not grow");
  assert.ok(grown.height <= 180.01);
  assert.equal(grown.overflowY, "auto");
  // Past three lines the text takes its own full-width row above the buttons;
  // the buttons themselves keep their corner positions throughout.
  const wrapped = await corners();
  assert.deepEqual(
    { attach: wrapped.attach, live: wrapped.live, send: wrapped.send },
    { attach: oneLine.attach, live: oneLine.live, send: oneLine.send },
    "composer buttons moved when the message wrapped",
  );
  assert.equal(
    await page.locator("#composer-grid").evaluate((el) => el.classList.contains("tall")),
    true,
    "a long message should lift the text above the buttons",
  );
  assert.ok(wrapped.inputBottom > oneLine.inputBottom, "the wrapped text box should sit above the buttons");
  await page.locator("#input").fill("");
  assert.deepEqual(await corners(), oneLine, "emptying the composer should restore the one-line layout");

  if (functional) {
    await page.locator("#input").focus();
    await page.keyboard.press("Enter");
    assert.equal(await page.locator("#input").inputValue(), "");
    await page.keyboard.press("Shift+Enter");
    assert.equal(await page.locator("#input").inputValue(), "\n");
    await page.locator("#input").fill("");

    // An automation runs from its own ⋯ menu, reached by keyboard — in the
    // background: the view stays put and a toast reports the outcome.
    await openDrawer(page);
    await page.locator("#channel-chat").focus();
    assert.match(await tabUntil(page, /^Organize tasks options$/), /^Organize tasks options$/);
    await page.keyboard.press("Enter");
    assert.match(await tabUntil(page, /^Run now$/), /^Run now$/);
    await page.keyboard.press("Enter");
    await page.waitForFunction(
      () => /Organize tasks ran/.test(document.querySelector("#toast")?.textContent || ""),
    );
    await page.keyboard.press("Escape");
    await closedDrawer(page);
    assert.equal(
      await page.evaluate(() => document.body.classList.contains("automation-view")),
      false,
      "running an automation must not move the user to its channel",
    );
    // Visiting the channel afterwards shows the answer that landed there.
    await openDrawer(page);
    await page.locator("#automation-channels a").first().click();
    await closedDrawer(page);
    await page.waitForFunction(
      () => /Added Print the contract/.test(document.querySelector("#transcript")?.textContent || ""),
    );
    await page.screenshot({ path: path.join(evidenceDirectory, `${theme}-${mobile ? "mobile" : "desktop"}-automation.png`) });

    await openDrawer(page);
    await page.locator("#channel-chat").click();
    await closedDrawer(page);
    await page.waitForSelector("#chat-pane:not([hidden])");
    await resetTabOrder(page);
    assert.match(await tabUntil(page, /^Attach a file$/), /^Attach a file$/);
    // The button is keyboard-reachable (asserted above); the file itself is
    // fed straight to the hidden input — the native chooser event is flaky
    // under headless load and adds nothing to the coverage.
    await page.locator("#file-input").setInputFiles({
      name: "synthetic-attachment.pdf",
      mimeType: "application/pdf",
      buffer: Buffer.from("synthetic browser fixture"),
    });
    await page.getByRole("button", { name: "Remove synthetic-attachment.pdf" }).waitFor();

    await page.locator("#input").focus();
    await page.keyboard.type("print the contract at the office");
    await page.keyboard.press("Enter");
    const replyBubble = page.locator(".message-row.assistant .message-bubble").last();
    await until(async () => (await replyBubble.innerText()).includes("Added"), "reply never arrived");
    const replyText = await replyBubble.innerText();
    // One short line: the reply names the task and stops there.
    assert.equal(replyText.trim(), "Added Print the contract.");

    const user = page.locator(".message-row.user .message-bubble").last();
    const assistant = replyBubble;
    const userStyle = await user.evaluate((element) => {
      const value = getComputedStyle(element);
      return {
        radius: value.borderRadius,
        padding: value.padding,
        shadow: value.boxShadow,
        background: value.backgroundColor,
        border: value.borderColor,
      };
    });
    const assistantStyle = await assistant.evaluate((element) => {
      const value = getComputedStyle(element);
      return {
        background: value.backgroundColor,
        border: value.borderColor,
        padding: value.padding,
        animation: value.animationName,
        transition: value.transitionDuration,
      };
    });
    assert.equal(userStyle.radius, "16px 16px 0px");
    assert.equal(userStyle.padding, "10px 16px 8px");
    assert.match(
      userStyle.shadow,
      theme === "dark" ? /0px 20px 25px -5px/ : /0px 10px 18px -8px/,
    );
    // The bubble colors derive from the accent tokens; resolve them in-page
    // instead of pinning raw color strings.
    const expectedBubble = await page.evaluate(() => {
      const probe = document.createElement("div");
      probe.style.cssText = "background: var(--user-bubble); border: 1px solid var(--user-border)";
      document.body.append(probe);
      const probeStyle = getComputedStyle(probe);
      const resolved = { background: probeStyle.backgroundColor, border: probeStyle.borderColor };
      probe.remove();
      return resolved;
    });
    assert.equal(userStyle.background, expectedBubble.background);
    assert.equal(userStyle.border, expectedBubble.border);
    assert.equal(assistantStyle.background, "rgba(0, 0, 0, 0)");
    assert.equal(assistantStyle.border, "rgba(0, 0, 0, 0)");
    assert.equal(assistantStyle.padding, "0px");
    assert.equal(assistantStyle.animation, "none");
    assert.equal(assistantStyle.transition, "0s");

  }

  await assertAccessibleControls(page, `task ${theme} ${mobile ? "mobile" : "desktop"}`);
  await page.screenshot({
    path: path.join(evidenceDirectory, `${theme}-${mobile ? "mobile" : "desktop"}-task.png`),
  });
}


async function main() {
  await assertExpectedServer();
  await fs.mkdir(evidenceDirectory, { recursive: true });
  const browser = await chromium.launch({
    executablePath: chromePath,
    headless: true,
    args: ["--disable-background-networking"],
  });
  try {
    const matrix = [
      { theme: "dark", mobile: false, viewport: { width: 1200, height: 800 } },
      { theme: "light", mobile: false, viewport: { width: 1200, height: 800 } },
      { theme: "dark", mobile: true, viewport: { width: 390, height: 844 } },
      { theme: "light", mobile: true, viewport: { width: 390, height: 844 } },
    ];
    for (const entry of matrix) {
      const context = await browser.newContext({ viewport: entry.viewport, locale: "en-US", timezoneId: "Asia/Jerusalem" });
      await context.addInitScript((theme) => localStorage.setItem("agentonomy-theme", theme), entry.theme);
      const page = await context.newPage();
      page.on("dialog", (dialog) => dialog.accept());
      page.on("console", (message) => {
        if (message.type() === "error") diagnostics.push(`console:${message.text()}`);
      });
      page.on("pageerror", (error) => diagnostics.push(`pageerror:${error.message}`));
      page.on("requestfailed", (request) => diagnostics.push(`requestfailed:${request.url()}:${request.failure()?.errorText}`));
      const functional = entry.theme === "dark" && entry.mobile === false;
      await check(`task-${entry.theme}-${entry.mobile ? "mobile" : "desktop"}`, () => exerciseTaskSurface(page, entry.theme, entry.mobile, functional));
      await check(`editor-${entry.theme}-${entry.mobile ? "mobile" : "desktop"}`, () => exerciseEditorSurface(page, entry.theme, entry.mobile, functional));
      await context.close();
    }
    await check("browser-console-and-network", async () => {
      assert.deepEqual(diagnostics, []);
      return "no console errors, page errors, or failed requests";
    });
  } finally {
    await browser.close();
  }

  const report = {
    runtime: `playwright-core ${JSON.parse(await fs.readFile(new URL("../node_modules/playwright-core/package.json", import.meta.url))).version} with system Google Chrome`,
    baseURL,
    checks,
    pass: checks.filter((item) => item.status === "PASS").length,
    fail: checks.filter((item) => item.status === "FAIL").length,
    total: checks.length,
    diagnostics,
  };
  await fs.writeFile(path.join(evidenceDirectory, "report.json"), `${JSON.stringify(report, null, 2)}\n`);
  console.log(`UI_BROWSER_SUITE pass=${report.pass} fail=${report.fail} total=${report.total}`);
  for (const item of checks) console.log(`${item.status} ${item.name}${item.detail ? ` \u2014 ${item.detail}` : ""}`);
  if (report.fail) process.exitCode = 1;
}


main().catch(async (error) => {
  console.error(`UI_BROWSER_SUITE_FATAL ${error.stack || error}`);
  try {
    await fs.mkdir(evidenceDirectory, { recursive: true });
    await fs.writeFile(path.join(evidenceDirectory, "report.json"), `${JSON.stringify({ checks, diagnostics, fatal: String(error.stack || error) }, null, 2)}\n`);
  } catch {}
  process.exitCode = 1;
});
