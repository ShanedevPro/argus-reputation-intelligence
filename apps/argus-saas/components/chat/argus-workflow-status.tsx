"use client";

import type { UseChatHelpers } from "@ai-sdk/react";
import {
  AlertTriangleIcon,
  CheckCircle2Icon,
  FolderOpenIcon,
  PencilLineIcon,
  PlayIcon,
} from "lucide-react";
import { useMemo, useRef, useState } from "react";
import { toast } from "sonner";
import type { UIArtifact } from "@/components/chat/artifact";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  ARGUS_PROFILE_IDS,
  getArgusProfile,
  type ArgusProfileId,
} from "@/lib/argus/profiles";
import { buildReportArtifactMarkdown } from "@/lib/argus/report-artifact";
import {
  applyResearchProfileToMarkdown,
  buildAnalysisQuery,
  buildResearchPlanMarkdown,
  canSwitchResearchProfile,
  deriveWorkflowSnapshot,
  extractResearchRequest,
  type WorkflowStage,
} from "@/lib/argus/workflow";
import {
  collectResumableEngineArtifacts,
  type ArgusRunState,
  createArgusWorkflowRunner,
} from "@/lib/argus/workflow-runner";
import { buildArgusReportHtmlPath } from "@/lib/argus/workflow-api";
import type { ChatMessage } from "@/lib/types";
import { cn } from "@/lib/utils";

type ArgusWorkflowStatusProps = {
  chatId: string;
  chatStatus: UseChatHelpers<ChatMessage>["status"];
  artifact: UIArtifact;
  isReadonly: boolean;
  messages: ChatMessage[];
  sendMessage: UseChatHelpers<ChatMessage>["sendMessage"];
  setArtifact: (
    artifact: UIArtifact | ((currentArtifact: UIArtifact) => UIArtifact)
  ) => void;
};

export function ArgusWorkflowStatus({
  chatId,
  chatStatus,
  artifact,
  isReadonly,
  messages,
  sendMessage,
  setArtifact,
}: ArgusWorkflowStatusProps) {
  const snapshot = deriveWorkflowSnapshot({ messages, artifact });
  const [runState, setRunState] = useState<ArgusRunState | null>(null);
  const [profileOverride, setProfileOverride] = useState<{
    requestKey: string;
    profileId: ArgusProfileId;
  } | null>(null);
  const abortRef = useRef<AbortController | null>(null);
  const runner = useMemo(() => createArgusWorkflowRunner(), []);
  const researchRequest = extractResearchRequest({ messages, artifact });
  const requestKey = getResearchRequestKey(researchRequest);
  const activeProfileId =
    profileOverride?.requestKey === requestKey
      ? profileOverride.profileId
      : researchRequest?.profileId;
  const activeResearchRequest = researchRequest
    ? { ...researchRequest, profileId: activeProfileId }
    : null;
  const isRunning =
    runState?.status === "preparing_data" ||
    runState?.status === "running_analysis" ||
    runState?.status === "generating_report";
  const isChatBusy = chatStatus === "submitted" || chatStatus === "streaming";
  const currentProfile = getArgusProfile(activeResearchRequest?.profileId);
  const canSwitchProfile = canSwitchResearchProfile({
    hasResearchRequest: Boolean(activeResearchRequest),
    isReadonly,
    isWorkflowRunning: isRunning,
    isChatBusy,
    stage: snapshot.stage,
  });
  const resumableEngineArtifacts = collectResumableEngineArtifacts(
    runState?.searchTask
  );
  const activeAnalysisQuery = activeResearchRequest
    ? buildAnalysisQuery(activeResearchRequest)
    : "";
  const canUseRunStateForCurrentRequest =
    Boolean(activeAnalysisQuery) && runState?.analysisQuery === activeAnalysisQuery;
  const canResumeAnalysis =
    runState?.status === "failed" &&
    canUseRunStateForCurrentRequest &&
    Object.keys(resumableEngineArtifacts).length > 0;

  if (snapshot.stage === "collecting" && artifact.documentId === "init") {
    return null;
  }

  const sendWorkflowCommand = (text: string) => {
    if (isChatBusy) {
      toast.error("请等待模型回复完成。");
      return;
    }
    window.history.pushState(
      {},
      "",
      `${process.env.NEXT_PUBLIC_BASE_PATH ?? ""}/chat/${chatId}`
    );
    sendMessage({
      role: "user",
      parts: [{ type: "text", text }],
    });
  };

  const handleProfileChange = async (profileId: string) => {
    if (!activeResearchRequest) {
      return;
    }
    const nextProfileId = profileId as ArgusProfileId;
    const nextProfile = getArgusProfile(nextProfileId);
    const documentId =
      artifact.documentId === "init" ? crypto.randomUUID() : artifact.documentId;
    const title =
      artifact.title || `Research Plan: ${activeResearchRequest.affectedSubject}`;
    const baseContent =
      artifact.kind === "text" && artifact.content.trim()
        ? artifact.content
        : buildResearchPlanMarkdown(activeResearchRequest);
    const content = applyResearchProfileToMarkdown(baseContent, nextProfileId);

    setProfileOverride({ requestKey, profileId: nextProfileId });
    setArtifact((currentArtifact) => ({
      ...currentArtifact,
      documentId,
      title,
      kind: "text",
      content,
      status: "idle",
    }));

    try {
      const response = await fetch(
        `${process.env.NEXT_PUBLIC_BASE_PATH ?? ""}/api/document?id=${documentId}`,
        {
          method: "POST",
          headers: { "content-type": "application/json" },
          body: JSON.stringify({ title, content, kind: "text" }),
        }
      );

      if (!response.ok) {
        throw new Error("profile document save failed");
      }
    } catch (_error) {
      toast.error("画像已切换，但研究计划保存失败。");
      return;
    }

    toast.success(`已切换为${nextProfile.label}`);
  };

  const openArtifact = () => {
    if (artifact.documentId === "init") {
      return;
    }
    setArtifact((currentArtifact) => ({
      ...currentArtifact,
      isVisible: true,
    }));
  };

  const createReportDocument = async (state: ArgusRunState) => {
    if (!state.crawlTask || !state.searchTask || !state.reportResult) {
      return;
    }

    const reportTaskId = state.reportResult.task.task_id;
    const htmlUrl = buildArgusReportHtmlPath(reportTaskId);
    const content = buildReportArtifactMarkdown({
      analysisQuery: state.analysisQuery,
      researchRequest: activeResearchRequest,
      crawlTask: state.crawlTask,
      searchTask: state.searchTask,
      reportResult: state.reportResult,
      htmlUrl,
    });
    const documentId = crypto.randomUUID();
    const title = `Argus Report: ${state.analysisQuery}`;

    const response = await fetch(
      `${process.env.NEXT_PUBLIC_BASE_PATH ?? ""}/api/document?id=${documentId}`,
      {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ title, content, kind: "text" }),
      }
    );

    if (!response.ok) {
      throw new Error("保存报告卡片失败。");
    }

    setArtifact((currentArtifact) => ({
      ...currentArtifact,
      documentId,
      title,
      content,
      kind: "text",
      status: "idle",
      isVisible: true,
    }));
  };

  const startRealWorkflow = async () => {
    if (!activeResearchRequest) {
      toast.error("请先创建或打开研究计划。");
      return;
    }

    abortRef.current?.abort();
    const abortController = new AbortController();
    abortRef.current = abortController;

    try {
      const finalState = await runner.run(activeResearchRequest, {
        signal: abortController.signal,
        onState: setRunState,
      });

      if (finalState.status === "report_ready") {
        await createReportDocument(finalState);
        toast.success("Argus 报告已完成。");
        return;
      }

      if (finalState.status === "insufficient_data") {
        toast.warning("微博样本不足，暂不能进入正式分析。");
        return;
      }

      if (finalState.status === "failed") {
        toast.error(finalState.message);
      }
    } catch (error) {
      const message =
        error instanceof Error ? error.message : "Argus 工作流运行失败。";
      setRunState((currentState) => ({
        status: "failed",
        message,
        analysisQuery: currentState?.analysisQuery ?? "",
        error: message,
      }));
      toast.error(message);
    }
  };

  const resumeRealWorkflow = async () => {
    if (!activeResearchRequest || !runState?.searchTask) {
      return;
    }
    if (!canUseRunStateForCurrentRequest) {
      toast.error("当前研究计划与可恢复任务不一致。");
      return;
    }
    const engineArtifacts = collectResumableEngineArtifacts(runState.searchTask);
    if (Object.keys(engineArtifacts).length === 0) {
      toast.error("没有可复用的已完成分析结果。");
      return;
    }

    abortRef.current?.abort();
    const abortController = new AbortController();
    abortRef.current = abortController;

    try {
      const finalState = await runner.run(activeResearchRequest, {
        signal: abortController.signal,
        onState: setRunState,
        engineArtifacts,
      });

      if (finalState.status === "report_ready") {
        await createReportDocument(finalState);
        toast.success("Argus 报告已恢复并完成。");
        return;
      }

      if (finalState.status === "insufficient_data") {
        toast.warning("微博样本不足，暂不能进入正式分析。");
        return;
      }

      toast.error(finalState.message);
    } catch (error) {
      const message =
        error instanceof Error ? error.message : "Argus 恢复运行失败。";
      setRunState((currentState) => ({
        status: "failed",
        message,
        analysisQuery: currentState?.analysisQuery ?? "",
        crawlTask: currentState?.crawlTask,
        searchTask: currentState?.searchTask,
        reportProgress: currentState?.reportProgress,
        reportResult: currentState?.reportResult,
        error: message,
      }));
      toast.error(message);
    }
  };

  const actions = getActions({
    stage: snapshot.stage,
    isReadonly,
    isRunning: isRunning || isChatBusy,
    onOpen: openArtifact,
    onConfirm: () => sendWorkflowCommand("Confirm the research plan."),
    onRevise: () =>
      sendWorkflowCommand(
        "Please revise the research plan with the latest details."
      ),
    onStart: startRealWorkflow,
  });

  return (
    <div className="mx-auto w-full max-w-4xl px-2 md:px-4">
      <div className="flex w-full flex-col gap-3 rounded-2xl border border-border/50 bg-card/90 px-4 py-3 shadow-[var(--shadow-card)] backdrop-blur-sm">
        <div className="flex items-start gap-3">
          <div className="flex min-w-0 flex-1 flex-col gap-1">
            <div className="flex flex-wrap items-center gap-2">
              <span className="font-medium text-[13px] text-foreground">
                {snapshot.title}
              </span>
              <Badge
                className={cn({
                  "bg-amber-500/10 text-amber-700 dark:bg-amber-500/15 dark:text-amber-300":
                    snapshot.preflight === "needs_weibo_data",
                  "bg-rose-500/10 text-rose-700 dark:bg-rose-500/15 dark:text-rose-300":
                    snapshot.preflight === "needs_event",
                  "bg-slate-500/10 text-slate-700 dark:bg-slate-500/15 dark:text-slate-300":
                    snapshot.preflight === "not_reportable",
                  "bg-emerald-500/10 text-emerald-700 dark:bg-emerald-500/15 dark:text-emerald-300":
                    snapshot.preflight === "reportable",
                })}
                variant="outline"
              >
                {formatPreflightStatus(snapshot.preflight)}
              </Badge>
            </div>
            <p className="max-w-[70ch] text-muted-foreground text-[12px] leading-relaxed">
              {snapshot.summary}
            </p>
            {researchRequest ? (
              <div className="mt-1 flex flex-wrap items-center gap-2 text-[12px]">
                <span className="text-muted-foreground">分析画像</span>
                <Select
                  disabled={!canSwitchProfile}
                  onValueChange={handleProfileChange}
                  value={currentProfile.id}
                >
                  <SelectTrigger
                    aria-label="切换分析画像"
                    className="h-8 min-w-[150px] rounded-lg text-[12px]"
                    size="sm"
                  >
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent align="start">
                    {ARGUS_PROFILE_IDS.map((profileId) => {
                      const profile = getArgusProfile(profileId);
                      return (
                        <SelectItem key={profile.id} value={profile.id}>
                          {profile.label}
                        </SelectItem>
                      );
                    })}
                  </SelectContent>
                </Select>
                {!canSwitchProfile ? (
                  <span className="text-muted-foreground">
                    运行后不可切换
                  </span>
                ) : null}
              </div>
            ) : null}
            {runState ? (
              <div className="mt-2 rounded-lg border border-border/50 bg-background/60 px-3 py-2 text-[12px]">
                <div className="font-medium text-foreground">
                  {runState.message}
                </div>
                {runState.crawlTask?.reportability?.counts ? (
                  <div className="mt-1 text-muted-foreground">
                    帖子：{" "}
                    {runState.crawlTask.reportability.counts.posts ?? 0} ·
                    评论：{" "}
                    {runState.crawlTask.reportability.counts.comments ?? 0}
                  </div>
                ) : null}
                {runState.crawlTask?.evidence_manifest?.counts ? (
                  <WeiboSampleStatus
                    counts={runState.crawlTask.evidence_manifest.counts}
                    sampleBoundary={
                      runState.crawlTask.evidence_manifest.sample_boundary
                    }
                  />
                ) : null}
                {runState.crawlTask?.reportability?.stop_reason &&
                runState.crawlTask.status !== "reportable" ? (
                  <div className="mt-1 text-muted-foreground">
                    样本说明：{" "}
                    {runState.crawlTask.reportability.stop_reason}
                  </div>
                ) : null}
                {runState.searchTask?.engines ? (
                  <EngineStatusList engines={runState.searchTask.engines} />
                ) : null}
              </div>
            ) : null}
          </div>
          {snapshot.stage === "collecting" ? null : (
            <span className="mt-0.5 flex size-8 shrink-0 items-center justify-center rounded-lg border border-border/50 bg-muted/40 text-muted-foreground">
              {snapshot.stage === "report_ready" ? (
                <CheckCircle2Icon className="size-4" />
              ) : snapshot.stage === "needs_data_prep" ? (
                <AlertTriangleIcon className="size-4" />
              ) : (
                <PlayIcon className="size-4" />
              )}
            </span>
          )}
        </div>

        {actions.length > 0 ? (
          <div className="flex flex-wrap items-center justify-end gap-2">
            {canResumeAnalysis ? (
              <Button
                className="h-8 rounded-full px-3 text-[12px]"
                onClick={resumeRealWorkflow}
                disabled={isRunning || isChatBusy}
                size="sm"
                variant="outline"
              >
                <PlayIcon className="size-3.5" />
                使用已完成结果恢复分析
              </Button>
            ) : null}
            {actions.map((action) => (
              <Button
                className="h-8 rounded-full px-3 text-[12px]"
                key={action.label}
                onClick={action.onClick}
                disabled={action.disabled}
                size="sm"
                variant={action.variant}
              >
                {action.icon}
                {action.label}
              </Button>
            ))}
          </div>
        ) : null}
      </div>
    </div>
  );
}

function getResearchRequestKey(
  request: ReturnType<typeof extractResearchRequest>
): string {
  if (!request) {
    return "";
  }

  return [
    request.eventOrIssue,
    request.affectedSubject,
    request.timeWindow,
  ].join("\u001f");
}

function WeiboSampleStatus({
  counts,
  sampleBoundary,
}: {
  counts: Record<string, number>;
  sampleBoundary?: Record<string, unknown>;
}) {
  const posts = counts.posts ?? 0;
  const comments = counts.comments ?? 0;
  const commentDepth =
    sampleBoundary?.comment_depth === "first_level_only"
      ? "仅一级评论"
      : sampleBoundary?.comment_depth
        ? String(sampleBoundary.comment_depth)
        : "已记录样本边界";

  return (
    <div className="mt-1 grid gap-0.5 text-muted-foreground">
      <div>
        微博样本：{posts} 条帖子 / {comments} 条评论
      </div>
      <div>样本边界：{commentDepth}</div>
    </div>
  );
}

function EngineStatusList({
  engines,
}: {
  engines: Record<string, Record<string, unknown>>;
}) {
  const engineEntries = ["query", "media", "insight"]
    .map((name) => [name, engines[name]] as const)
    .filter((entry): entry is readonly [string, Record<string, unknown>] =>
      Boolean(entry[1])
    );

  if (engineEntries.length === 0) {
    return null;
  }

  return (
    <div className="mt-2 grid gap-1.5">
      {engineEntries.map(([name, engine]) => {
        const status = String(engine.status ?? "unknown");
        const errorMessage = String(engine.error_message ?? "");
        return (
          <div
            className="rounded-md border border-border/40 bg-background/70 px-2.5 py-1.5"
            key={name}
          >
            <div className="flex items-center justify-between gap-3">
              <span className="font-medium text-foreground">
                {formatEngineName(name)}
              </span>
              <span className="text-[10px] text-muted-foreground">
                {formatEngineStatus(status)}
              </span>
            </div>
            {errorMessage ? (
              <div className="mt-1 break-words text-[11px] text-destructive">
                {errorMessage}
              </div>
            ) : null}
          </div>
        );
      })}
    </div>
  );
}

function getActions({
  stage,
  isReadonly,
  isRunning,
  onOpen,
  onConfirm,
  onRevise,
  onStart,
}: {
  stage: WorkflowStage;
  isReadonly: boolean;
  isRunning: boolean;
  onOpen: () => void;
  onConfirm: () => void;
  onRevise: () => void;
  onStart: () => void;
}) {
  if (isReadonly) {
    return stage === "collecting"
      ? []
      : [
          {
            label: "打开",
            onClick: onOpen,
            variant: "outline" as const,
            icon: <FolderOpenIcon className="size-3.5" />,
            disabled: false,
          },
        ];
  }

  switch (stage) {
    case "ready_to_confirm":
      return [
        {
          label: "打开",
          onClick: onOpen,
          variant: "outline" as const,
          icon: <FolderOpenIcon className="size-3.5" />,
          disabled: isRunning,
        },
        {
          label: "修改",
          onClick: onRevise,
          variant: "secondary" as const,
          icon: <PencilLineIcon className="size-3.5" />,
          disabled: isRunning,
        },
        {
          label: "确认",
          onClick: onConfirm,
          variant: "default" as const,
          icon: <CheckCircle2Icon className="size-3.5" />,
          disabled: isRunning,
        },
      ];
    case "confirmed":
      return [
        {
          label: "打开",
          onClick: onOpen,
          variant: "outline" as const,
          icon: <FolderOpenIcon className="size-3.5" />,
          disabled: isRunning,
        },
        {
          label: "修改",
          onClick: onRevise,
          variant: "secondary" as const,
          icon: <PencilLineIcon className="size-3.5" />,
          disabled: isRunning,
        },
        {
          label: "开始研究",
          onClick: onStart,
          variant: "default" as const,
          icon: <PlayIcon className="size-3.5" />,
          disabled: isRunning,
        },
      ];
    case "needs_data_prep":
      return [
        {
          label: "打开",
          onClick: onOpen,
          variant: "outline" as const,
          icon: <FolderOpenIcon className="size-3.5" />,
          disabled: isRunning,
        },
        {
          label: "修改",
          onClick: onRevise,
          variant: "secondary" as const,
          icon: <PencilLineIcon className="size-3.5" />,
          disabled: isRunning,
        },
        {
          label: "开始数据准备",
          onClick: onStart,
          variant: "default" as const,
          icon: <AlertTriangleIcon className="size-3.5" />,
          disabled: isRunning,
        },
      ];
    case "analysis_running":
      return [
        {
          label: "打开",
          onClick: onOpen,
          variant: "outline" as const,
          icon: <FolderOpenIcon className="size-3.5" />,
          disabled: false,
        },
      ];
    case "report_ready":
      return [
        {
          label: "打开",
          onClick: onOpen,
          variant: "default" as const,
          icon: <FolderOpenIcon className="size-3.5" />,
          disabled: false,
        },
      ];
    default:
      return [];
  }
}

function formatPreflightStatus(status: string) {
  const labels: Record<string, string> = {
    needs_event: "需要事件信息",
    needs_weibo_data: "需要微博数据",
    not_reportable: "暂不可分析",
    reportable: "可分析",
  };
  return labels[status] ?? status;
}

function formatEngineName(name: string) {
  const labels: Record<string, string> = {
    query: "事实核验员",
    media: "传播观察员",
    insight: "舆情洞察员",
  };
  return labels[name] ?? name;
}

function formatEngineStatus(status: string) {
  const labels: Record<string, string> = {
    pending: "等待中",
    running: "运行中",
    completed: "已完成",
    blocked: "已阻塞",
    error: "失败",
    unknown: "未知",
  };
  return labels[status] ?? status;
}
