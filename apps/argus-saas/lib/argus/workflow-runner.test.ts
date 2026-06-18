import assert from "node:assert/strict";
import test from "node:test";
import {
  collectResumableEngineArtifacts,
  createArgusWorkflowRunner,
} from "./workflow-runner";

const request = {
  eventOrIssue: "交付争议",
  affectedSubject: "小米SU7",
  timeWindow: "最近三个月",
  weiboClue: "小米SU7",
};

test("collects only completed evidence-ready engine artifacts", () => {
  const artifacts = collectResumableEngineArtifacts({
    success: true,
    task_id: "search_1",
    query: "王鹤棣 不舒服文学",
    status: "error",
    engines: {
      query: {
        status: "completed",
        evidence_status: "ready",
        output_file: "  query.md  ",
      },
      media: {
        status: "completed",
        evidence_status: "no_data",
        output_file: "media.md",
      },
      insight: {
        status: "completed",
        evidence_status: "ready",
        output_file: "insight.md",
      },
      forum: {
        status: "completed",
        evidence_status: "ready",
        output_file: "forum.md",
      },
    },
  });

  assert.deepEqual(artifacts, {
    query: { output_file: "query.md" },
    insight: { output_file: "insight.md" },
  });
});

test("collects no artifact for empty or incomplete engine outputs", () => {
  assert.deepEqual(collectResumableEngineArtifacts(undefined), {});
  assert.deepEqual(
    collectResumableEngineArtifacts({
      success: true,
      task_id: "search_1",
      query: "王鹤棣 不舒服文学",
      status: "error",
      engines: {
        query: {
          status: "completed",
          evidence_status: "ready",
          output_file: "   ",
        },
        media: {
          status: "running",
          evidence_status: "ready",
          output_file: "media.md",
        },
        insight: {
          status: "completed",
          evidence_status: "pending",
          output_file: "insight.md",
        },
      },
    }),
    {}
  );
});

test("runner completes reportable workflow", async () => {
  const states: string[] = [];
  const runner = createArgusWorkflowRunner({
    pollIntervalMs: 1,
    api: {
      createCrawlTask: async () => ({
        success: true,
        task: { task_id: "crawl_1", status: "collecting" },
      }) as any,
      getCrawlTask: async () => ({
        success: true,
        task: {
          task_id: "crawl_1",
          status: "reportable",
          reportability: {
            status: "reportable",
            can_start_analysis: true,
            counts: { posts: 30, comments: 120 },
          },
          evidence_manifest: {
            counts: { posts: 29, comments: 115 },
            sample_boundary: { comment_depth: "first_level_only" },
          },
        },
      }) as any,
      startSearch: async () =>
        ({
          success: true,
          task_id: "search_1",
          query: "小米SU7 交付争议 最近三个月",
          status: "running",
        }) as any,
      getSearchStatus: async () =>
        ({
          success: true,
          task_id: "search_1",
          query: "小米SU7 交付争议 最近三个月",
          status: "completed",
          report_task_id: "report_1",
        }) as any,
      getReportProgress: async () =>
        ({
          success: true,
          task: {
            task_id: "report_1",
            query: "小米SU7 交付争议 最近三个月",
            status: "completed",
            progress: 100,
            report_file_ready: true,
          },
        }) as any,
      getReportResult: async () =>
        ({
          success: true,
          html_content: "<!doctype html><html><body>Report</body></html>",
          task: {
            task_id: "report_1",
            query: "小米SU7 交付争议 最近三个月",
            status: "completed",
            progress: 100,
            report_file_ready: true,
            report_file_name: "report.html",
            report_file_path: "final_reports/report.html",
          },
        }) as any,
    },
  });

  const finalState = await runner.run(request, {
    onState: (state) => states.push(state.status),
  });

  assert.equal(finalState.status, "report_ready");
  assert.equal(finalState.analysisQuery, "小米SU7 交付争议 最近三个月");
  assert.equal(finalState.crawlTask?.task_id, "crawl_1");
  assert.equal(finalState.crawlTask?.evidence_manifest?.counts?.posts, 29);
  assert.equal(finalState.searchTask?.task_id, "search_1");
  assert.equal(finalState.reportResult?.task.task_id, "report_1");
  assert.ok(states.includes("preparing_data"));
  assert.ok(states.includes("running_analysis"));
  assert.ok(states.includes("generating_report"));
});

test("runner sends a normalized default profile to data prep", async () => {
  let sentDataRequest: any = null;
  const runner = createArgusWorkflowRunner({
    pollIntervalMs: 1,
    api: {
      createCrawlTask: async (payload: any) => {
        sentDataRequest = payload.data_request;
        return {
          success: true,
          task: { task_id: "crawl_1", status: "reportable" },
        } as any;
      },
      getCrawlTask: async () => {
        throw new Error("crawl status should not be polled");
      },
      startSearch: async () =>
        ({
          success: true,
          task_id: "search_1",
          query: "小米SU7 交付争议 最近三个月",
          status: "completed",
          report_task_id: "report_1",
        }) as any,
      getSearchStatus: async () => {
        throw new Error("search status should not be polled");
      },
      getReportProgress: async () =>
        ({
          success: true,
          task: {
            task_id: "report_1",
            query: "小米SU7 交付争议 最近三个月",
            status: "completed",
            progress: 100,
            report_file_ready: true,
          },
        }) as any,
      getReportResult: async () =>
        ({
          success: true,
          html_content: "<!doctype html><html><body>Report</body></html>",
          task: {
            task_id: "report_1",
            query: "小米SU7 交付争议 最近三个月",
            status: "completed",
            progress: 100,
            report_file_ready: true,
            report_file_name: "report.html",
            report_file_path: "final_reports/report.html",
          },
        }) as any,
    },
  });

  await runner.run(request, { onState: () => undefined });

  assert.equal(sentDataRequest.profileId, "generic_event_risk");
});

test("runner passes engine artifacts when starting search", async () => {
  let sentEngineArtifacts: any = null;
  const engineArtifacts = {
    insight: { output_file: "insight.md" },
  };
  const runner = createArgusWorkflowRunner({
    pollIntervalMs: 1,
    api: {
      createCrawlTask: async () => ({
        success: true,
        task: { task_id: "crawl_1", status: "reportable" },
      }) as any,
      getCrawlTask: async () => {
        throw new Error("crawl status should not be polled");
      },
      startSearch: async (_query: string, _taskId: string, artifacts: any) => {
        sentEngineArtifacts = artifacts;
        return {
          success: true,
          task_id: "search_1",
          query: "小米SU7 交付争议 最近三个月",
          status: "completed",
          report_task_id: "report_1",
        } as any;
      },
      getSearchStatus: async () => {
        throw new Error("search status should not be polled");
      },
      getReportProgress: async () =>
        ({
          success: true,
          task: {
            task_id: "report_1",
            query: "小米SU7 交付争议 最近三个月",
            status: "completed",
            progress: 100,
            report_file_ready: true,
          },
        }) as any,
      getReportResult: async () =>
        ({
          success: true,
          html_content: "<!doctype html><html><body>Report</body></html>",
          task: {
            task_id: "report_1",
            query: "小米SU7 交付争议 最近三个月",
            status: "completed",
            progress: 100,
            report_file_ready: true,
            report_file_name: "report.html",
            report_file_path: "final_reports/report.html",
          },
        }) as any,
    },
  });

  await runner.run(request, {
    engineArtifacts,
    onState: () => undefined,
  });

  assert.deepEqual(sentEngineArtifacts, engineArtifacts);
});

test("runner blocks when Weibo data is insufficient", async () => {
  let searchStarted = false;
  const runner = createArgusWorkflowRunner({
    pollIntervalMs: 1,
    api: {
      createCrawlTask: async () => ({
        success: true,
        task: { task_id: "crawl_1", status: "collecting" },
      }) as any,
      getCrawlTask: async () => ({
        success: true,
        task: {
          task_id: "crawl_1",
          status: "insufficient_data",
          next_action: "Refine the event.",
          reportability: {
            status: "insufficient_data",
            can_start_analysis: false,
            stop_reason: "insufficient_posts",
            counts: { posts: 8, comments: 6 },
          },
        },
      }) as any,
      startSearch: async () => {
        searchStarted = true;
        throw new Error("search must not start");
      },
      getSearchStatus: async () => {
        throw new Error("search status must not be polled");
      },
      getReportProgress: async () => {
        throw new Error("report must not be polled");
      },
      getReportResult: async () => {
        throw new Error("report result must not be fetched");
      },
    },
  });

  const finalState = await runner.run(request, { onState: () => undefined });

  assert.equal(finalState.status, "insufficient_data");
  assert.equal(finalState.crawlTask?.reportability?.stop_reason, "insufficient_posts");
  assert.equal(searchStarted, false);
});

test("runner surfaces engine-level search failures", async () => {
  const runner = createArgusWorkflowRunner({
    pollIntervalMs: 1,
    api: {
      createCrawlTask: async () =>
        ({
          success: true,
          task: {
            task_id: "crawl_1",
            status: "reportable",
            reportability: {
              status: "reportable",
              can_start_analysis: true,
              counts: { posts: 51, comments: 86 },
            },
          },
        }) as any,
      getCrawlTask: async () => {
        throw new Error("crawl status should not be polled");
      },
      startSearch: async () =>
        ({
          success: true,
          task_id: "search_1",
          query: "小米SU7 交付争议 最近三个月",
          status: "error",
          error_message: "引擎失败: query, insight",
          engines: {
            query: {
              status: "error",
              error_message:
                "Tavily库未安装，请运行 `pip install tavily-python` 进行安装。",
            },
            insight: {
              status: "error",
              error_message: "No module named 'sqlalchemy'",
            },
            media: { status: "running" },
          },
        }) as any,
      getSearchStatus: async () => {
        throw new Error("search status should not be polled");
      },
      getReportProgress: async () => {
        throw new Error("report must not be polled");
      },
      getReportResult: async () => {
        throw new Error("report result must not be fetched");
      },
    },
  });

  const finalState = await runner.run(request, { onState: () => undefined });

  assert.equal(finalState.status, "failed");
  assert.match(finalState.message, /query|insight|引擎失败/);
  assert.equal(finalState.searchTask?.engines?.query?.status, "error");
});

test("runner summarizes engine progress in Chinese during analysis", async () => {
  const messages: string[] = [];
  const runner = createArgusWorkflowRunner({
    pollIntervalMs: 1,
    api: {
      createCrawlTask: async () =>
        ({
          success: true,
          task: {
            task_id: "crawl_1",
            status: "reportable",
            reportability: {
              status: "reportable",
              can_start_analysis: true,
              counts: { posts: 51, comments: 86 },
            },
          },
        }) as any,
      getCrawlTask: async () => {
        throw new Error("crawl status should not be polled");
      },
      startSearch: async () =>
        ({
          success: true,
          task_id: "search_1",
          query: "小米SU7 交付争议 最近三个月",
          status: "running",
          engines: {
            query: { status: "running" },
            media: { status: "completed" },
            insight: { status: "pending" },
          },
        }) as any,
      getSearchStatus: async () =>
        ({
          success: true,
          task_id: "search_1",
          query: "小米SU7 交付争议 最近三个月",
          status: "completed",
          report_task_id: "report_1",
        }) as any,
      getReportProgress: async () =>
        ({
          success: true,
          task: {
            task_id: "report_1",
            query: "小米SU7 交付争议 最近三个月",
            status: "completed",
            progress: 100,
            report_file_ready: true,
          },
        }) as any,
      getReportResult: async () =>
        ({
          success: true,
          html_content: "<!doctype html><html><body>Report</body></html>",
          task: {
            task_id: "report_1",
            query: "小米SU7 交付争议 最近三个月",
            status: "completed",
            progress: 100,
            report_file_ready: true,
            report_file_name: "report.html",
            report_file_path: "final_reports/report.html",
          },
        }) as any,
    },
  });

  await runner.run(request, {
    onState: (state) => messages.push(state.message),
  });

  assert.ok(
    messages.some((message) =>
      message.includes(
        "事实核验员运行中 · 传播观察员已完成 · 舆情洞察员等待中"
      )
    )
  );
});

test("runner uses separate poll budgets for long search and report stages", async () => {
  let searchPolls = 0;
  let reportPolls = 0;
  const runner = createArgusWorkflowRunner({
    pollIntervalMs: 1,
    crawlMaxPolls: 1,
    searchMaxPolls: 3,
    reportMaxPolls: 3,
    api: {
      createCrawlTask: async () =>
        ({
          success: true,
          task: {
            task_id: "crawl_1",
            status: "reportable",
            reportability: {
              status: "reportable",
              can_start_analysis: true,
              counts: { posts: 51, comments: 86 },
            },
          },
        }) as any,
      getCrawlTask: async () => {
        throw new Error("crawl status should not be polled");
      },
      startSearch: async () =>
        ({
          success: true,
          task_id: "search_1",
          query: "小米SU7 交付争议 最近三个月",
          status: "running",
        }) as any,
      getSearchStatus: async () => {
        searchPolls += 1;
        return {
          success: true,
          task_id: "search_1",
          query: "小米SU7 交付争议 最近三个月",
          status: searchPolls < 3 ? "running" : "completed",
          report_task_id: searchPolls < 3 ? null : "report_1",
        } as any;
      },
      getReportProgress: async () => {
        reportPolls += 1;
        return {
          success: true,
          task: {
            task_id: "report_1",
            query: "小米SU7 交付争议 最近三个月",
            status: reportPolls < 3 ? "running" : "completed",
            progress: reportPolls < 3 ? 50 : 100,
            report_file_ready: reportPolls >= 3,
          },
        } as any;
      },
      getReportResult: async () =>
        ({
          success: true,
          html_content: "<!doctype html><html><body>Report</body></html>",
          task: {
            task_id: "report_1",
            query: "小米SU7 交付争议 最近三个月",
            status: "completed",
            progress: 100,
            report_file_ready: true,
            report_file_name: "report.html",
            report_file_path: "final_reports/report.html",
          },
        }) as any,
    },
  });

  const finalState = await runner.run(request, { onState: () => undefined });

  assert.equal(finalState.status, "report_ready");
  assert.equal(searchPolls, 3);
  assert.equal(reportPolls, 3);
});
