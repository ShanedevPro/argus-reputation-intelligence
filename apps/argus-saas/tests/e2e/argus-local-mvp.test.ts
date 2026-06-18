import { expect, type Page, test } from "@playwright/test";

const REPORTABLE_PLAN = [
  "# Research Plan",
  "",
  "Event or issue: 交付争议",
  "Affected subject: 小米SU7",
  "Time window: 最近三个月",
  "Weibo clue: 小米SU7 交付争议",
  "Decision goal: 评估微博舆论风险，并形成可审阅的行动建议",
  "Known materials:",
  "- 公开微博讨论",
  "Preflight:",
  "",
  "Suggested analysis path:",
  "",
].join("\n");

const SPARSE_PLAN = [
  "# Research Plan",
  "",
  "Event or issue: 小众话题热度",
  "Affected subject: LABUBU",
  "Time window: 最近三个月",
  "Weibo clue: LABUBU 小众话题样本",
  "Decision goal: 验证证据不足时阻断正式分析",
  "Known materials:",
  "-",
  "Preflight:",
  "",
  "Suggested analysis path:",
  "",
].join("\n");

const WANG_HEDI_PARAGRAPH_PLAN = [
  "Research Plan: 王鹤棣",
  "",
  "Event or issue:",
  "",
  '王鹤棣在《亲爱的客栈2026》中因颁奖感到不适并发微博回应（"我当时确实不舒服"）引发"不舒服文学"出圈。',
  "",
  "Affected subject:",
  "",
  "王鹤棣",
  "",
  "Time window:",
  "",
  "2026年5月1日 — 2026年5月29日",
  "",
  "Weibo clue:",
  "",
  '关键词："不舒服文学"、"王鹤棣"、"我当时确实不舒服"、"亲爱的客栈"',
  "",
  "Known materials:",
  "",
  "《亲爱的客栈2026》收官颁奖视频片段",
  "王鹤棣28字微博原文",
].join("\n");

test.beforeEach(async ({ page }) => {
  await mockDatabaseBackedRoutes(page);
});

test("runs mocked Argus workflow to report artifact", async ({ page }) => {
  await mockChatResearchPlan(page, REPORTABLE_PLAN);
  await mockReportableWorkflow(page);

  await page.goto("/");
  await page
    .getByTestId("multimodal-input")
    .fill("研究小米SU7最近三个月交付争议在微博上的舆论风险");
  await page.getByTestId("send-button").click();

  await expect(page.getByText("研究计划待确认")).toBeVisible();
  await expect(page.getByText("通用事件风险")).toBeVisible();
  await page.getByLabel("切换分析画像").click();
  await page.getByRole("option", { name: "企业公关舆情" }).click();
  await expect(
    page.getByRole("combobox", { name: "切换分析画像" })
  ).toContainText("企业公关舆情");
  await page.getByRole("button", { name: "确认" }).click();
  await expect(page.getByText("研究计划已确认")).toBeVisible();

  await page.getByRole("button", { name: "开始研究" }).click();

  await expect(page.getByText("报告已完成。")).toBeVisible();
  await expect(page.getByTestId("artifact")).toContainText(
    "Argus 报告已完成"
  );
  await expect(page.getByTestId("artifact")).toContainText("打开 HTML 报告");
  await expect(page.getByTestId("artifact")).toContainText("分析画像：企业公关舆情");
  await expect(page.getByTestId("artifact")).toContainText("微博样本：30 条帖子 / 120 条一级评论");
});

test("unlocks workflow for paragraph-style Research Plan output", async ({
  page,
}) => {
  await mockChatResearchPlan(page, WANG_HEDI_PARAGRAPH_PLAN);

  await page.goto("/");
  await page
    .getByTestId("multimodal-input")
    .fill(
      "请以王鹤棣不舒服文学事件创建 Research Plan，主体王鹤棣，时间窗口2026年5月1日至2026年5月29日"
    );
  await page.getByTestId("send-button").click();

  await expect(page.getByText("研究计划待确认")).toBeVisible();
  await expect(
    page.getByRole("button", { name: "Copy user message" })
  ).toBeVisible();
  await expect(
    page.getByRole("button", { name: "Copy assistant response" })
  ).toBeVisible();
  await expect(page.getByRole("button", { name: "确认" })).toBeVisible();
  await page.getByRole("button", { name: "确认" }).click();
  await expect(page.getByText("研究计划已确认")).toBeVisible();
  await expect(
    page.getByRole("button", { name: "开始研究" })
  ).toBeVisible();
});

test("blocks analysis when mocked Weibo data is insufficient", async ({
  page,
}) => {
  let searchCalls = 0;

  await mockChatResearchPlan(page, SPARSE_PLAN);
  await mockInsufficientDataWorkflow(page, () => {
    searchCalls += 1;
  });

  await page.goto("/");
  await page
    .getByTestId("multimodal-input")
    .fill("研究LABUBU最近三个月在微博上的热度和负面舆情");
  await page.getByTestId("send-button").click();

  await expect(page.getByText("研究计划待确认")).toBeVisible();
  await page.getByRole("button", { name: "确认" }).click();
  await expect(page.getByText("研究计划已确认")).toBeVisible();

  await page.getByRole("button", { name: "开始研究" }).click();

  await expect(
    page.getByText("请收窄事件边界，或选择微博讨论量更高的议题。")
  ).toBeVisible();
  await expect(page.getByText(/帖子：\s*3\s*·\s*评论：\s*1/)).toBeVisible();
  await expect(page.getByText(/样本说明：\s*insufficient_posts/)).toBeVisible();
  expect(searchCalls).toBe(0);
});

async function mockChatResearchPlan(page: Page, planMarkdown: string) {
  let responseCount = 0;

  await page.route("**/api/chat", async (route) => {
    responseCount += 1;
    const sse = [
      {
        type: "start",
        messageId: `00000000-0000-4000-8000-${String(responseCount).padStart(
          12,
          "0"
        )}`,
      },
      { type: "text-start", id: `text-${responseCount}` },
      {
        type: "text-delta",
        id: `text-${responseCount}`,
        delta: planMarkdown,
      },
      { type: "text-end", id: `text-${responseCount}` },
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
      body: `${sse}data: [DONE]\n\n`,
    });
  });
}

async function mockDatabaseBackedRoutes(page: Page) {
  await page.route("**/api/history*", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify([]),
    });
  });

  await page.route("**/api/messages*", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify([]),
    });
  });

  await page.route("**/api/suggestions*", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify([]),
    });
  });

  await page.route("**/api/document?id=*", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify([]),
    });
  });
}

async function mockReportableWorkflow(page: Page) {
  let savedDocument = {
    content: "",
    createdAt: new Date().toISOString(),
    id: "doc_1",
    kind: "text",
    title: "Argus Report",
    userId: "user_1",
  };

  await page.route("**/api/argus/crawl", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        success: true,
        task: {
          task_id: "crawl_1",
          analysis_query: "小米SU7 交付争议 最近三个月",
          data_request: "小米SU7 交付争议 最近三个月",
          platforms: ["wb"],
          provider: "tikhub",
          caps: {},
          status: "reportable",
          error_message: "",
          next_action: "微博数据已达到报告分析门槛。",
          status_url: "/api/argus/crawl/crawl_1",
          reportability: {
            status: "reportable",
            can_start_analysis: true,
            counts: { posts: 30, comments: 120 },
          },
        },
      }),
    });
  });

  await page.route("**/api/argus/search", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        success: true,
        task_id: "search_1",
        query: "小米SU7 交付争议 最近三个月",
        status: "completed",
        report_task_id: "report_1",
      }),
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
          "<!doctype html><html><body>Argus HTML Report</body></html>",
        task: buildReportTask(),
      }),
    });
  });

  await page.route("**/api/document?id=*", async (route) => {
    if (route.request().method() === "POST") {
      const payload = route.request().postDataJSON() as {
        content: string;
        kind: string;
        title: string;
      };
      savedDocument = {
        ...savedDocument,
        content: payload.content,
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

async function mockInsufficientDataWorkflow(
  page: Page,
  onUnexpectedSearch: () => void
) {
  await page.route("**/api/argus/crawl", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        success: true,
        task: {
          task_id: "crawl_sparse",
          analysis_query: "LABUBU 小众话题热度 最近三个月",
          data_request: "LABUBU 小众话题热度 最近三个月",
          platforms: ["wb"],
          provider: "tikhub",
          caps: {},
          status: "insufficient_data",
          error_message: "",
          next_action:
            "请收窄事件边界，或选择微博讨论量更高的议题。",
          status_url: "/api/argus/crawl/crawl_sparse",
          reportability: {
            status: "insufficient_data",
            can_start_analysis: false,
            stop_reason: "insufficient_posts",
            counts: { posts: 3, comments: 1 },
          },
        },
      }),
    });
  });

  await page.route("**/api/argus/search", async (route) => {
    onUnexpectedSearch();
    await route.fulfill({
      status: 500,
      contentType: "application/json",
      body: JSON.stringify({ error: "Search should not be called." }),
    });
  });
}

function buildReportTask() {
  return {
    task_id: "report_1",
    query: "小米SU7 交付争议 最近三个月",
    status: "completed",
    progress: 100,
    error_message: "",
    has_result: true,
    report_file_ready: true,
    report_file_name: "report.html",
    report_file_path: "final_reports/report.html",
    markdown_file_ready: false,
    markdown_file_name: "",
    markdown_file_path: "",
    pdf_file_ready: false,
    pdf_file_name: "",
    pdf_file_path: "",
    export_errors: [],
  };
}
