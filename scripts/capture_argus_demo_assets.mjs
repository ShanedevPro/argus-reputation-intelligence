#!/usr/bin/env node
import fs from "node:fs/promises";
import { existsSync } from "node:fs";
import { createRequire } from "node:module";
import path from "node:path";
import { spawn } from "node:child_process";
import { fileURLToPath, pathToFileURL } from "node:url";

const rootDir = path.resolve(
  path.dirname(fileURLToPath(import.meta.url)),
  ".."
);
const appDir = path.join(rootDir, "apps", "argus-saas");
const requireFromArgusSaas = createRequire(
  pathToFileURL(path.join(appDir, "package.json"))
);
const { chromium } = requireFromArgusSaas("@playwright/test");

const port = Number(process.env.ARGUS_DEMO_CAPTURE_PORT || "3099");
const baseURL = `http://127.0.0.1:${port}`;
const screenshotsDir = path.join(rootDir, "assets", "screenshots");
const demoDir = path.join(rootDir, "assets", "demo");
const videoName = "argus-curated-live-demo";
const generatedAssetDirs = [screenshotsDir, demoDir];

const reportPlan = [
  "# 研究计划",
  "",
  "**事件或议题：** 小米SU7 碰撞起火事故",
  "",
  "**受影响主体：** 小米汽车",
  "",
  "**时间窗口：** 2025年3月 - 2025年4月",
  "",
  "**分析画像：** 企业公关舆情",
  "",
  "**微博线索：** 小米SU7 碰撞起火 事故 品牌回应",
  "",
  "**决策目标：** 评估企业公关舆情风险，并形成可审阅的行动建议",
  "",
  "**已知材料：**",
  "- 公开新闻报道",
  "- 微博公开讨论样本",
  "",
  "**预检结果：** 可进入分析",
  "",
  "**建议分析路径：**",
  "- 事实核验",
  "- 传播链路",
  "- 情绪与风险研判",
  "- 行动建议",
].join("\n");

for (const dir of generatedAssetDirs) {
  await fs.rm(dir, { recursive: true, force: true });
}
await fs.mkdir(screenshotsDir, { recursive: true });
await fs.mkdir(demoDir, { recursive: true });

const server = await startFrontend();
let browser;

try {
  const executablePath = findChromeExecutable();
  browser = await chromium.launch({
    headless: true,
    ...(executablePath ? { executablePath } : {}),
  });
  await warmFrontend(browser);
  const videoContext = await browser.newContext({
    viewport: { width: 1440, height: 1000 },
    deviceScaleFactor: 1,
    recordVideo: { dir: demoDir, size: { width: 1440, height: 1000 } },
  });
  const videoPage = await videoContext.newPage();
  videoPage.setDefaultTimeout(120_000);
  videoPage.setDefaultNavigationTimeout(120_000);
  await mockFrontendRoutes(videoPage);
  await captureFrontendWorkflow(videoPage);
  await videoContext.close();

  const screenshotContext = await browser.newContext({
    viewport: { width: 1440, height: 1000 },
    deviceScaleFactor: 1,
  });
  const screenshotPage = await screenshotContext.newPage();
  screenshotPage.setDefaultTimeout(120_000);
  screenshotPage.setDefaultNavigationTimeout(120_000);
  await captureSampleReportScreenshots(screenshotPage);
  await screenshotContext.close();

  await browser.close();
  browser = undefined;
  await convertLatestWebmToMp4();
  await captureThumbnail();
} finally {
  if (browser) {
    await browser.close();
  }
  await stopFrontend(server);
}

async function mockFrontendRoutes(page) {
  await mockDatabaseBackedRoutes(page);
  await mockChatResearchPlan(page);
  await mockReportableWorkflow(page);
}

async function warmFrontend(browser) {
  const context = await browser.newContext({
    viewport: { width: 1440, height: 1000 },
    deviceScaleFactor: 1,
  });
  const page = await context.newPage();
  page.setDefaultTimeout(120_000);
  page.setDefaultNavigationTimeout(120_000);
  await mockFrontendRoutes(page);
  await page.goto(baseURL, { waitUntil: "load" });
  await page.getByTestId("multimodal-input").waitFor({ state: "visible" });
  await context.close();
}

async function mockChatResearchPlan(page) {
  let chatCallCount = 0;
  await page.route("**/api/chat", async (route) => {
    chatCallCount += 1;
    const responseText =
      chatCallCount === 1 ? reportPlan : "研究计划已确认，可以开始正式分析。";
    const chunks = [
      { type: "start", messageId: "00000000-0000-4000-8000-000000000001" },
      { type: "text-start", id: "text-1" },
      { type: "text-delta", id: "text-1", delta: responseText },
      { type: "text-end", id: "text-1" },
      { type: "finish", finishReason: "stop" },
    ]
      .map((chunk) => `data: ${JSON.stringify(chunk)}\n\n`)
      .join("");

    await route.fulfill({
      status: 200,
      headers: {
        "cache-control": "no-cache",
        connection: "keep-alive",
        "content-type": "text/event-stream",
        "x-vercel-ai-ui-message-stream": "v1",
      },
      body: `${chunks}data: [DONE]\n\n`,
    });
  });
}

async function mockDatabaseBackedRoutes(page) {
  let savedDocument = {
    content: "",
    createdAt: new Date("2026-06-13T00:00:00.000Z").toISOString(),
    id: "doc_1",
    kind: "text",
    title: "Argus Report",
    userId: "user_1",
  };

  for (const pattern of [
    "**/api/history*",
    "**/api/messages*",
    "**/api/suggestions*",
  ]) {
    await page.route(pattern, async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify([]),
      });
    });
  }

  await page.route("**/api/document?id=*", async (route) => {
    if (route.request().method() === "POST") {
      const payload = route.request().postDataJSON();
      savedDocument = {
        ...savedDocument,
        content: payload.content,
        id: new URL(route.request().url()).searchParams.get("id") || "doc_1",
        kind: payload.kind,
        title: payload.title,
      };
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(savedDocument),
      });
      return;
    }

    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify([savedDocument]),
    });
  });
}

async function mockReportableWorkflow(page) {
  await page.route("**/api/argus/crawl", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        success: true,
        task: buildCrawlTask(),
      }),
    });
  });

  await page.route("**/api/argus/crawl/crawl_1", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        success: true,
        task: buildCrawlTask(),
      }),
    });
  });

  await page.route("**/api/argus/search", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(buildSearchTask()),
    });
  });

  await page.route("**/api/argus/search/search_1", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(buildSearchTask()),
    });
  });

  await page.route("**/api/argus/report/report_1/progress", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        success: true,
        task: buildReportTask(),
      }),
    });
  });

  await page.route("**/api/argus/report/report_1/result", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        success: true,
        html_content:
          "<!doctype html><html><body>Argus sanitized sample report is ready.</body></html>",
        task: buildReportTask(),
      }),
    });
  });
}

function buildCrawlTask() {
  return {
    task_id: "crawl_1",
    analysis_query: "小米SU7 碰撞起火事故 小米汽车 2025年3月 - 2025年4月",
    data_request: "小米SU7 碰撞起火事故 品牌回应",
    platforms: ["wb"],
    provider: "tikhub",
    caps: {},
    status: "reportable",
    error_message: "",
    next_action: "微博数据已达到报告分析门槛。",
    status_url: "/api/argus/crawl/crawl_1",
    evidence_manifest: {
      sample_boundary: {
        comment_depth: "first_level_only",
        source: "public_sample",
      },
      counts: { posts: 30, comments: 120 },
      keywords: ["小米SU7", "碰撞起火", "品牌回应"],
    },
    reportability: {
      status: "reportable",
      can_start_analysis: true,
      counts: { posts: 30, comments: 120 },
    },
  };
}

function buildSearchTask() {
  return {
    success: true,
    task_id: "search_1",
    query: "小米SU7 碰撞起火事故 品牌回应",
    status: "completed",
    report_task_id: "report_1",
    data_ready: true,
    engines: {
      insight: { status: "completed", output_file: "sanitized-insight.json" },
      media: { status: "completed", output_file: "sanitized-media.json" },
      query: { status: "completed", output_file: "sanitized-query.json" },
    },
  };
}

function buildReportTask() {
  return {
    task_id: "report_1",
    query: "小米SU7 碰撞起火事故 品牌回应",
    status: "completed",
    progress: 100,
    error_message: "",
    has_result: true,
    report_file_ready: true,
    report_file_name: "report.html",
    report_file_path: "sample_reports/xiaomi-su7-enterprise-pr/report.html",
    markdown_file_ready: true,
    markdown_file_name: "report.md",
    markdown_file_path: "sample_reports/xiaomi-su7-enterprise-pr/report.md",
    pdf_file_ready: true,
    pdf_file_name: "report.pdf",
    pdf_file_path: "sample_reports/xiaomi-su7-enterprise-pr/report.pdf",
    export_errors: [],
  };
}

async function captureFrontendWorkflow(page) {
  const prompt =
    "请分析小米SU7碰撞起火事故的企业公关舆情风险，并生成可供管理层审阅的中文报告。";

  await page.goto(baseURL, { waitUntil: "load" });
  await page.getByTestId("multimodal-input").waitFor({ state: "visible" });
  await pauseForReading(page, 5000);
  await typePromptSlowly(page, prompt);
  await page.waitForFunction(() => {
    const input = document.querySelector("[data-testid='multimodal-input']");
    const button = document.querySelector("[data-testid='send-button']");
    return (
      input instanceof HTMLTextAreaElement &&
      input.value.trim().length > 0 &&
      button instanceof HTMLButtonElement &&
      !button.disabled
    );
  });
  await pauseForReading(page, 4000);
  await page.getByTestId("send-button").click();
  await page.getByText("研究计划待确认").waitFor({ timeout: 90_000 });
  await scrollViewportToTop(page);
  await pauseForReading(page, 18000);
  await page.screenshot({
    path: path.join(screenshotsDir, "argus-workflow-plan.png"),
    fullPage: false,
  });

  await page.getByLabel("切换分析画像").click();
  await pauseForReading(page, 8000);
  await page.getByRole("option", { name: "企业公关舆情" }).click();
  await pauseForReading(page, 9000);
  await page.getByRole("button", { name: "确认" }).click();
  await pauseForReading(page, 10000);
  await page.getByRole("button", { name: "开始研究" }).click();
  await page
    .getByText("正在使用微博样本运行多引擎分析链路。")
    .waitFor({ timeout: 90_000 });
  await pauseForReading(page, 18000);
  await page.getByText("报告已完成。").waitFor({ timeout: 90_000 });
  await scrollViewportToTop(page);
  await pauseForReading(page, 22000);
  await page.screenshot({
    path: path.join(screenshotsDir, "argus-workflow-report-ready.png"),
    fullPage: false,
  });
}

async function scrollViewportToTop(page) {
  await page.evaluate(() => {
    window.scrollTo(0, 0);
    for (const element of document.querySelectorAll("*")) {
      if (!(element instanceof HTMLElement)) {
        continue;
      }
      const style = window.getComputedStyle(element);
      if (
        (style.overflowY === "auto" || style.overflowY === "scroll") &&
        element.scrollTop > 0
      ) {
        element.scrollTop = 0;
      }
    }
  });
}

async function pauseForReading(page, milliseconds = 3500) {
  await page.waitForTimeout(milliseconds);
}

async function typePromptSlowly(page, prompt) {
  const input = page.getByTestId("multimodal-input");
  await input.click();
  await input.fill("");
  if (typeof input.pressSequentially === "function") {
    await input.pressSequentially(prompt, { delay: 22 });
    return;
  }
  await page.keyboard.type(prompt, { delay: 22 });
}

async function captureSampleReportScreenshots(page) {
  for (const [name, relPath] of [
    [
      "report-wang-hedi-executive-brief.png",
      "sample_reports/wang-hedi-artist-profile/report.html",
    ],
    [
      "report-xiaomi-su7-executive-brief.png",
      "sample_reports/xiaomi-su7-enterprise-pr/report.html",
    ],
  ]) {
    await page.goto(pathToFileURL(path.join(rootDir, relPath)).href, {
      waitUntil: "networkidle",
    });
    await page.waitForTimeout(2500);
    await page.screenshot({
      path: path.join(screenshotsDir, name),
      fullPage: false,
    });
    await scrollForVideo(page);
  }
}

async function scrollForVideo(page) {
  for (const amount of [500, 500, 650, 650, -450, 600, 700]) {
    await page.mouse.wheel(0, amount);
    await page.waitForTimeout(2500);
  }
}

function findChromeExecutable() {
  const candidates = [
    process.env.CHROME_EXECUTABLE_PATH,
    "/usr/bin/google-chrome-stable",
    "/usr/bin/google-chrome",
    "/usr/bin/chromium-browser",
  ].filter(Boolean);
  return candidates.find((candidate) => existsSync(candidate));
}

async function waitForServer(url) {
  const deadline = Date.now() + 120_000;
  while (Date.now() < deadline) {
    try {
      const response = await fetch(url);
      if (response.ok) return;
    } catch {}
    await new Promise((resolve) => setTimeout(resolve, 1000));
  }
  throw new Error(`Timed out waiting for ${url}`);
}

async function startFrontend() {
  const child = spawn(findExecutableOnPath("pnpm"), ["dev"], {
    cwd: appDir,
    detached: process.platform !== "win32",
    stdio: ["ignore", "pipe", "pipe"],
    env: buildFrontendEnv({
      PORT: String(port),
      PLAYWRIGHT: "True",
      NEXT_TELEMETRY_DISABLED: "1",
      AUTH_SECRET: "argus-demo-capture-not-for-production-32-bytes",
      BETTAFISH_BACKEND_URL: "http://127.0.0.1:5000",
      NEXT_PUBLIC_BETTAFISH_BACKEND_URL: "http://127.0.0.1:5000",
    }),
  });
  child.stdout.on("data", (chunk) => process.stdout.write(chunk));
  child.stderr.on("data", (chunk) => process.stderr.write(chunk));
  await waitForServer(`${baseURL}/ping`);
  return child;
}

function findExecutableOnPath(name) {
  const explicitPath = process.env.ARGUS_DEMO_CAPTURE_PNPM;
  if (explicitPath && existsSync(explicitPath)) {
    return explicitPath;
  }

  for (const dir of (process.env.PATH ?? "").split(path.delimiter)) {
    const candidate = path.join(dir, name);
    if (existsSync(candidate)) {
      return candidate;
    }
  }

  return name;
}

function buildFrontendEnv(overrides) {
  const env = {
    CI: process.env.CI ?? "1",
    COREPACK_HOME: "/tmp/argus-demo-capture-corepack",
    LANG: process.env.LANG ?? "C.UTF-8",
    LC_ALL: process.env.LC_ALL ?? "C.UTF-8",
    PATH: "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin",
    TEMP: "/tmp",
    TERM: process.env.TERM ?? "xterm-256color",
    TMP: "/tmp",
    TMPDIR: "/tmp",
  };
  return {
    ...env,
    HOME: "/tmp/argus-demo-capture-home",
    LOGNAME: "argus-demo",
    USER: "argus-demo",
    XDG_CACHE_HOME: "/tmp/argus-demo-capture-cache",
    ...overrides,
  };
}

async function stopFrontend(child) {
  if (child.exitCode !== null) {
    return;
  }
  signalFrontend(child, "SIGTERM");
  await new Promise((resolve) => {
    const timeout = setTimeout(() => {
      signalFrontend(child, "SIGKILL");
      resolve();
    }, 5000);
    child.once("exit", () => {
      clearTimeout(timeout);
      resolve();
    });
  });
}

function signalFrontend(child, signal) {
  try {
    if (process.platform === "win32") {
      child.kill(signal);
      return;
    }
    process.kill(-child.pid, signal);
  } catch (error) {
    if (error?.code !== "ESRCH") {
      throw error;
    }
  }
}

async function convertLatestWebmToMp4() {
  const entries = await fs.readdir(demoDir);
  const webmFiles = entries
    .filter((entry) => entry.endsWith(".webm"))
    .sort();
  if (webmFiles.length === 0) throw new Error("No Playwright video was recorded.");
  const webmPath = path.join(demoDir, webmFiles[webmFiles.length - 1]);
  const mp4Path = path.join(demoDir, `${videoName}.mp4`);
  await run("ffmpeg", [
    "-y",
    "-ss",
    "3",
    "-i",
    webmPath,
    "-vf",
    "scale=1280:-2,fps=24",
    "-c:v",
    "libx264",
    "-preset",
    "veryfast",
    "-crf",
    "28",
    "-movflags",
    "+faststart",
    "-an",
    mp4Path,
  ]);
  await fs.rm(webmPath, { force: true });
}

async function captureThumbnail() {
  await fs.copyFile(
    path.join(screenshotsDir, "argus-workflow-report-ready.png"),
    path.join(demoDir, `${videoName}-thumbnail.png`)
  );
}

async function run(command, args) {
  await new Promise((resolve, reject) => {
    const child = spawn(command, args, {
      cwd: rootDir,
      stdio: ["ignore", "inherit", "inherit"],
    });
    child.on("error", reject);
    child.on("exit", (code) => {
      if (code === 0) {
        resolve();
        return;
      }
      reject(new Error(`${command} exited with code ${code}`));
    });
  });
}
