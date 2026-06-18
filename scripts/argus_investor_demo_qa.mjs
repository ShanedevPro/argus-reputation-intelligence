#!/usr/bin/env node
import fs from "node:fs/promises";
import { createRequire } from "node:module";
import path from "node:path";

const requireFromArgusSaas = createRequire(
  new URL("../apps/argus-saas/package.json", import.meta.url)
);
const { chromium } = requireFromArgusSaas("@playwright/test");

const frontendUrl = process.env.FRONTEND_URL || "http://localhost:3010";
const outputDir =
  process.env.ARGUS_QA_OUTPUT_DIR || "/tmp/argus-demo-qa-rerun";
const maxMinutes = Number(process.env.ARGUS_QA_MAX_MINUTES || "45");

const primaryPrompt = process.env.ARGUS_QA_PRIMARY_PROMPT ||
  "你可以联网搜索王鹤棣最近的“不舒服文学”争议吗？你自己看一下先";
const confirmPrompt = process.env.ARGUS_QA_CONFIRM_PROMPT ||
  "是的。请以这个事件作为研究对象：王鹤棣在《亲爱的客栈2026》中因颁奖感到不适并发微博回应（“我当时确实不舒服”）引发“不舒服文学”出圈。主体是王鹤棣，时间窗口为2026年5月1日至2026年5月29日。请创建 Research Plan。";
const expectedSearchTexts = (
  process.env.ARGUS_QA_EXPECTED_SEARCH_TEXTS || "不舒服文学,webSearch,搜索结果"
)
  .split(",")
  .map((text) => text.trim())
  .filter(Boolean);
const expectedProfileLabel = (process.env.ARGUS_QA_PROFILE_LABEL || "").trim();

const screenshotsDir = path.join(outputDir, "screenshots");
const logsDir = path.join(outputDir, "logs");
const networkDir = path.join(outputDir, "network");
const reportsDir = path.join(outputDir, "reports");
const consoleEvents = [];
const networkEvents = [];
const findings = [];
let screenshotIndex = 0;
let observedCrawlTaskId = "";
let observedAnalysisQuery = "";
let observedSearchTaskId = "";
let observedReportTaskId = "";

await prepareOutput();

const browser = await chromium.launch({ headless: true });
const context = await browser.newContext({ viewport: { width: 1440, height: 1000 } });
const page = await context.newPage();

page.on("console", (message) => {
  consoleEvents.push({
    at: new Date().toISOString(),
    type: message.type(),
    text: message.text(),
    url: page.url(),
  });
});
page.on("pageerror", (error) => {
  consoleEvents.push({
    at: new Date().toISOString(),
    type: "pageerror",
    text: error.message,
    url: page.url(),
  });
});
page.on("response", async (response) => {
  const url = response.url();
  const tracked = [
    "/api/chat",
    "/api/intake/web-search",
    "/api/argus/crawl",
    "/api/argus/search",
    "/api/argus/report",
  ].some((part) => url.includes(part));
  if (!tracked) {
    return;
  }
  const entry = {
    at: new Date().toISOString(),
    method: response.request().method(),
    url,
    status: response.status(),
    statusText: response.statusText(),
  };
  networkEvents.push(entry);
  await saveResponseBody(response, entry);
});

try {
  await page.goto(frontendUrl, { waitUntil: "domcontentloaded", timeout: 60_000 });
  await screenshot(page, "001-homepage");
  await expectAnyText(
    page,
    ["What should Argus investigate?", "Argus", "研究"],
    "homepage prompt"
  );

  await sendPrompt(page, primaryPrompt);
  await screenshot(page, "002-web-search-sent");
  await waitForAnyText(page, expectedSearchTexts, 180_000);
  await screenshot(page, "003-web-search-result");

  const bodyAfterSearch = await page.locator("body").innerText();
  if (/无法联网|不能联网|无法搜索|不能搜索/.test(bodyAfterSearch)) {
    findings.push({
      severity: "P1",
      finding: "Assistant said it could not search.",
      evidence: bodyAfterSearch.slice(0, 1000),
    });
  }

  await sendPrompt(page, confirmPrompt);
  await screenshot(page, "004-confirm-topic-sent");
  await expectAnyText(
    page,
    ["研究计划待确认", "Research Plan ready", "Research Plan"],
    "Research Plan ready",
    180_000
  );
  await screenshot(page, "005-research-plan-ready");

  if (expectedProfileLabel) {
    await selectProfile(page, expectedProfileLabel);
    await screenshot(page, "005b-profile-selected");
  }

  await expectButton(page, ["确认", "Confirm"]);
  await clickButton(page, ["确认", "Confirm"]);
  await expectAnyText(
    page,
    ["研究计划已确认", "Research Plan confirmed"],
    "Research Plan confirmed",
    180_000
  );
  await screenshot(page, "006-research-plan-confirmed");

  await expectButton(page, ["开始研究", "开始数据准备", "Start research"]);
  await clickButton(page, ["开始研究", "开始数据准备", "Start research"]);
  await screenshot(page, "007-start-research-clicked");

  await waitForDataPrepOrAnalysisState(page, 180_000);
  await screenshot(page, "008-data-prep-or-analysis-state");

  const terminal = await waitForTerminalOutcome(page);
  await screenshot(page, `009-terminal-${terminal}`);

  await collectButtonInventory(page, "final-button-inventory");
  await sweepPrimaryControls(page);
  await screenshot(page, "010-after-button-sweep");

  if (findings.some((finding) => finding.severity === "P1")) {
    process.exitCode = 1;
  }
} catch (error) {
  findings.push({
    severity: "P1",
    finding: "QA runner failed before reaching a terminal outcome.",
    evidence: error instanceof Error ? error.stack || error.message : String(error),
  });
  await screenshot(page, "999-runner-failure").catch(() => undefined);
  process.exitCode = 1;
} finally {
  await fs.writeFile(
    path.join(logsDir, "browser-console-events.json"),
    JSON.stringify(consoleEvents, null, 2)
  );
  await fs.writeFile(
    path.join(networkDir, "browser-network-events.json"),
    JSON.stringify(networkEvents, null, 2)
  );
  await fs.writeFile(
    path.join(reportsDir, "browser-findings.json"),
    JSON.stringify(findings, null, 2)
  );
  await browser.close();
}

async function prepareOutput() {
  await fs.rm(outputDir, { recursive: true, force: true });
  await fs.mkdir(screenshotsDir, { recursive: true });
  await fs.mkdir(logsDir, { recursive: true });
  await fs.mkdir(networkDir, { recursive: true });
  await fs.mkdir(reportsDir, { recursive: true });
}

async function sendPrompt(targetPage, text) {
  const input = targetPage.getByTestId("multimodal-input");
  const sendButton = targetPage.getByTestId("send-button");
  await input.fill(text);
  const deadline = Date.now() + 180_000;
  while (Date.now() < deadline) {
    try {
      await sendButton.waitFor({ state: "visible", timeout: 3000 });
      await sendButton.click({ timeout: 3000 });
    } catch {
      await targetPage.waitForTimeout(1000);
      continue;
    }

    const accepted = await isInputCleared(targetPage);
    if (accepted) {
      return;
    }
    await targetPage.waitForTimeout(1000);
  }
  throw new Error("Prompt was not accepted by the composer before timeout.");
}

async function isInputCleared(targetPage) {
  return targetPage.evaluate(() => {
    const field = document.querySelector('[data-testid="multimodal-input"]');
    if (!field) {
      return false;
    }
    if (field instanceof HTMLTextAreaElement || field instanceof HTMLInputElement) {
      return field.value.trim() === "";
    }
    return (field.textContent || "").trim() === "";
  });
}

async function expectText(targetPage, text, label, timeout = 60_000) {
  try {
    await targetPage.getByText(text, { exact: false }).first().waitFor({
      state: "visible",
      timeout,
    });
  } catch (error) {
    findings.push({
      severity: "P1",
      finding: `Missing expected text: ${label}`,
      evidence: error instanceof Error ? error.message : String(error),
    });
    throw error;
  }
}

async function expectAnyText(targetPage, texts, label, timeout = 60_000) {
  try {
    await waitForAnyText(targetPage, texts, timeout);
  } catch (error) {
    findings.push({
      severity: "P1",
      finding: `Missing expected text: ${label}`,
      evidence: error instanceof Error ? error.message : String(error),
    });
    throw error;
  }
}

async function expectButton(targetPage, names) {
  const nameList = Array.isArray(names) ? names : [names];
  try {
    await waitForNamedButton(targetPage, nameList, 60_000);
  } catch (error) {
    findings.push({
      severity: "P1",
      finding: `Missing expected button: ${nameList.join(" / ")}`,
      evidence: error instanceof Error ? error.message : String(error),
    });
    throw error;
  }
}

async function clickButton(targetPage, names) {
  const nameList = Array.isArray(names) ? names : [names];
  const deadline = Date.now() + 180_000;
  while (Date.now() < deadline) {
    const locator = await findNamedButton(targetPage, nameList, 3000);
    if (await locator.isEnabled().catch(() => false)) {
      await locator.click();
      return;
    }
    await targetPage.waitForTimeout(500);
  }
  throw new Error(`Button did not become enabled before timeout: ${nameList.join(" / ")}`);
}

async function waitForNamedButton(targetPage, names, timeout) {
  const deadline = Date.now() + timeout;
  while (Date.now() < deadline) {
    const locator = await findNamedButton(targetPage, names, 1000).catch(
      () => null
    );
    if (locator) {
      return locator;
    }
  }
  throw new Error(`Button was not visible before timeout: ${names.join(" / ")}`);
}

async function findNamedButton(targetPage, names, timeout) {
  for (const name of names) {
    const locator = targetPage.getByRole("button", { name }).first();
    if ((await locator.count()) > 0) {
      await locator.waitFor({ state: "visible", timeout });
      return locator;
    }
  }
  throw new Error(`No matching button: ${names.join(" / ")}`);
}

async function selectProfile(targetPage, profileLabel) {
  const trigger = targetPage.getByRole("combobox", { name: "切换分析画像" });
  await trigger.waitFor({ state: "visible", timeout: 60_000 });
  if ((await trigger.innerText()).includes(profileLabel)) {
    return;
  }
  await trigger.click();
  await targetPage.getByRole("option", { name: profileLabel }).click();
  await targetPage
    .getByRole("combobox", { name: "切换分析画像" })
    .waitFor({ state: "visible", timeout: 60_000 });
  await targetPage.waitForFunction(
    (label) => document.body?.innerText.includes(label),
    profileLabel,
    { timeout: 60_000 }
  );
}

async function waitForAnyText(targetPage, texts, timeout) {
  await targetPage.waitForFunction(
    (expectedTexts) => {
      const body = document.body?.innerText || "";
      return expectedTexts.some((text) => body.includes(text));
    },
    texts,
    { timeout }
  );
}

async function waitForDataPrepOrAnalysisState(targetPage, timeout) {
  const deadline = Date.now() + timeout;
  const expectedTexts = [
    "帖子：",
    "Posts:",
    "TIKHUB_API_KEY",
    "引擎失败",
    "报告已完成",
    "Report ready.",
    "Analysis did not produce",
  ];
  while (Date.now() < deadline) {
    const backendOutcome = await pollBackendTerminalOutcome();
    if (backendOutcome || observedSearchTaskId || observedReportTaskId) {
      return;
    }
    if (observedCrawlTaskId) {
      const crawlStatus = await getBackendJson(
        `/api/crawl/tasks/${encodeURIComponent(observedCrawlTaskId)}`
      );
      const crawlTask = crawlStatus?.task;
      if (crawlTask?.status && crawlTask.status !== "created") {
        return;
      }
    }
    const bodyText = await readBodyText(targetPage, 5000);
    if (expectedTexts.some((text) => bodyText.includes(text))) {
      return;
    }
    await targetPage.waitForTimeout(2500);
  }
  throw new Error("Data prep or analysis state did not become visible before timeout.");
}

async function waitForTerminalOutcome(targetPage) {
  const timeout = Date.now() + maxMinutes * 60_000;
  while (Date.now() < timeout) {
    const backendOutcome = await pollBackendTerminalOutcome();
    if (backendOutcome) {
      return backendOutcome;
    }

    const bodyText = await readBodyText(targetPage, 10_000);
    if (
      bodyText.includes("报告已完成") ||
      bodyText.includes("Argus 报告已完成") ||
      bodyText.includes("Report ready.") ||
      bodyText.includes("Argus Report Ready")
    ) {
      return "report-ready";
    }
    if (bodyText.includes("引擎失败") || bodyText.includes("Analysis did not produce")) {
      if (!/(query|insight|media)/i.test(bodyText)) {
        findings.push({
          severity: "P1",
          finding: "Analysis failed without visible engine-level detail.",
          evidence: bodyText.slice(0, 2000),
        });
      }
      return "engine-failed";
    }
    if (bodyText.includes("TIKHUB_API_KEY is required")) {
      return "missing-tikhub-key";
    }
    await targetPage.waitForTimeout(5000);
  }
  const backendOutcome = await pollBackendTerminalOutcome();
  if (backendOutcome) {
    return backendOutcome;
  }
  findings.push({
    severity: "info",
    finding: `Analysis was still running after ${maxMinutes} minutes.`,
    evidence: (await readBodyText(targetPage, 10_000)).slice(0, 2000),
  });
  return "analysis-still-running";
}

async function readBodyText(targetPage, timeout) {
  try {
    return await targetPage.locator("body").innerText({ timeout });
  } catch (error) {
    findings.push({
      severity: "P2",
      finding: "Could not read page body while waiting for terminal outcome.",
      evidence: error instanceof Error ? error.message : String(error),
    });
    return "";
  }
}

async function pollBackendTerminalOutcome() {
  if (observedCrawlTaskId && !observedSearchTaskId) {
    const crawlStatus = await getBackendJson(
      `/api/crawl/tasks/${encodeURIComponent(observedCrawlTaskId)}`
    );
    const crawlTask = crawlStatus?.task;
    if (crawlTask?.status === "reportable") {
      observedAnalysisQuery = observedAnalysisQuery || crawlTask.analysis_query || "";
      const startedSearch = await postBackendJson("/api/search", {
        query: observedAnalysisQuery,
        data_prep_task_id: observedCrawlTaskId,
      });
      if (startedSearch?.task_id) {
        observedSearchTaskId = String(startedSearch.task_id);
      }
    } else if (crawlTask?.status === "insufficient_data") {
      return "insufficient-data";
    } else if (crawlTask?.status === "failed") {
      findings.push({
        severity: "P1",
        finding: "TikHub data preparation failed.",
        evidence: JSON.stringify(crawlTask).slice(0, 2000),
      });
      return "missing-tikhub-key";
    }
  }

  if (!observedSearchTaskId) {
    return "";
  }
  const searchStatus = await getBackendJson(
    `/api/search/status/${encodeURIComponent(observedSearchTaskId)}`
  );
  if (searchStatus) {
    const status = String(searchStatus.status || "");
    if (searchStatus.report_task_id) {
      observedReportTaskId = String(searchStatus.report_task_id);
    }
    if (status === "error" || status === "blocked") {
      const message = searchStatus.error_message || searchStatus.blocked_reason || "";
      if (!/(query|insight|media)/i.test(message)) {
        findings.push({
          severity: "P1",
          finding: "Analysis failed without visible engine-level detail.",
          evidence: JSON.stringify(searchStatus).slice(0, 2000),
        });
      }
      return "engine-failed";
    }
  }

  if (!observedReportTaskId) {
    return "";
  }
  const reportProgress = await getBackendJson(
    `/api/report/progress/${encodeURIComponent(observedReportTaskId)}`
  );
  const task = reportProgress?.task || {};
  if (task.status === "completed" && task.report_file_ready) {
    return "report-ready";
  }
  if (task.status === "error") {
    findings.push({
      severity: "P1",
      finding: "Report generation failed.",
      evidence: JSON.stringify(task).slice(0, 2000),
    });
    return "engine-failed";
  }
  return "";
}

async function getBackendJson(pathname) {
  try {
    const response = await fetch(`http://localhost:5000${pathname}`);
    if (!response.ok) {
      return null;
    }
    return await response.json();
  } catch {
    return null;
  }
}

async function postBackendJson(pathname, payload) {
  try {
    const response = await fetch(`http://localhost:5000${pathname}`, {
      method: "POST",
      headers: { "content-type": "application/json", accept: "application/json" },
      body: JSON.stringify(payload),
    });
    if (!response.ok) {
      return null;
    }
    return await response.json();
  } catch {
    return null;
  }
}

async function collectButtonInventory(targetPage, label) {
  const inventory = await targetPage
    .locator('button, [role="button"], a[href], input[type="file"]')
    .evaluateAll((elements) =>
      elements.map((element, index) => {
        const rect = element.getBoundingClientRect();
        return {
          index,
          tag: element.tagName.toLowerCase(),
          text: element.textContent?.trim() || "",
          ariaLabel: element.getAttribute("aria-label") || "",
          testId: element.getAttribute("data-testid") || "",
          href: element.getAttribute("href") || "",
          visible:
            rect.width > 0 &&
            rect.height > 0 &&
            getComputedStyle(element).visibility !== "hidden" &&
            getComputedStyle(element).display !== "none" &&
            getComputedStyle(element).pointerEvents !== "none",
        };
      })
    );
  await fs.writeFile(
    path.join(reportsDir, `${label}.json`),
    JSON.stringify(inventory, null, 2)
  );
}

async function sweepPrimaryControls(targetPage) {
  await safeClick(targetPage, "button", "Copy user message");
  await safeClick(targetPage, "button", "Copy assistant response");
  await safeClick(targetPage, "button", "Upvote Response");
  await safeClick(targetPage, "button", "Downvote Response");
  await safeClick(targetPage, "button", "Open");
  await safeClick(targetPage, "button", "Revise");
  await safeClick(targetPage, "button", "Toggle Sidebar");
  await safeClick(targetPage, "button", "Open sidebar");
  await safeClick(targetPage, "button", "Guest");
  await safeClick(targetPage, "button", "Mimo V2.5 Pro");
  await safeClick(targetPage, "button", "Delete all");
  await safeClick(targetPage, "button", "Cancel");
}

async function safeClick(targetPage, role, name) {
  const locator = targetPage.getByRole(role, { name }).first();
  if ((await locator.count()) === 0) {
    return;
  }
  if (await locator.isDisabled().catch(() => false)) {
    return;
  }
  try {
    await locator.click({ timeout: 3000 });
  } catch (error) {
    findings.push({
      severity: "P2",
      finding: `Visible control could not be clicked: ${name}`,
      evidence: error instanceof Error ? error.message : String(error),
    });
  }
}

async function screenshot(targetPage, label) {
  screenshotIndex += 1;
  const file = path.join(
    screenshotsDir,
    `${String(screenshotIndex).padStart(3, "0")}-${label}.png`
  );
  await targetPage.screenshot({ path: file, fullPage: false, caret: "initial" });
}

async function saveResponseBody(response, entry) {
  const safeName = `${String(networkEvents.length).padStart(3, "0")}-${entry.method}-${new URL(entry.url).pathname
    .replace(/[^a-zA-Z0-9]+/g, "-")
    .replace(/^-|-$/g, "")}.txt`;
  try {
    const body = await response.text();
    await fs.writeFile(path.join(networkDir, safeName), body);
    entry.bodyFile = safeName;
    rememberTaskIds(entry.url, body);
  } catch {
    entry.bodyFile = "";
  }
}

function rememberTaskIds(url, body) {
  try {
    const payload = JSON.parse(body);
    if (url.includes("/api/argus/crawl") || url.includes("/api/crawl/tasks")) {
      const task = payload.task || {};
      if (task.task_id && String(task.task_id).startsWith("crawl_")) {
        observedCrawlTaskId = String(task.task_id);
        observedAnalysisQuery = String(task.analysis_query || observedAnalysisQuery || "");
      }
    }
    if (url.includes("/api/argus/search") || url.includes("/api/search")) {
      if (payload.task_id && String(payload.task_id).startsWith("search_")) {
        observedSearchTaskId = String(payload.task_id);
      }
      if (payload.report_task_id) {
        observedReportTaskId = String(payload.report_task_id);
      }
    }
    if (url.includes("/api/argus/report") || url.includes("/api/report")) {
      const taskId = payload.task?.task_id || payload.task_id;
      if (taskId && String(taskId).startsWith("report_")) {
        observedReportTaskId = String(taskId);
      }
    }
  } catch {
    // Non-JSON responses are saved for inspection but do not carry task ids.
  }
}
