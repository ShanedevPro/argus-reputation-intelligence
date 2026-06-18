"use client";

import type { ResearchRequest } from "./workflow";

export type CrawlTaskStatus =
  | "created"
  | "compiling"
  | "collecting"
  | "normalizing"
  | "importing"
  | "readiness_checking"
  | "reportable"
  | "insufficient_data"
  | "queued"
  | "manual_action_required"
  | "imported"
  | "failed";

export type CrawlTask = {
  task_id: string;
  analysis_query: string;
  data_request: string;
  platforms: string[];
  provider: string;
  caps: Record<string, unknown>;
  status: CrawlTaskStatus;
  cloud_job_id?: string;
  cloud_status_url?: string;
  error_message: string;
  import_result?: Record<string, unknown>;
  readiness?: Record<string, unknown>;
  bundle_metadata?: Record<string, unknown>;
  evidence_manifest?: {
    sample_boundary?: Record<string, unknown>;
    counts?: Record<string, number>;
    keywords?: string[];
    key_posts?: Array<Record<string, unknown>>;
    key_comments?: Array<Record<string, unknown>>;
  };
  reportability?: {
    status?: string;
    can_start_analysis?: boolean;
    stop_reason?: string;
    counts?: Record<string, number>;
    reasons?: string[];
  };
  next_action: string;
  created_at?: string;
  updated_at?: string;
  status_url: string;
};

export type CrawlTaskResponse = {
  success: boolean;
  task: CrawlTask;
  message?: string;
};

export type CrawlTaskInput = {
  analysis_query: string;
  data_request: ResearchRequest;
  platforms?: string[];
};

export type SearchTaskStatus = {
  success: boolean;
  task_id: string;
  query: string;
  status: "pending" | "running" | "completed" | "blocked" | "error";
  report_task_id?: string | null;
  data_ready?: boolean;
  blocked_reason?: string;
  error_message?: string;
  created_at?: string;
  updated_at?: string;
  status_url?: string;
  engines?: Record<string, Record<string, unknown>>;
};

export type EngineArtifactName = "insight" | "media" | "query";
export type EngineArtifactMap = Partial<
  Record<EngineArtifactName, { output_file: string }>
>;

export type ReportProgressTask = {
  task_id: string;
  query: string;
  status: "pending" | "running" | "completed" | "error" | "cancelled";
  progress: number;
  error_message: string;
  created_at?: string;
  updated_at?: string;
  has_result: boolean;
  report_file_ready: boolean;
  report_file_name: string;
  report_file_path: string;
  state_file_ready?: boolean;
  state_file_path?: string;
  ir_file_ready?: boolean;
  ir_file_path?: string;
  markdown_file_ready: boolean;
  markdown_file_name: string;
  markdown_file_path: string;
  pdf_file_ready: boolean;
  pdf_file_name: string;
  pdf_file_path: string;
  export_errors: string[];
};

export type ReportProgressResponse = {
  success: boolean;
  task: ReportProgressTask;
};

export type ReportResultResponse = {
  success: boolean;
  task: ReportProgressTask;
  html_content: string;
};

export function buildArgusReportHtmlPath(taskId: string) {
  return `/api/argus/report/${encodeURIComponent(taskId)}/html`;
}

async function requestJson<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, {
    cache: "no-store",
    ...init,
    headers: {
      accept: "application/json",
      ...(init?.headers ?? {}),
    },
  });

  if (!response.ok) {
    throw new Error(await readResponseError(response));
  }

  return (await response.json()) as T;
}

async function readResponseError(response: Response) {
  try {
    const payload = (await response.json()) as {
      error?: string;
      message?: string;
    };
    return payload.error ?? payload.message ?? `Request failed: ${response.status}`;
  } catch {
    return `Request failed: ${response.status}`;
  }
}

export function createCrawlTask(input: CrawlTaskInput) {
  return requestJson<CrawlTaskResponse>("/api/argus/crawl", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(input),
  });
}

export function getCrawlTask(taskId: string) {
  return requestJson<CrawlTaskResponse>(
    `/api/argus/crawl/${encodeURIComponent(taskId)}`
  );
}

export function startSearch(
  query: string,
  dataPrepTaskId: string,
  engineArtifacts?: EngineArtifactMap
) {
  return requestJson<SearchTaskStatus>("/api/argus/search", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({
      query,
      data_prep_task_id: dataPrepTaskId,
      ...(engineArtifacts && Object.keys(engineArtifacts).length > 0
        ? { engine_artifacts: engineArtifacts }
        : {}),
    }),
  });
}

export function getSearchStatus(taskId: string) {
  return requestJson<SearchTaskStatus>(
    `/api/argus/search/${encodeURIComponent(taskId)}`
  );
}

export function getReportProgress(taskId: string) {
  return requestJson<ReportProgressResponse>(
    `/api/argus/report/${encodeURIComponent(taskId)}/progress`
  );
}

export function getReportResult(taskId: string) {
  return requestJson<ReportResultResponse>(
    `/api/argus/report/${encodeURIComponent(taskId)}/result`
  );
}
