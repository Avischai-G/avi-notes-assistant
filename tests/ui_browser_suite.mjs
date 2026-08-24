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


/* Settings is the one non-chat surface: the chat prompt, then a prompt and a
   trigger per automation. Its API round trips are covered by the pytest suite. */
async function exerciseSettingsSurface(page, theme, mobile) {
  await page.goto(`${baseURL}/#settings`, { waitUntil: "networkidle" });
  await page.waitForSelector("#settings-pane:not([hidden])");
  assert.equal(await page.locator("#chat-pane").getAttribute("hidden"), "");
  assert.ok((await page.locator("#system-prompt").inputValue()).includes("Avi's assistant"));
  assert.equal(await page.locator(".automation-card").count(), 2);
  assert.deepEqual(
    await page.locator(".automation-card [data-field=schedule]").evaluateAll(
      (fields) => fields.map((field) => field.value),
    ),
    ["daily", "daily at 21:00 Asia/Jerusalem"],
  );
  // Built-in automations are load-bearing for planning, so they offer no delete.
  assert.equal(await page.locator("[data-delete]").count(), 0);
  assert.equal(await page.locator("#add-automation").count(), 1);
  const layout = await page.evaluate(() => ({
    scrollWidth: document.documentElement.scrollWidth,
    width: innerWidth,
  }));
  assert.ok(layout.scrollWidth <= layout.width, "settings page overflows horizontally");
  await assertAccessibleControls(page, `settings ${theme} ${mobile ? "mobile" : "desktop"}`);
  await page.screenshot({
    path: path.join(evidenceDirectory, `${theme}-${mobile ? "mobile" : "desktop"}-settings.png`),
  });
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
  assert.equal((await page.locator(".wordmark").innerText()).trim(), "Agentonomy Tasks");
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
  assert.deepEqual(
    (await page.locator("#drawer .channel").allInnerTexts()).map((item) => item.trim()),
    ["Chat", "Knowledge cleanup", "Plan tomorrow", "Learning", "Settings"],
  );
  assert.equal(await page.locator("#drawer [data-run]").count(), 2);
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
  assert.equal(styles.inputMinHeight, "48px");
  assert.equal(styles.inputMaxHeight, "180px");
  assert.equal(styles.inputPadding, "12px 4px 10px");
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

  await page.locator("#input").fill("A long synthetic sentence that wraps across multiple lines. ".repeat(30));
  assert.equal(await page.locator("#composer-grid").getAttribute("data-expanded"), "true");
  const expanded = await page.locator("#input").evaluate((element) => ({
    height: element.getBoundingClientRect().height,
    overflowY: getComputedStyle(element).overflowY,
    paddingLeft: getComputedStyle(element).paddingLeft,
    gridColumn: getComputedStyle(element).gridColumn,
    attachRow: getComputedStyle(document.querySelector(".attach-button")).gridRow,
    sendRow: getComputedStyle(document.querySelector(".send-button")).gridRow,
  }));
  assert.ok(expanded.height <= 180.01);
  assert.equal(expanded.overflowY, "auto");
  assert.equal(expanded.paddingLeft, "8px");
  assert.match(expanded.gridColumn, /1\s*\/\s*-1/);
  assert.equal(expanded.attachRow, "2");
  assert.equal(expanded.sendRow, "2");
  await page.locator("#input").fill("");
  assert.equal(await page.locator("#composer-grid").getAttribute("data-expanded"), "false");

  if (functional) {
    await page.locator("#input").focus();
    await page.keyboard.press("Enter");
    assert.equal(await page.locator("#input").inputValue(), "");
    await page.keyboard.press("Shift+Enter");
    assert.equal(await page.locator("#input").inputValue(), "\n");
    await page.locator("#input").fill("");

    // An automation runs from its own channel row, reached by keyboard.
    await openDrawer(page);
    await page.locator("#channel-chat").focus();
    assert.match(await tabUntil(page, /^Knowledge cleanup$/), /^Knowledge cleanup$/);
    await page.keyboard.press("Tab");
    assert.match(await accessibleName(page), /^Run Knowledge cleanup now$/);
    await page.keyboard.press("Enter");
    await closedDrawer(page);
    await page.waitForFunction(() => document.querySelector("#transcript")?.textContent.includes("No dream notes to consolidate."));
    await page.screenshot({ path: path.join(evidenceDirectory, `${theme}-${mobile ? "mobile" : "desktop"}-automation.png`) });

    await openDrawer(page);
    await page.locator("#channel-chat").click();
    await closedDrawer(page);
    await page.waitForSelector("#chat-pane:not([hidden])");
    await resetTabOrder(page);
    assert.match(await tabUntil(page, /^Attach a file$/), /^Attach a file$/);
    const chooserPromise = page.waitForEvent("filechooser");
    await page.keyboard.press("Enter");
    const chooser = await chooserPromise;
    await chooser.setFiles({
      name: "synthetic-attachment.pdf",
      mimeType: "application/pdf",
      buffer: Buffer.from("synthetic browser fixture"),
    });
    await page.getByRole("button", { name: "Remove synthetic-attachment.pdf" }).waitFor();

    await page.locator("#input").focus();
    await page.keyboard.type("I will be at Office tomorrow.");
    await page.keyboard.press("Enter");
    await page.getByRole("button", { name: "Pick Plan A" }).waitFor();
    const replyBubble = page.locator(".message-row.assistant .message-bubble").last();
    const replyText = await replyBubble.innerText();
    assert.match(replyText, /Planning tomorrow for Office\./);
    assert.equal(replyText.includes("?"), false, `place reply asked again: ${replyText}`);
    assert.equal(await page.locator(".plan-control").count(), 2);
    assert.deepEqual(await page.locator(".plan-control").allTextContents(), ["Pick Plan A", "Pick Plan B"]);

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

    await resetTabOrder(page);
    assert.match(await tabUntil(page, /^Pick Plan A$/), /^Pick Plan A$/);
    await page.keyboard.press("Tab");
    assert.match(await accessibleName(page), /^Pick Plan B$/);
    await page.keyboard.press("Shift+Tab");
    await page.keyboard.press("Enter");
    await page.getByText(/Plan A is set for/).last().waitFor();
  }

  await assertAccessibleControls(page, `task ${theme} ${mobile ? "mobile" : "desktop"}`);
  await page.screenshot({
    path: path.join(evidenceDirectory, `${theme}-${mobile ? "mobile" : "desktop"}-task.png`),
  });
}


async function exerciseLearningSurface(page, theme, mobile, functional, beforeRawLogProbes) {
  await page.goto(`${baseURL}/learning`, { waitUntil: "networkidle" });
  await page.waitForSelector(".metrics");
  assert.equal(await page.locator("html").getAttribute("data-theme"), theme);
  const layout = await page.evaluate(() => ({
    background: getComputedStyle(document.body).backgroundColor,
    scrollWidth: document.documentElement.scrollWidth,
    width: innerWidth,
    periods: [...document.querySelectorAll("[data-period]")].map((button) => ({
      name: button.textContent.trim(),
      pressed: button.getAttribute("aria-pressed"),
    })),
  }));
  assert.equal(layout.background, expectedRGB(theme, "rgb(18, 18, 18)", "rgb(237, 237, 237)"));
  assert.ok(layout.scrollWidth <= layout.width, "Learning page overflows horizontally");
  assert.deepEqual(layout.periods.map((item) => item.name), ["Day", "Week", "Month"]);
  assert.equal(layout.periods[0].pressed, "true");
  if (functional) {
    await resetTabOrder(page);
    assert.match(await tabUntil(page, /^Task Chat$/), /^Task Chat$/);
    assert.match(await tabUntil(page, /^Day$/), /^Day$/);
    await page.keyboard.press("Tab");
    assert.match(await accessibleName(page), /^Week$/);
    await page.keyboard.press("Space");
    assert.equal(await page.getByRole("button", { name: "Week" }).getAttribute("aria-pressed"), "true");
    await page.keyboard.press("Tab");
    assert.match(await accessibleName(page), /^Month$/);
    await page.keyboard.press("Space");
    assert.equal(await page.getByRole("button", { name: "Month" }).getAttribute("aria-pressed"), "true");
    await beforeRawLogProbes();
    for (const endpoint of ["raw", "events", "log"]) {
      const status = await page.evaluate(async (name) => (await fetch(`/api/learning/${name}`)).status, endpoint);
      assert.equal(status, 404, `raw Learning surface ${endpoint} must fail`);
    }
  }
  await assertAccessibleControls(page, `learning ${theme} ${mobile ? "mobile" : "desktop"}`);
  await page.screenshot({
    path: path.join(evidenceDirectory, `${theme}-${mobile ? "mobile" : "desktop"}-learning.png`),
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
      let captureConsoleErrors = true;
      page.on("console", (message) => {
        if (captureConsoleErrors && message.type() === "error") diagnostics.push(`console:${message.text()}`);
      });
      page.on("pageerror", (error) => diagnostics.push(`pageerror:${error.message}`));
      page.on("requestfailed", (request) => diagnostics.push(`requestfailed:${request.url()}:${request.failure()?.errorText}`));
      const functional = entry.theme === "dark" && entry.mobile === false;
      await check(`task-${entry.theme}-${entry.mobile ? "mobile" : "desktop"}`, () => exerciseTaskSurface(page, entry.theme, entry.mobile, functional));
      await check(`settings-${entry.theme}-${entry.mobile ? "mobile" : "desktop"}`, () => exerciseSettingsSurface(page, entry.theme, entry.mobile));
      await check(`learning-${entry.theme}-${entry.mobile ? "mobile" : "desktop"}`, () => exerciseLearningSurface(
        page,
        entry.theme,
        entry.mobile,
        functional,
        async () => {
          assert.deepEqual(diagnostics, [], "unexpected diagnostics before intentional raw-log 404 probes");
          captureConsoleErrors = false;
        },
      ));
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
