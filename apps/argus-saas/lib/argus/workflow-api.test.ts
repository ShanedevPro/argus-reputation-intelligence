import assert from "node:assert/strict";
import test from "node:test";
import {
  buildArgusReportHtmlPath,
  createCrawlTask,
  getCrawlTask,
  getReportProgress,
  getReportResult,
  getSearchStatus,
  startSearch,
} from "./workflow-api";

test("workflow API calls the expected local routes", async () => {
  const originalFetch = globalThis.fetch;
  const calls: Array<{ url: string; init?: RequestInit }> = [];

  globalThis.fetch = (async (url: string | URL, init?: RequestInit) => {
    calls.push({ url: String(url), init });
    return new Response(
      JSON.stringify({
        success: true,
        task: { task_id: "crawl_1", status: "reportable" },
        task_id: "search_1",
        status: "completed",
      }),
      { status: 200, headers: { "content-type": "application/json" } }
    );
  }) as typeof fetch;

  try {
    await createCrawlTask({
      analysis_query: "小米SU7 交付争议 最近三个月",
      data_request: {
        eventOrIssue: "交付争议",
        affectedSubject: "小米SU7",
        timeWindow: "最近三个月",
      },
      platforms: ["wb"],
    });
    await getCrawlTask("crawl_1");
    await startSearch("小米SU7 交付争议 最近三个月", "crawl_1");
    await startSearch("小米SU7 交付争议 最近三个月", "crawl_1", {
      insight: { output_file: "insight.md" },
    });
    await getSearchStatus("search_1");
    await getReportProgress("report_1");
    await getReportResult("report_1");
  } finally {
    globalThis.fetch = originalFetch;
  }

  assert.equal(calls[0]?.url, "/api/argus/crawl");
  assert.equal(calls[1]?.url, "/api/argus/crawl/crawl_1");
  assert.equal(calls[2]?.url, "/api/argus/search");
  assert.equal(calls[3]?.url, "/api/argus/search");
  assert.equal(calls[4]?.url, "/api/argus/search/search_1");
  assert.equal(calls[5]?.url, "/api/argus/report/report_1/progress");
  assert.equal(calls[6]?.url, "/api/argus/report/report_1/result");
  assert.equal(
    buildArgusReportHtmlPath("report_1"),
    "/api/argus/report/report_1/html"
  );

  assert.equal(calls[0]?.init?.method, "POST");
  assert.equal(calls[2]?.init?.body, JSON.stringify({
    query: "小米SU7 交付争议 最近三个月",
    data_prep_task_id: "crawl_1",
  }));
  assert.equal(calls[3]?.init?.body, JSON.stringify({
    query: "小米SU7 交付争议 最近三个月",
    data_prep_task_id: "crawl_1",
    engine_artifacts: {
      insight: { output_file: "insight.md" },
    },
  }));
});
