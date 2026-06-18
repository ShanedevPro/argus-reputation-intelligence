"use client";

import { normalizeArgusProfileId } from "./profiles";
import { buildAnalysisQuery, type ResearchRequest } from "./workflow";
import {
  createCrawlTask,
  getCrawlTask,
  getReportProgress,
  getReportResult,
  getSearchStatus,
  startSearch,
  type CrawlTask,
  type CrawlTaskResponse,
  type ReportProgressResponse,
  type ReportResultResponse,
  type EngineArtifactMap,
  type SearchTaskStatus,
} from "./workflow-api";

export type { EngineArtifactMap } from "./workflow-api";

export type ArgusRunStatus =
  | "idle"
  | "preparing_data"
  | "insufficient_data"
  | "running_analysis"
  | "generating_report"
  | "report_ready"
  | "failed";

export type ArgusRunState = {
  status: ArgusRunStatus;
  message: string;
  analysisQuery: string;
  crawlTask?: CrawlTask;
  searchTask?: SearchTaskStatus;
  reportProgress?: ReportProgressResponse;
  reportResult?: ReportResultResponse;
  error?: string;
};

export type ArgusWorkflowApi = {
  createCrawlTask: typeof createCrawlTask;
  getCrawlTask: typeof getCrawlTask;
  startSearch: typeof startSearch;
  getSearchStatus: typeof getSearchStatus;
  getReportProgress: typeof getReportProgress;
  getReportResult: typeof getReportResult;
};

type RunnerOptions = {
  api?: ArgusWorkflowApi;
  pollIntervalMs?: number;
  maxPolls?: number;
  crawlMaxPolls?: number;
  searchMaxPolls?: number;
  reportMaxPolls?: number;
};

type RunOptions = {
  onState: (state: ArgusRunState) => void;
  signal?: AbortSignal;
  engineArtifacts?: EngineArtifactMap;
};

const terminalCrawlStatuses = ["reportable", "insufficient_data", "failed"];
const terminalSearchStatuses = ["completed", "blocked", "error"];
const terminalReportStatuses = ["completed", "error", "cancelled"];

const defaultApi: ArgusWorkflowApi = {
  createCrawlTask,
  getCrawlTask,
  startSearch,
  getSearchStatus,
  getReportProgress,
  getReportResult,
};

export function createArgusWorkflowRunner(options: RunnerOptions = {}) {
  const api = options.api ?? defaultApi;
  const pollIntervalMs = options.pollIntervalMs ?? 2500;
  const crawlMaxPolls = options.crawlMaxPolls ?? options.maxPolls ?? 240;
  const searchMaxPolls = options.searchMaxPolls ?? options.maxPolls ?? 2400;
  const reportMaxPolls = options.reportMaxPolls ?? options.maxPolls ?? 2400;

  async function run(
    request: ResearchRequest,
    { onState, signal, engineArtifacts }: RunOptions
  ): Promise<ArgusRunState> {
    const normalizedRequest: ResearchRequest = {
      ...request,
      profileId: normalizeArgusProfileId(request.profileId),
    };
    const analysisQuery = buildAnalysisQuery(normalizedRequest);
    let state: ArgusRunState = emit(
      {
        status: "preparing_data",
        message: "正在使用 TikHub 采集微博帖子和一级评论。",
        analysisQuery,
      },
      onState,
      signal
    );

    try {
      const created = await api.createCrawlTask({
        analysis_query: analysisQuery,
        data_request: normalizedRequest,
        platforms: ["wb"],
      });

      const crawlTask = await pollCrawlTask(
        created,
        analysisQuery,
        onState,
        signal
      );
      state = { ...state, crawlTask };

      if (crawlTask.status === "insufficient_data") {
        return emit(
          {
            ...state,
            status: "insufficient_data",
            message:
              crawlTask.next_action ||
              "微博样本不足，暂不能进入正式分析。",
          },
          onState,
          signal
        );
      }

      if (crawlTask.status !== "reportable") {
        const message =
          crawlTask.error_message || `微博数据准备状态异常：${crawlTask.status}`;
        return emit(
          {
            ...state,
            status: "failed",
            message,
            error: message,
          },
          onState,
          signal
        );
      }

      state = emit(
        {
          ...state,
          status: "running_analysis",
          message: "正在使用微博样本运行多引擎分析链路。",
        },
        onState,
        signal
      );

      const startedSearch = await api.startSearch(
        analysisQuery,
        crawlTask.task_id,
        engineArtifacts
      );
      const searchTask = await pollSearchTask(
        startedSearch,
        onState,
        signal,
        state
      );

      if (searchTask.status !== "completed" || !searchTask.report_task_id) {
        const message =
          searchTask.blocked_reason ||
          searchTask.error_message ||
          "分析链路没有生成报告任务。";
        return emit(
          {
            ...state,
            crawlTask,
            searchTask,
            status: "failed",
            message,
            error: message,
          },
          onState,
          signal
        );
      }

      state = emit(
        {
          ...state,
          crawlTask,
          searchTask,
          status: "generating_report",
          message: "正在生成 HTML 报告。",
        },
        onState,
        signal
      );

      const reportProgress = await pollReportTask(
        searchTask.report_task_id,
        onState,
        signal,
        state
      );

      if (
        reportProgress.task.status !== "completed" ||
        !reportProgress.task.report_file_ready
      ) {
        const message =
          reportProgress.task.error_message ||
          "报告没有成功完成。";
        return emit(
          {
            ...state,
            reportProgress,
            status: "failed",
            message,
            error: message,
          },
          onState,
          signal
        );
      }

      const reportResult = await api.getReportResult(searchTask.report_task_id);
      return emit(
        {
          ...state,
          reportProgress,
          reportResult,
          status: "report_ready",
          message: "报告已完成。",
        },
        onState,
        signal
      );
    } catch (error) {
      const message = error instanceof Error ? error.message : "工作流运行失败。";
      return emit(
        { ...state, status: "failed", message, error: message },
        onState,
        signal
      );
    }
  }

  async function pollCrawlTask(
    created: CrawlTaskResponse,
    analysisQuery: string,
    onState: RunOptions["onState"],
    signal: AbortSignal | undefined
  ) {
    let task = created.task;
    for (let index = 0; index < crawlMaxPolls; index += 1) {
      emit(
        {
          status: "preparing_data",
          message: task.next_action || "正在准备微博数据。",
          analysisQuery,
          crawlTask: task,
        },
        onState,
        signal
      );
      if (terminalCrawlStatuses.includes(task.status)) {
        return task;
      }
      await wait(pollIntervalMs, signal);
      task = (await api.getCrawlTask(task.task_id)).task;
      if (terminalCrawlStatuses.includes(task.status)) {
        return task;
      }
    }
    throw new Error("等待微博数据准备超时。");
  }

  async function pollSearchTask(
    started: SearchTaskStatus,
    onState: RunOptions["onState"],
    signal: AbortSignal | undefined,
    baseState: ArgusRunState
  ) {
    let task = started;
    for (let index = 0; index < searchMaxPolls; index += 1) {
      emit(
        {
          ...baseState,
          searchTask: task,
          status: "running_analysis",
          message: formatSearchMessage(task),
        },
        onState,
        signal
      );
      if (terminalSearchStatuses.includes(task.status)) {
        return task;
      }
      await wait(pollIntervalMs, signal);
      task = await api.getSearchStatus(task.task_id);
      if (terminalSearchStatuses.includes(task.status)) {
        return task;
      }
    }
    throw new Error("等待分析链路完成超时。");
  }

  async function pollReportTask(
    taskId: string,
    onState: RunOptions["onState"],
    signal: AbortSignal | undefined,
    baseState: ArgusRunState
  ) {
    for (let index = 0; index < reportMaxPolls; index += 1) {
      const progress = await api.getReportProgress(taskId);
      emit(
        {
          ...baseState,
          reportProgress: progress,
          status: "generating_report",
          message: `报告进度：${progress.task.progress}%`,
        },
        onState,
        signal
      );
      if (terminalReportStatuses.includes(progress.task.status)) {
        return progress;
      }
      await wait(pollIntervalMs, signal);
    }
    throw new Error("等待报告生成超时。");
  }

  return { run };
}

export function collectResumableEngineArtifacts(
  searchTask: SearchTaskStatus | undefined
): EngineArtifactMap {
  const artifacts: EngineArtifactMap = {};
  const engines = searchTask?.engines ?? {};
  for (const name of ["query", "media", "insight"] as const) {
    const engine = engines[name];
    const outputFile = String(engine?.output_file ?? "").trim();
    if (
      engine?.status === "completed" &&
      engine?.evidence_status === "ready" &&
      outputFile
    ) {
      artifacts[name] = { output_file: outputFile };
    }
  }
  return artifacts;
}

function formatSearchStatus(status: string) {
  const labels: Record<string, string> = {
    pending: "等待中",
    running: "运行中",
    completed: "已完成",
    blocked: "已阻塞",
    error: "失败",
  };
  return labels[status] ?? status;
}

function formatSearchMessage(task: SearchTaskStatus) {
  const engineProgress = formatEngineProgress(task.engines);
  if (engineProgress) {
    return `分析进度：${engineProgress}`;
  }

  return `分析状态：${formatSearchStatus(task.status)}`;
}

function formatEngineProgress(
  engines: Record<string, Record<string, unknown>> | undefined
) {
  if (!engines) {
    return "";
  }

  const labels: Record<string, string> = {
    query: "事实核验员",
    media: "传播观察员",
    insight: "舆情洞察员",
  };

  return ["query", "media", "insight"]
    .map((name) => {
      const engine = engines[name];
      if (!engine) {
        return "";
      }
      return `${labels[name] ?? name}${formatSearchStatus(String(engine.status ?? "unknown"))}`;
    })
    .filter(Boolean)
    .join(" · ");
}

function emit(
  state: ArgusRunState,
  onState: RunOptions["onState"],
  signal?: AbortSignal
) {
  if (signal?.aborted) {
    throw new Error("工作流已取消。");
  }
  onState(state);
  return state;
}

function wait(ms: number, signal?: AbortSignal) {
  if (signal?.aborted) {
    return Promise.reject(new Error("工作流已取消。"));
  }

  return new Promise<void>((resolve, reject) => {
    const timer = globalThis.setTimeout(resolve, ms);
    signal?.addEventListener(
      "abort",
      () => {
        globalThis.clearTimeout(timer);
        reject(new Error("Workflow cancelled."));
      },
      { once: true }
    );
  });
}
