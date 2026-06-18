import assert from "node:assert/strict";
import test from "node:test";
import {
  applyResearchProfileToMarkdown,
  buildAnalysisQuery,
  buildResearchPlanMarkdown,
  canSwitchResearchProfile,
  derivePreflightStatus,
  deriveWorkflowSnapshot,
  extractResearchRequest,
  parseResearchPlanMarkdown,
  shouldSyncArgusWorkflowDocument,
} from "./workflow";

const request = {
  eventOrIssue: "Xiaomi Auto delivery delay complaints",
  affectedSubject: "Xiaomi Auto",
  timeWindow: "last 3 months",
  decisionGoal: "understand whether the issue is escalating",
};

test("buildResearchPlanMarkdown uses the expected section labels", () => {
  const markdown = buildResearchPlanMarkdown(request);

  assert.match(markdown, /Event or issue:/);
  assert.match(markdown, /Affected subject:/);
  assert.match(markdown, /Time window:/);
  assert.match(markdown, /Profile:/);
  assert.match(markdown, /Weibo clue:/);
  assert.match(markdown, /Decision goal:/);
  assert.match(markdown, /Known materials:/);
  assert.match(markdown, /Preflight:/);
  assert.match(markdown, /Suggested analysis path:/);
});

test("parseResearchPlanMarkdown recovers the structured request", () => {
  const markdown = buildResearchPlanMarkdown({
    ...request,
    weiboClue: "xiaomi auto",
    knownMaterials: ["Weibo hot search link", "User screenshot"],
  });

  const parsed = parseResearchPlanMarkdown(markdown);

  assert.deepEqual(parsed, {
    eventOrIssue: "Xiaomi Auto delivery delay complaints",
    affectedSubject: "Xiaomi Auto",
    timeWindow: "last 3 months",
    profileId: "generic_event_risk",
    weiboClue: "xiaomi auto",
    decisionGoal: "understand whether the issue is escalating",
    knownMaterials: ["Weibo hot search link", "User screenshot"],
  });
});

test("Research Plan profile defaults to generic and accepts Chinese profile labels", () => {
  assert.equal(
    parseResearchPlanMarkdown(
      [
        "# 研究计划",
        "",
        "事件或议题：袁娅维成都音乐会临时取消",
        "研究对象：袁娅维及其经纪演出团队",
        "时间范围：2022-12-23 至 2023-01-05",
      ].join("\n")
    )?.profileId,
    "generic_event_risk"
  );

  assert.equal(
    parseResearchPlanMarkdown(
      [
        "# 研究计划",
        "",
        "事件或议题：袁娅维成都音乐会临时取消",
        "研究对象：袁娅维及其经纪演出团队",
        "时间范围：2022-12-23 至 2023-01-05",
        "分析画像：艺人明星舆情",
      ].join("\n")
    )?.profileId,
    "artist_management"
  );

  assert.equal(
    parseResearchPlanMarkdown(
      [
        "# Research Plan: Xiaomi SU7",
        "",
        "Event or issue: Xiaomi SU7 collision and fire controversy",
        "Affected subject: Xiaomi Auto",
        "Time window: 2025-03-29 to 2025-04-30",
        "Profile: enterprise_pr",
      ].join("\n")
    )?.profileId,
    "enterprise_pr"
  );
});

test("applyResearchProfileToMarkdown updates only the profile field", () => {
  const markdown = buildResearchPlanMarkdown({
    ...request,
    profileId: "generic_event_risk",
    weiboClue: "xiaomi auto",
  });

  const updated = applyResearchProfileToMarkdown(markdown, "enterprise_pr");
  const parsed = parseResearchPlanMarkdown(updated);

  assert.equal(parsed?.profileId, "enterprise_pr");
  assert.equal(parsed?.eventOrIssue, request.eventOrIssue);
  assert.equal(parsed?.affectedSubject, request.affectedSubject);
  assert.equal(parsed?.timeWindow, request.timeWindow);
  assert.match(updated, /Profile: enterprise_pr/);
});

test("canSwitchResearchProfile blocks profile choice while chat is busy", () => {
  assert.equal(
    canSwitchResearchProfile({
      hasResearchRequest: true,
      isReadonly: false,
      isWorkflowRunning: false,
      isChatBusy: true,
      stage: "ready_to_confirm",
    }),
    false
  );

  assert.equal(
    canSwitchResearchProfile({
      hasResearchRequest: true,
      isReadonly: false,
      isWorkflowRunning: true,
      isChatBusy: false,
      stage: "analysis_running",
    }),
    false
  );

  assert.equal(
    canSwitchResearchProfile({
      hasResearchRequest: true,
      isReadonly: false,
      isWorkflowRunning: false,
      isChatBusy: false,
      stage: "report_ready",
    }),
    false
  );
});

test("derivePreflightStatus asks for Weibo evidence when the plan has none", () => {
  assert.equal(
    derivePreflightStatus({
      ...request,
      weiboClue: "",
      knownMaterials: [],
    }),
    "needs_weibo_data"
  );

  assert.equal(
    derivePreflightStatus({
      ...request,
      weiboClue: "xiaomi auto delivery complaints",
      knownMaterials: ["https://weibo.com/xyz"],
    }),
    "reportable"
  );
});

test("deriveWorkflowSnapshot shows confirmation and data prep states", () => {
  const readySnapshot = deriveWorkflowSnapshot({
    messages: [],
    artifact: {
      documentId: "doc-1",
      kind: "text",
      title: "Research Plan: Xiaomi Auto",
      content: buildResearchPlanMarkdown(request),
      status: "idle",
      isVisible: false,
      boundingBox: {
        top: 0,
        left: 0,
        width: 0,
        height: 0,
      },
    },
  });

  assert.equal(readySnapshot.stage, "ready_to_confirm");
  assert.equal(readySnapshot.preflight, "needs_weibo_data");

  const runningSnapshot = deriveWorkflowSnapshot({
    messages: [
      {
        role: "user",
        parts: [{ type: "text", text: "Start research." }],
      },
    ],
    artifact: {
      documentId: "doc-1",
      kind: "text",
      title: "Research Plan: Xiaomi Auto",
      content: buildResearchPlanMarkdown({
        ...request,
        weiboClue: "xiaomi auto delivery complaints",
        knownMaterials: ["https://weibo.com/abc"],
      }),
      status: "idle",
      isVisible: false,
      boundingBox: {
        top: 0,
        left: 0,
        width: 0,
        height: 0,
      },
    },
  });

  assert.equal(runningSnapshot.stage, "analysis_running");
  assert.equal(runningSnapshot.preflight, "reportable");
});

test("deriveWorkflowSnapshot can read a Research Plan from chat messages", () => {
  const snapshot = deriveWorkflowSnapshot({
    messages: [
      {
        role: "assistant",
        parts: [
          {
            type: "text",
            text: [
              "# Research Plan: Tesla China",
              "",
              "Event or issue: Tesla safety complaints in China",
              "Affected subject: Tesla (China)",
              "Time window: Last 3 months",
              "Weibo clue:",
              "Decision goal:",
              "Known materials:",
              "Preflight:",
              "",
              "Suggested analysis path:",
            ].join("\n"),
          },
        ],
      },
    ],
    artifact: {
      documentId: "init",
      kind: "text",
      title: "",
      content: "",
      status: "idle",
      isVisible: false,
      boundingBox: {
        top: 0,
        left: 0,
        width: 0,
        height: 0,
      },
    },
  });

  assert.equal(snapshot.stage, "ready_to_confirm");
  assert.equal(snapshot.preflight, "needs_weibo_data");
});

test("deriveWorkflowSnapshot recognizes a Chinese Research Plan from chat messages", () => {
  const snapshot = deriveWorkflowSnapshot({
    messages: [
      {
        role: "assistant",
        parts: [
          {
            type: "text",
            text: [
              "# 研究计划",
              "",
              "Event or issue: 负面传闻",
              "Affected subject: 钛动科技",
              "Time window: 最近一个月",
            ].join("\n"),
          },
        ],
      },
    ],
    artifact: {
      documentId: "init",
      kind: "text",
      title: "",
      content: "",
      status: "idle",
      isVisible: false,
      boundingBox: {
        top: 0,
        left: 0,
        width: 0,
        height: 0,
      },
    },
  });

  assert.equal(snapshot.stage, "ready_to_confirm");
  assert.equal(snapshot.title, "研究计划待确认");
});

test("deriveWorkflowSnapshot accepts affected subject phrasing from generated Chinese plans", () => {
  const snapshot = deriveWorkflowSnapshot({
    messages: [],
    artifact: {
      documentId: "doc-1",
      kind: "text",
      title: "Research Plan: 王鹤棣",
      content: [
        "# Research Plan: 王鹤棣",
        "",
        "事件或议题：王鹤棣在《亲爱的客栈2026》中因颁奖感到不适并发微博回应。",
        "受影响主体：王鹤棣",
        "时间窗口：2026年5月1日至2026年5月29日",
        "微博线索：不舒服文学",
      ].join("\n"),
      status: "idle",
      isVisible: false,
      boundingBox: {
        top: 0,
        left: 0,
        width: 0,
        height: 0,
      },
    },
  });

  assert.equal(snapshot.stage, "ready_to_confirm");
  assert.equal(snapshot.title, "研究计划待确认");
  assert.equal(snapshot.preflight, "reportable");
});

test("parseResearchPlanMarkdown accepts Chinese field labels", () => {
  const parsed = parseResearchPlanMarkdown(
    [
      "# 研究计划",
      "",
      "事件或议题：负面传闻",
      "研究对象：钛动科技",
      "时间范围：最近一个月",
      "微博线索：吴亦凡 热搜",
      "决策目标：判断是否值得继续追踪",
      "已知材料：",
      "- 用户截图",
    ].join("\n")
  );

  assert.deepEqual(parsed, {
    eventOrIssue: "负面传闻",
    affectedSubject: "钛动科技",
    timeWindow: "最近一个月",
    profileId: "generic_event_risk",
    weiboClue: "吴亦凡 热搜",
    decisionGoal: "判断是否值得继续追踪",
    knownMaterials: ["用户截图"],
  });
});

test("parseResearchPlanMarkdown accepts emphasized field labels", () => {
  const parsed = parseResearchPlanMarkdown(
    [
      "# Research Plan: Tesla China",
      "",
      "**Event or issue:** Tesla safety complaints in China",
      "",
      "**Affected subject:** Tesla (China)",
      "",
      "**Time window:** Last 3 months",
    ].join("\n")
  );

  assert.deepEqual(parsed, {
    eventOrIssue: "Tesla safety complaints in China",
    affectedSubject: "Tesla (China)",
    timeWindow: "Last 3 months",
    profileId: "generic_event_risk",
  });
});

test("parseResearchPlanMarkdown accepts field labels followed by paragraph values", () => {
  const parsed = parseResearchPlanMarkdown(
    [
      "Research Plan: 王鹤棣",
      "",
      "Event or issue:",
      "",
      '王鹤棣在《亲爱的客栈2026》收官颁奖环节因感到不适，随后在微博发布28字回应（"我当时确实不舒服"），引发"不舒服文学"网络造梗事件。',
      "",
      "Affected subject:",
      "",
      "王鹤棣（演员、艺人）",
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
    ].join("\n")
  );

  assert.equal(
    parsed?.eventOrIssue,
    '王鹤棣在《亲爱的客栈2026》收官颁奖环节因感到不适，随后在微博发布28字回应（"我当时确实不舒服"），引发"不舒服文学"网络造梗事件。'
  );
  assert.equal(parsed?.affectedSubject, "王鹤棣（演员、艺人）");
  assert.equal(parsed?.timeWindow, "2026年5月1日 — 2026年5月29日");
  assert.equal(
    parsed?.weiboClue,
    '关键词："不舒服文学"、"王鹤棣"、"我当时确实不舒服"、"亲爱的客栈"'
  );
  assert.deepEqual(parsed?.knownMaterials, [
    "《亲爱的客栈2026》收官颁奖视频片段",
    "王鹤棣28字微博原文",
  ]);
});

test("deriveWorkflowSnapshot unlocks paragraph-style Research Plan messages", () => {
  const snapshot = deriveWorkflowSnapshot({
    messages: [
      {
        role: "assistant",
        parts: [
          {
            type: "text",
            text: [
              "Research Plan: 王鹤棣",
              "",
              "Event or issue:",
              "",
              '王鹤棣在《亲爱的客栈2026》中因颁奖感到不适并发微博回应（"我当时确实不舒服"）引发"不舒服文学"出圈',
              "",
              "Affected subject:",
              "",
              "王鹤棣",
              "",
              "Time window:",
              "",
              "2026年5月1日 — 2026年5月29日",
            ].join("\n"),
          },
        ],
      },
    ],
    artifact: {
      documentId: "init",
      kind: "text",
      title: "",
      content: "",
      status: "idle",
      isVisible: false,
      boundingBox: {
        top: 0,
        left: 0,
        width: 0,
        height: 0,
      },
    },
  });

  assert.equal(snapshot.stage, "ready_to_confirm");
  assert.notEqual(snapshot.preflight, "needs_event");
});

test("deriveWorkflowSnapshot reads Research Plan content from createDocument input", () => {
  const snapshot = deriveWorkflowSnapshot({
    messages: [
      {
        role: "assistant",
        parts: [
          {
            type: "tool-createDocument",
            input: {
              title: "Research Plan: Tesla China",
              kind: "text",
              content: [
                "# Research Plan: Tesla China",
                "",
                "**Event or issue:** Tesla safety complaints in China",
                "",
                "**Affected subject:** Tesla (China)",
                "",
                "**Time window:** Last 3 months",
              ].join("\n"),
            },
            output: {
              id: "doc-1",
              title: "Research Plan: Tesla China",
              kind: "text",
              content: "A document was created and is now visible to the user.",
            },
          },
        ],
      },
    ],
    artifact: {
      documentId: "init",
      kind: "text",
      title: "",
      content: "",
      status: "idle",
      isVisible: false,
      boundingBox: {
        top: 0,
        left: 0,
        width: 0,
        height: 0,
      },
    },
  });

  assert.equal(snapshot.stage, "ready_to_confirm");
  assert.equal(snapshot.preflight, "needs_weibo_data");
});

test("shouldSyncArgusWorkflowDocument accepts Chinese plan titles with valid content", () => {
  assert.equal(
    shouldSyncArgusWorkflowDocument({
      title: "研究计划",
      content: [
        "# 研究计划",
        "",
        "Event or issue: 负面传闻",
        "Affected subject: 钛动科技",
        "Time window: 最近一个月",
      ].join("\n"),
    }),
    true
  );

  assert.equal(
    shouldSyncArgusWorkflowDocument({
      title: "Meeting notes",
      content: "This is not an Argus workflow document.",
    }),
    false
  );
});

test("deriveWorkflowSnapshot recognizes data prep messages", () => {
  const snapshot = deriveWorkflowSnapshot({
    messages: [
      {
        role: "assistant",
        parts: [
          {
            type: "text",
            text: [
              "Data Prep: Tesla Safety Complaints (China)",
              "",
              "Objective",
              "",
              "Prepare Weibo data collection framework for Tesla safety complaints analysis.",
              "",
              "Data Collection Requirements",
              "",
              "1. Core Search Terms",
            ].join("\n"),
          },
        ],
      },
    ],
    artifact: {
      documentId: "init",
      kind: "text",
      title: "",
      content: "",
      status: "idle",
      isVisible: false,
      boundingBox: {
        top: 0,
        left: 0,
        width: 0,
        height: 0,
      },
    },
  });

  assert.equal(snapshot.stage, "needs_data_prep");
  assert.equal(snapshot.title, "需要微博数据准备");
});

test("extractResearchRequest prefers the visible artifact over chat messages", () => {
  const artifactRequest = {
    ...request,
    eventOrIssue: "Artifact issue",
  };

  const extracted = extractResearchRequest({
    messages: [
      {
        role: "assistant",
        parts: [
          {
            type: "text",
            text: buildResearchPlanMarkdown({
              ...request,
              eventOrIssue: "Message issue",
            }),
          },
        ],
      },
    ],
    artifact: {
      documentId: "doc-1",
      kind: "text",
      title: "Research Plan: Xiaomi Auto",
      content: buildResearchPlanMarkdown(artifactRequest),
    },
  });

  assert.equal(extracted?.eventOrIssue, "Artifact issue");
});

test("buildAnalysisQuery joins subject, event, and time window", () => {
  assert.equal(
    buildAnalysisQuery({
      eventOrIssue: "交付争议",
      affectedSubject: "小米SU7",
      timeWindow: "最近三个月",
    }),
    "小米SU7 交付争议 最近三个月"
  );
});
