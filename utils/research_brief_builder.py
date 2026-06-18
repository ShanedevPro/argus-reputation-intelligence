"""Deterministic research briefs for the original BettaFish engines."""

from __future__ import annotations

import json
from typing import Any, Mapping


ROLE_TITLES = {
    "query": "事实核验员",
    "media": "传播观察员",
    "insight": "舆情洞察员",
}

PROFILE_LENSES = {
    "generic_event_risk": (
        "Profile lens: 通用事件风险。面向需要判断事实、传播、舆情和处置优先级的决策者，"
        "关注事件边界、证据强度、风险等级、利益相关方和不确定性。"
    ),
    "artist_management": (
        "Profile lens: 艺人明星舆情。面向艺人经纪、工作室和公关团队，关注粉丝关系、"
        "路人观感、节目/合作方责任边界、艺人形象损益、回应节奏和后续沟通风险。"
    ),
    "enterprise_pr": (
        "Profile lens: 企业公关舆情。面向企业公关、品牌、客服、法务和管理层，关注事实核验、"
        "公众信任、客户沟通、责任归因、监管/法律风险、服务补救和长期声誉影响。"
    ),
}


def build_common_research_context(
    *,
    query: str,
    research_request: Mapping[str, Any] | None = None,
    evidence_manifest: Mapping[str, Any] | None = None,
    data_prep_task_id: str = "",
) -> dict[str, Any]:
    return {
        "query": str(query or "").strip(),
        "data_prep_task_id": str(data_prep_task_id or "").strip(),
        "research_request": dict(research_request or {}),
        "evidence_manifest": dict(evidence_manifest or {}),
    }


def build_engine_brief(engine_name: str, context: Mapping[str, Any]) -> str:
    engine = str(engine_name or "").strip().lower()
    role_title = ROLE_TITLES.get(engine, engine_name)
    request = dict(context.get("research_request") or {})
    manifest = dict(context.get("evidence_manifest") or {})
    counts = dict(manifest.get("counts") or {})
    keywords = manifest.get("keywords") or []
    sample_note = _build_weibo_sample_note(counts, keywords, request)

    payload = {
        "query": context.get("query", ""),
        "data_prep_task_id": context.get("data_prep_task_id", ""),
        "research_request": request,
        "weibo_sample": {
            "scope": sample_note["scope"],
            "boundary": sample_note["boundary"],
            "counts": counts,
            "keywords": keywords,
        },
        "key_posts": list(manifest.get("key_posts") or [])[:10],
        "key_comments": list(manifest.get("key_comments") or [])[:15],
    }
    search_anchor = _build_search_anchor(context.get("query", ""), request, keywords)

    return (
        f"You are the {role_title} for an Argus Weibo negative event risk brief.\n\n"
        "<ARGUS_SEARCH_ANCHOR>\n"
        f"{search_anchor}\n"
        "</ARGUS_SEARCH_ANCHOR>\n\n"
        "Use the structured context below as the event boundary. Keep findings evidence-backed.\n"
        "Do not invent dates, numbers, sources, sentiment percentages, or causal links.\n"
        "Do not claim to represent all public opinion; describe Weibo findings as collected sample evidence.\n\n"
        f"{_profile_lens(request.get('profileId'))}\n\n"
        f"{_role_rules(engine)}\n\n"
        "<ARGUS_CONTEXT_JSON>\n"
        f"{json.dumps(payload, ensure_ascii=False, indent=2)}\n"
        "</ARGUS_CONTEXT_JSON>"
    )


def _build_search_anchor(query: Any, request: Mapping[str, Any], keywords: Any) -> str:
    anchors: list[str] = []
    subject = str((request or {}).get("affectedSubject") or "").strip()
    if subject:
        anchors.append(subject)

    if isinstance(keywords, list):
        for keyword in keywords:
            text = str(keyword or "").strip()
            if text and text not in anchors:
                anchors.append(text)
            if len(anchors) >= 4:
                break

    if not anchors:
        event = str((request or {}).get("eventOrIssue") or "").strip()
        if event:
            anchors.append(event)

    if not anchors:
        anchors.append(str(query or "").strip())

    return " ".join(anchor for anchor in anchors if anchor).strip()


def _build_weibo_sample_note(
    counts: Mapping[str, Any],
    keywords: Any,
    request: Mapping[str, Any],
) -> dict[str, str]:
    keyword_count = len(keywords) if isinstance(keywords, list) else 0
    time_window = str((request or {}).get("timeWindow") or "").strip()
    scope = (
        "本次分析使用采集到的微博样本："
        f"帖子 {counts.get('posts', 0)} 条、"
        f"微博一级评论 {counts.get('comments', 0)} 条、"
        f"作者 {counts.get('authors', 0)} 个、"
        f"关键词 {counts.get('keywords', keyword_count)} 个。"
    )
    if time_window:
        scope = f"{scope} 时间范围：{time_window}。"
    return {
        "scope": scope,
        "boundary": "仅代表本次采集到的微博样本，不代表全网或全部公众意见。",
    }


def _profile_lens(profile_id: Any) -> str:
    normalized = str(profile_id or "generic_event_risk").strip().lower()
    compact = normalized.replace("_", "").replace("-", "").replace(" ", "")
    if compact == "artistmanagement":
        normalized = "artist_management"
    elif compact == "enterprisepr":
        normalized = "enterprise_pr"
    elif compact == "genericeventrisk":
        normalized = "generic_event_risk"
    return PROFILE_LENSES.get(normalized, PROFILE_LENSES["generic_event_risk"])


def _role_rules(engine: str) -> str:
    if engine == "query":
        return (
            "Focus on event existence, facts, chronology, official statements, "
            "news/web sources, uncertainty, conflicts, and evidence gaps. "
            "Do not analyze Weibo sentiment or final response advice."
        )
    if engine == "media":
        return (
            "Focus on media visibility, source mix, narrative frames, spread beyond "
            "the core Weibo sample, conflicting narratives, and evidence gaps. "
            "Do not rebuild the full factual timeline or make final risk judgments."
        )
    if engine == "insight":
        return (
            "Focus on collected Weibo posts and first-level comments: sentiment, stance, "
            "responsibility attribution, controversy points, information gaps, escalation "
            "or cooling signals. Include sample scope. Do not claim to represent all public opinion."
        )
    return "Use the supplied context and keep unsupported claims visibly uncertain."
