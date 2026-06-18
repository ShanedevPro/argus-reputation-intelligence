import assert from "node:assert/strict";
import test from "node:test";
import { buildReportArtifactMarkdown } from "./report-artifact";

test("buildReportArtifactMarkdown is public-facing and hides backend details", () => {
  const markdown = buildReportArtifactMarkdown({
    analysisQuery: "小米SU7 交付争议 最近三个月",
    researchRequest: {
      eventOrIssue: "交付争议",
      affectedSubject: "小米SU7",
      timeWindow: "最近三个月",
      profileId: "enterprise_pr",
    },
    crawlTask: {
      task_id: "crawl_1",
      status: "reportable",
      reportability: {
        status: "reportable",
        counts: { posts: 30, comments: 120 },
      },
    } as any,
    searchTask: {
      task_id: "search_1",
      status: "completed",
      report_task_id: "report_1",
    } as any,
    reportResult: {
      success: true,
      html_content: "<html></html>",
      task: {
        task_id: "report_1",
        query: "小米SU7 交付争议 最近三个月",
        status: "completed",
        report_file_name: "report.html",
        report_file_path: "final_reports/report.html",
      },
    } as any,
    htmlUrl: "/api/argus/report/report_1/html",
  });

  assert.match(markdown, /# Argus 报告已完成/);
  assert.match(markdown, /小米SU7 交付争议 最近三个月/);
  assert.match(markdown, /分析画像：企业公关舆情/);
  assert.match(markdown, /微博样本：30 条帖子 \/ 120 条一级评论/);
  assert.match(markdown, /数据状态：可分析/);
  assert.match(markdown, /报告已生成，可打开 HTML 报告查看/);
  assert.match(
    markdown,
    /\[打开 HTML 报告\]\(\/api\/argus\/report\/report_1\/html\)/
  );
  assert.doesNotMatch(markdown, /Crawl task|Search task|Report task/);
  assert.doesNotMatch(markdown, /final_reports\/report\.html/);
  assert.doesNotMatch(markdown, /reportable/);
  assert.doesNotMatch(markdown, /停止原因/);
  assert.doesNotMatch(markdown, /验收 HTML|HTML 报告质量/);
});
