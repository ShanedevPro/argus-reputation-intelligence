import type {
  CrawlTask,
  ReportResultResponse,
  SearchTaskStatus,
} from "./workflow-api";
import { getArgusProfile } from "./profiles";
import type { ResearchRequest } from "./workflow";

export function buildReportArtifactMarkdown({
  analysisQuery,
  researchRequest,
  crawlTask,
  reportResult,
  htmlUrl,
}: {
  analysisQuery: string;
  researchRequest?: ResearchRequest | null;
  crawlTask: CrawlTask;
  searchTask: SearchTaskStatus;
  reportResult: ReportResultResponse;
  htmlUrl: string;
}) {
  const counts = crawlTask.reportability?.counts ?? {};
  const posts = Number(counts.posts ?? 0);
  const comments = Number(counts.comments ?? 0);
  const profile = getArgusProfile(researchRequest?.profileId);
  const reportTask = reportResult.task;
  const dataStatus = formatDataStatus(
    crawlTask.reportability?.status ?? crawlTask.status
  );

  return [
    "# Argus 报告已完成",
    "",
    `研究主题：${analysisQuery}`,
    `分析画像：${profile.label}`,
    "",
    "## 报告",
    "",
    `[打开 HTML 报告](${htmlUrl})`,
    "",
    "## 样本概况",
    "",
    `微博样本：${posts} 条帖子 / ${comments} 条一级评论`,
    `数据状态：${dataStatus}`,
    "",
    "## 使用提示",
    "",
    reportTask.pdf_file_ready
      ? "报告已生成，可打开 HTML 报告查看；PDF 版本也已准备好。"
      : "报告已生成，可打开 HTML 报告查看。",
  ].join("\n");
}

function formatDataStatus(status: string | undefined) {
  const labels: Record<string, string> = {
    reportable: "可分析",
    not_reportable: "暂不可分析",
    insufficient_data: "样本不足",
    collecting: "采集中",
    failed: "失败",
  };
  return status ? labels[status] ?? status : "可分析";
}
