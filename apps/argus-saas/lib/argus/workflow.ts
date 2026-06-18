import {
  DEFAULT_ARGUS_PROFILE_ID,
  normalizeArgusProfileId,
  type ArgusProfileId,
} from "./profiles";

export type ResearchRequest = {
  eventOrIssue: string;
  affectedSubject: string;
  timeWindow: string;
  profileId?: ArgusProfileId;
  weiboClue?: string;
  decisionGoal?: string;
  knownMaterials?: string[];
};

export type PreflightStatus =
  | "needs_event"
  | "needs_weibo_data"
  | "not_reportable"
  | "reportable";

export type WorkflowStage =
  | "collecting"
  | "ready_to_confirm"
  | "confirmed"
  | "needs_data_prep"
  | "analysis_running"
  | "report_ready";

export type WorkflowSnapshot = {
  stage: WorkflowStage;
  preflight: PreflightStatus;
  title: string;
  summary: string;
};

const requiredFields: (keyof Pick<
  ResearchRequest,
  "eventOrIssue" | "affectedSubject" | "timeWindow"
>)[] = ["eventOrIssue", "affectedSubject", "timeWindow"];

const eventOrIssueLabels = ["Event or issue", "事件或议题", "事件", "议题"];
const affectedSubjectLabels = [
  "Affected subject",
  "受影响主体",
  "研究对象",
  "主体",
  "品牌/实体",
  "对象",
];
const timeWindowLabels = ["Time window", "时间范围", "时间窗口", "时间段"];
const profileLabels = ["Profile", "分析画像", "业务画像", "画像"];
const weiboClueLabels = ["Weibo clue", "微博线索", "微博关键词"];
const decisionGoalLabels = ["Decision goal", "研究目标", "决策目标", "目标"];
const knownMaterialsLabels = [
  "Known materials",
  "已知材料",
  "已有材料",
  "相关材料",
];
const preflightLabels = ["Preflight", "预检", "预检查"];
const suggestedAnalysisPathLabels = [
  "Suggested analysis path",
  "建议分析路径",
  "分析路径",
];

const researchPlanSectionLabels = [
  ...eventOrIssueLabels,
  ...affectedSubjectLabels,
  ...timeWindowLabels,
  ...profileLabels,
  ...weiboClueLabels,
  ...decisionGoalLabels,
  ...knownMaterialsLabels,
  ...preflightLabels,
  ...suggestedAnalysisPathLabels,
];

export function buildResearchPlanMarkdown(request: ResearchRequest): string {
  const knownMaterials = request.knownMaterials ?? [];
  const profileId = normalizeArgusProfileId(request.profileId);

  return [
    "# Research Plan",
    "",
    `Event or issue: ${request.eventOrIssue}`,
    `Affected subject: ${request.affectedSubject}`,
    `Time window: ${request.timeWindow}`,
    `Profile: ${profileId}`,
    `Weibo clue: ${request.weiboClue ?? ""}`,
    `Decision goal: ${request.decisionGoal ?? ""}`,
    "Known materials:",
    ...knownMaterials.map((material) => `- ${material}`),
    ...(knownMaterials.length ? [] : ["-"]),
    "Preflight:",
    "",
    "Suggested analysis path:",
    "",
  ].join("\n");
}

export function parseResearchPlanMarkdown(
  markdown: string
): ResearchRequest | null {
  const eventOrIssue = readSectionValue(markdown, eventOrIssueLabels);
  const affectedSubject = readSectionValue(markdown, affectedSubjectLabels);
  const timeWindow = readSectionValue(markdown, timeWindowLabels);

  if (!eventOrIssue || !affectedSubject || !timeWindow) {
    return null;
  }

  const request: ResearchRequest = {
    eventOrIssue,
    affectedSubject,
    timeWindow,
    profileId: DEFAULT_ARGUS_PROFILE_ID,
  };

  const profileId = readSectionValue(markdown, profileLabels);
  if (profileId) {
    request.profileId = normalizeArgusProfileId(profileId);
  }

  const weiboClue = readSectionValue(markdown, weiboClueLabels);
  if (weiboClue) {
    request.weiboClue = weiboClue;
  }

  const decisionGoal = readSectionValue(markdown, decisionGoalLabels);
  if (decisionGoal) {
    request.decisionGoal = decisionGoal;
  }

  const knownMaterials = readListSection(markdown, knownMaterialsLabels);
  if (knownMaterials.length > 0) {
    request.knownMaterials = knownMaterials;
  }

  return request;
}

export function applyResearchProfileToMarkdown(
  markdown: string,
  profileId: ArgusProfileId
): string {
  const normalizedProfileId = normalizeArgusProfileId(profileId);
  const lines = markdown.split("\n");
  const profileLineIndex = lines.findIndex((line) =>
    profileLabels.some((label) => matchesInlineSection(line, label))
  );

  if (profileLineIndex >= 0) {
    const line = lines[profileLineIndex] ?? "";
    const prefix = line.slice(0, line.search(/[:：]/) + 1) || "Profile:";
    lines[profileLineIndex] = `${prefix} ${normalizedProfileId}`;
    return lines.join("\n");
  }

  const timeWindowIndex = lines.findIndex((line) =>
    timeWindowLabels.some((label) => matchesInlineSection(line, label))
  );
  const insertIndex = timeWindowIndex >= 0 ? timeWindowIndex + 1 : lines.length;
  lines.splice(insertIndex, 0, `Profile: ${normalizedProfileId}`);
  return lines.join("\n");
}

export function derivePreflightStatus(
  request: ResearchRequest
): PreflightStatus {
  if (!requiredFields.every((field) => hasText(request[field]))) {
    return "needs_event";
  }

  if (looksNonReportable(request)) {
    return "not_reportable";
  }

  if (!hasText(request.weiboClue) && !hasTextList(request.knownMaterials)) {
    return "needs_weibo_data";
  }

  return "reportable";
}

export function extractResearchRequest({
  messages,
  artifact,
}: {
  messages: Array<{ role?: string; parts?: unknown[] }>;
  artifact: {
    documentId: string;
    kind: string;
    title: string;
    content: string;
  };
}): ResearchRequest | null {
  const artifactRequest =
    artifact.documentId !== "init" && artifact.kind === "text"
      ? parseResearchPlanMarkdown(artifact.content)
      : null;
  const messageRequest = parseResearchPlanMarkdown(
    getLatestResearchPlanMarkdown(messages)
  );

  return artifactRequest ?? messageRequest;
}

export function buildAnalysisQuery(request: ResearchRequest): string {
  return [request.affectedSubject, request.eventOrIssue, request.timeWindow]
    .filter((part) => normalizeText(part).length > 0)
    .join(" ");
}

export function canSwitchResearchProfile({
  hasResearchRequest,
  isReadonly,
  isWorkflowRunning,
  isChatBusy,
  stage,
}: {
  hasResearchRequest: boolean;
  isReadonly: boolean;
  isWorkflowRunning: boolean;
  isChatBusy: boolean;
  stage: WorkflowStage;
}): boolean {
  return (
    hasResearchRequest &&
    !isReadonly &&
    !isWorkflowRunning &&
    !isChatBusy &&
    stage !== "analysis_running" &&
    stage !== "report_ready"
  );
}

export function deriveWorkflowSnapshot({
  messages,
  artifact,
}: {
  messages: Array<{ role?: string; parts?: unknown[] }>;
  artifact: {
    documentId: string;
    kind: string;
    title: string;
    content: string;
    isVisible: boolean;
    status: string;
    boundingBox: {
      top: number;
      left: number;
      width: number;
      height: number;
    };
  };
}): WorkflowSnapshot {
  const dataPrepVisible =
    artifact.title.startsWith("Data Prep:") ||
    artifact.title.includes("数据准备") ||
    isDataPrepMarkdown(artifact.content) ||
    hasDataPrepMarkdown(messages);
  const request = extractResearchRequest({ messages, artifact });

  if (dataPrepVisible) {
    const preflight = request
      ? derivePreflightStatus(request)
      : "needs_weibo_data";

    return {
      stage: "needs_data_prep",
      preflight,
      title: "需要微博数据准备",
      summary: "正式分析前需要先采集可支撑报告的微博证据。",
    };
  }

  if (!request) {
    return {
      stage: "collecting",
      preflight: "needs_event",
      title: "正在确认研究需求",
      summary: "请先确认事件、受影响主体和时间范围。",
    };
  }

  const preflight = derivePreflightStatus(request);
  const latestUserMessage = getLatestMessageText(messages, "user");
  const latestAssistantMessage = getLatestMessageText(messages, "assistant");

  if (containsAny(latestAssistantMessage, ["report ready", "报告已完成"])) {
    return {
      stage: "report_ready",
      preflight,
      title: "报告已完成",
      summary: "可以打开右侧报告卡片查看 HTML 报告。",
    };
  }

  if (
    containsAny(latestUserMessage, [
      "start research",
      "start analysis",
      "开始研究",
      "开始分析",
    ])
  ) {
    return {
      stage:
        preflight === "needs_weibo_data"
          ? "needs_data_prep"
          : "analysis_running",
      preflight,
      title:
        preflight === "needs_weibo_data"
          ? "需要微博数据准备"
          : "分析正在运行",
      summary:
        preflight === "needs_weibo_data"
          ? "正式分析前需要先采集可支撑报告的微博证据。"
          : "系统正在按研究计划推进分析链路。",
    };
  }

  if (containsAny(latestUserMessage, ["confirm", "确认"])) {
    return {
      stage: "confirmed",
      preflight,
      title: "研究计划已确认",
      summary:
        preflight === "needs_weibo_data"
          ? "计划已确认，但仍需要先采集微博证据。"
          : "计划已确认，可以开始正式分析。",
    };
  }

  return {
    stage: "ready_to_confirm",
    preflight,
    title: "研究计划待确认",
    summary:
      preflight === "needs_weibo_data"
        ? "请检查研究计划，确认后系统会采集微博证据。"
        : "请检查研究计划，确认后继续分析。",
  };
}

export function shouldSyncArgusWorkflowDocument({
  title,
  content,
}: {
  title: string;
  content?: string;
}): boolean {
  const normalizedTitle = normalizeText(title);
  const normalizedTitleLower = normalizedTitle.toLowerCase();

  if (
    normalizedTitleLower.startsWith("research plan") ||
    normalizedTitleLower.startsWith("data prep") ||
    normalizedTitle.includes("研究计划") ||
    normalizedTitle.includes("数据准备")
  ) {
    return true;
  }

  if (hasText(content) && parseResearchPlanMarkdown(content ?? "") !== null) {
    return true;
  }

  if (hasText(content) && isDataPrepMarkdown(content ?? "")) {
    return true;
  }

  return false;
}

function readSectionValue(markdown: string, labels: string[]): string {
  const lines = markdown.split("\n");

  for (const label of labels) {
    for (let index = 0; index < lines.length; index += 1) {
      const line = lines[index] ?? "";
      if (!matchesInlineSection(line, label)) {
        continue;
      }

      const value = normalizeMarkdownSectionLine(line).match(
        createInlineSectionPattern(label)
      )?.[1];
      if (hasText(value)) {
        return normalizeText(value ?? "");
      }

      const paragraphValue = readNextParagraphValue(lines, index);
      if (hasText(paragraphValue)) {
        return paragraphValue;
      }
    }
  }

  return "";
}

function readListSection(markdown: string, labels: string[]): string[] {
  const lines = markdown.split("\n");

  for (const label of labels) {
    const startIndex = lines.findIndex((line) =>
      matchesSectionHeader(line, label)
    );
    if (startIndex < 0) {
      continue;
    }

    const items: string[] = [];
    for (let index = startIndex + 1; index < lines.length; index += 1) {
      const line = normalizeMarkdownSectionLine(lines[index] ?? "");
      if (!hasText(line)) {
        continue;
      }
      if (isResearchPlanSectionLine(line)) {
        break;
      }
      const item = normalizeListItem(line);
      if (item) {
        items.push(item);
      }
    }

    if (items.length > 0) {
      return items;
    }
  }

  return [];
}

function readNextParagraphValue(lines: string[], startIndex: number): string {
  for (let index = startIndex + 1; index < lines.length; index += 1) {
    const line = normalizeMarkdownSectionLine(lines[index] ?? "");
    if (!hasText(line)) {
      continue;
    }
    if (isResearchPlanSectionLine(line)) {
      return "";
    }
    return normalizeListItem(line);
  }

  return "";
}

function looksNonReportable(request: ResearchRequest): boolean {
  const haystack = [
    request.eventOrIssue,
    request.affectedSubject,
    request.timeWindow,
    request.weiboClue ?? "",
    request.decisionGoal ?? "",
    ...(request.knownMaterials ?? []),
  ]
    .join(" ")
    .toLowerCase();

  return [
    "homework",
    "essay",
    "translate",
    "coding",
    "programming",
    "support ticket",
    "generic question",
  ].some((term) => haystack.includes(term));
}

function getLatestMessageText(
  messages: Array<{ role?: string; parts?: unknown[] }>,
  role: string
): string {
  for (let index = messages.length - 1; index >= 0; index -= 1) {
    const message = messages[index];
    if (message.role !== role) {
      continue;
    }

    const textParts = (message.parts ?? []).flatMap((part) => {
      if (!isTextPart(part) || !hasText(part.text)) {
        return [];
      }

      return [normalizeText(part.text)];
    });

    return textParts.join(" ");
  }

  return "";
}

function getLatestResearchPlanMarkdown(
  messages: Array<{ role?: string; parts?: unknown[] }>
): string {
  for (let index = messages.length - 1; index >= 0; index -= 1) {
    const parts = messages[index]?.parts ?? [];
    const content = parts
      .map((part) => {
        if (isTextPart(part) && hasText(part.text)) {
          return normalizeText(part.text);
        }

        if (
          isToolCreateDocumentPart(part) &&
          hasText(part.input?.content ?? part.output.content ?? "")
        ) {
          return normalizeText(
            part.input?.content ?? part.output.content ?? ""
          );
        }

        return "";
      })
      .filter((part) => hasText(part))
      .join("\n\n");

    if (parseResearchPlanMarkdown(content) !== null) {
      return content;
    }
  }

  return "";
}

function hasDataPrepMarkdown(
  messages: Array<{ role?: string; parts?: unknown[] }>
): boolean {
  for (let index = messages.length - 1; index >= 0; index -= 1) {
    const parts = messages[index]?.parts ?? [];
    const content = parts
      .map((part) => {
        if (isTextPart(part) && hasText(part.text)) {
          return normalizeText(part.text);
        }

        if (
          isToolCreateDocumentPart(part) &&
          hasText(part.input?.content ?? part.output.content ?? "")
        ) {
          return normalizeText(
            part.input?.content ?? part.output.content ?? ""
          );
        }

        return "";
      })
      .filter((part) => hasText(part))
      .join("\n\n");

    if (isDataPrepMarkdown(content)) {
      return true;
    }
  }

  return false;
}

function isDataPrepMarkdown(content: string): boolean {
  return (
    (content.includes("Data Prep:") || content.includes("数据准备")) &&
    (content.includes("Objective") || content.includes("目标")) &&
    (content.includes("Data Collection Requirements") ||
      content.includes("数据收集要求"))
  );
}

function matchesInlineSection(line: string, label: string): boolean {
  return createInlineSectionPattern(label).test(
    normalizeMarkdownSectionLine(line)
  );
}

function matchesSectionHeader(line: string, label: string): boolean {
  const normalizedLine = normalizeMarkdownSectionLine(line);
  const pattern = new RegExp(`^${escapeRegExp(label)}\\s*[:：]\\s*$`);
  return pattern.test(normalizedLine);
}

function isResearchPlanSectionLine(line: string): boolean {
  return researchPlanSectionLabels.some((label) =>
    matchesInlineSection(line, label)
  );
}

function createInlineSectionPattern(label: string): RegExp {
  return new RegExp(
    `^\\s*(?:[-*+>]\\s*)?${escapeRegExp(label)}\\s*[:：]\\s*(.*)$`
  );
}

function isTextPart(part: unknown): part is { type: "text"; text: string } {
  return Boolean(
    part &&
      typeof part === "object" &&
      "type" in part &&
      (part as { type?: unknown }).type === "text" &&
      "text" in part &&
      typeof (part as { text?: unknown }).text === "string"
  );
}

function isToolCreateDocumentPart(part: unknown): part is {
  type: "tool-createDocument";
  input?: { content?: string };
  output: { content?: string };
} {
  return Boolean(
    part &&
      typeof part === "object" &&
      "type" in part &&
      (part as { type?: unknown }).type === "tool-createDocument" &&
      "output" in part &&
      typeof (part as { output?: unknown }).output === "object" &&
      (part as { output?: { content?: unknown } }).output !== null
  );
}

function containsAny(haystack: string, needles: string[]): boolean {
  const normalizedHaystack = haystack.toLowerCase();
  return needles.some((needle) =>
    normalizedHaystack.includes(needle.toLowerCase())
  );
}

function hasText(value: string | undefined): boolean {
  return normalizeText(value ?? "").length > 0;
}

function hasTextList(values: string[] | undefined): boolean {
  return (values ?? []).some((value) => hasText(value));
}

function normalizeText(value: string): string {
  return value.trim();
}

function normalizeMarkdownSectionLine(value: string): string {
  return value
    .replace(/^#+\s*/, "")
    .replace(/[`*_]/g, "")
    .trim();
}

function normalizeListItem(value: string): string {
  return normalizeText(value.replace(/^[-+]\s*/, ""));
}

function escapeRegExp(value: string): string {
  return value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}
