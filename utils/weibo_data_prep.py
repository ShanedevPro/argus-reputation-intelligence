"""Provider selection and deterministic policy helpers for Weibo data prep."""

from __future__ import annotations

import re
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any, Iterable, Mapping, Sequence

from downstream.weibo_data.providers import (
    MediaCrawlerWeiboProvider,
    TikHubWeiboProvider,
    WeiboCollectionBundle,
    WeiboDataCaps,
    WeiboDataTask,
    WeiboDataProvider,
    WeiboReportabilityResult,
)


KEYWORD_SPLIT_RE = re.compile(r"[|,，。:：/\\()\[\]{}\"'!?？!；;\s、]+")
QUOTE_RE = re.compile(r"[\"'“”‘’《》#]([^\"'“”‘’《》#]{2,32})[\"'“”‘’《》#]")
SOCIAL_TERMS = ("微博", "热搜", "话题", "keyword", "post", "link")
MAX_KEYWORD_CHARS = 32
MIN_KEYWORD_CHARS = 2
NOISE_KEYWORDS = {
    "及",
    "和",
    "与",
    "或",
    "的",
    "了",
    "在",
    "中",
    "后",
    "随后",
    "引发",
    "广泛讨论",
    "讨论",
    "事件",
    "争议",
    "关键词",
}
MIN_REPORTABLE_COMMENTS = 25
MIN_STRONG_POST_SAMPLE = 30
MIN_STRONG_POST_SAMPLE_AUTHORS = 5
MIN_STRONG_POST_SAMPLE_KEYWORDS = 2
PROFILE_IDS = {"generic_event_risk", "artist_management", "enterprise_pr"}


def build_weibo_data_caps(settings) -> WeiboDataCaps:
    return WeiboDataCaps(
        max_keywords=int(getattr(settings, "WEIBO_DATA_MAX_KEYWORDS", 6) or 6),
        max_posts_per_keyword=int(
            getattr(settings, "WEIBO_DATA_MAX_POSTS_PER_KEYWORD", 30) or 30
        ),
        max_selected_posts=int(
            getattr(settings, "WEIBO_DATA_MAX_SELECTED_POSTS", 12) or 12
        ),
        max_comments_per_post=int(
            getattr(settings, "WEIBO_DATA_MAX_COMMENTS_PER_POST", 20) or 20
        ),
        max_comments_per_post_hard=int(
            getattr(settings, "WEIBO_DATA_MAX_COMMENTS_PER_POST_HARD", 30) or 30
        ),
        allow_subcomments=False,
    )


def select_weibo_provider(settings) -> WeiboDataProvider:
    provider_name = str(
        getattr(settings, "WEIBO_DATA_PROVIDER", "tikhub") or "tikhub"
    ).strip().lower()

    if provider_name == "mediacrawler":
        return MediaCrawlerWeiboProvider()
    if provider_name == "tikhub":
        return TikHubWeiboProvider(
            base_url=str(getattr(settings, "TIKHUB_BASE_URL", "") or ""),
            api_key=str(getattr(settings, "TIKHUB_API_KEY", "") or ""),
            timeout=int(getattr(settings, "TIKHUB_TIMEOUT", 10) or 10),
            pages_per_keyword=int(
                getattr(settings, "WEIBO_DATA_SEARCH_PAGES_PER_KEYWORD", 3) or 3
            ),
            search_type=str(getattr(settings, "WEIBO_DATA_SEARCH_TYPE", "1") or "1"),
        )
    raise ValueError(f"Unsupported Weibo data provider: {provider_name}")


def normalize_weibo_request(request: Mapping[str, Any] | None) -> dict[str, Any]:
    raw = request if isinstance(request, Mapping) else {}
    materials = raw.get("knownMaterials") or []
    if isinstance(materials, str):
        normalized_materials = _split_phrases(materials)
    else:
        normalized_materials = [
            _clean_text(item)
            for item in materials
            if _clean_text(item)
        ]

    return {
        "eventOrIssue": _clean_text(raw.get("eventOrIssue")),
        "affectedSubject": _clean_text(raw.get("affectedSubject")),
        "timeWindow": _clean_text(raw.get("timeWindow")),
        "profileId": _normalize_profile_id(raw.get("profileId")),
        "weiboClue": _clean_text(raw.get("weiboClue")),
        "decisionGoal": _clean_text(raw.get("decisionGoal")),
        "knownMaterials": normalized_materials,
    }


def derive_weibo_keywords(
    request: Mapping[str, Any] | None,
    caps: WeiboDataCaps | None = None,
) -> list[str]:
    normalized = normalize_weibo_request(request)
    limit = max(1, int(getattr(caps, "max_keywords", 6) or 6))

    candidates: list[str] = []
    subject = normalized["affectedSubject"]
    event = normalized["eventOrIssue"]
    weibo_clue = normalized["weiboClue"]
    quoted_clues = _extract_quoted_phrases(weibo_clue)

    short_event = _preferred_short_event_phrase(event, subject, quoted_clues)
    if subject and short_event:
        if event and event.startswith(subject):
            _append_unique(candidates, f"{subject} {short_event}")
        else:
            _append_unique(candidates, f"{subject}{short_event}")
    elif event:
        _append_unique(candidates, _short_event_phrase(event, ""))

    if _should_combine_subject_clues(normalized):
        _append_subject_clue_combinations(candidates, subject, normalized)
        _append_anchor_event_clue_combinations(candidates, subject, normalized)

    for quoted in [*quoted_clues, *_extract_quoted_phrases(event)]:
        _append_unique(candidates, quoted)

    for value in (
        weibo_clue,
        event,
        subject,
    ):
        _append_phrase_candidates(candidates, value)

    for material in normalized["knownMaterials"]:
        _append_phrase_candidates(candidates, material)

    return candidates[:limit]


def compile_weibo_data_task(
    request: Mapping[str, Any] | None,
    caps: WeiboDataCaps,
    *,
    provider: str = "tikhub",
    pages_per_keyword: int = 3,
    search_type: str = "1",
) -> WeiboDataTask:
    normalized = normalize_weibo_request(request)
    keywords = derive_weibo_keywords(normalized, caps)
    bounded_pages = max(1, min(3, int(pages_per_keyword or 3)))

    return WeiboDataTask(
        provider=_clean_text(provider) or "tikhub",
        platform="weibo",
        keywords=keywords,
        search={
            "endpoint": "weibo_app.fetch_search_all",
            "pages_per_keyword": bounded_pages,
            "search_type": _clean_text(search_type) or "1",
            "time_scope": _derive_tikhub_time_scope(normalized.get("timeWindow")),
        },
        comments={
            "enabled": True,
            "selected_posts": caps.max_selected_posts,
            "max_comments_per_post": caps.max_comments_per_post,
            "max_comments_per_post_hard": caps.max_comments_per_post_hard,
            "subcomments": False,
            "endpoint": "weibo_web.fetch_post_comments",
        },
        caps={**caps.to_dict(), "allow_subcomments": False},
        metadata={
            "request": normalized,
            "original_time_window": normalized.get("timeWindow", ""),
        },
    )


def evaluate_weibo_reportability(
    bundle: WeiboCollectionBundle,
    *,
    readiness: Mapping[str, Any] | None = None,
) -> WeiboReportabilityResult:
    posts = [post for post in bundle.posts if isinstance(post, Mapping)]
    comments = [comment for comment in bundle.comments if isinstance(comment, Mapping)]
    distinct_authors = {
        _clean_text(post.get("author") or post.get("nickname") or post.get("user_id"))
        for post in posts
        if _clean_text(post.get("author") or post.get("nickname") or post.get("user_id"))
    }
    keyword_buckets = {
        _clean_text(post.get("source_keyword"))
        for post in posts
        if _clean_text(post.get("source_keyword"))
    }
    counts = {
        "posts": len(posts),
        "comments": len(comments),
        "distinct_authors": len(distinct_authors),
        "keyword_buckets": len(keyword_buckets),
    }
    readiness_payload = readiness if isinstance(readiness, Mapping) else {}

    if counts["posts"] == 0 and counts["comments"] == 0:
        return _reportability_result(
            status="insufficient_data",
            can_start_analysis=False,
            stop_reason="zero_results",
            counts=counts,
            reasons=["No matching Weibo posts or comments were collected."],
            readiness=readiness_payload,
        )

    if readiness_payload.get("success") is False and readiness_payload.get("errors"):
        return _reportability_result(
            status="insufficient_data",
            can_start_analysis=False,
            stop_reason="readiness_failed",
            counts=counts,
            reasons=["Data readiness check failed."],
            readiness=readiness_payload,
        )

    if readiness_payload and readiness_payload.get("data_ready") is False:
        return _reportability_result(
            status="insufficient_data",
            can_start_analysis=False,
            stop_reason="readiness_needs_data",
            counts=counts,
            reasons=["Imported Weibo evidence did not match the analysis request."],
            readiness=readiness_payload,
        )

    if counts["posts"] < 20 and not _has_high_hotness_core_evidence(posts):
        return _reportability_result(
            status="insufficient_data",
            can_start_analysis=False,
            stop_reason="insufficient_posts",
            counts=counts,
            reasons=["Fewer than 20 relevant Weibo posts were collected."],
            readiness=readiness_payload,
        )

    comment_sample_limited = counts["comments"] < MIN_REPORTABLE_COMMENTS
    strong_post_sample = (
        counts["posts"] >= MIN_STRONG_POST_SAMPLE
        and counts["distinct_authors"] >= MIN_STRONG_POST_SAMPLE_AUTHORS
        and counts["keyword_buckets"] >= MIN_STRONG_POST_SAMPLE_KEYWORDS
    )
    if comment_sample_limited and not strong_post_sample:
        return _reportability_result(
            status="insufficient_data",
            can_start_analysis=False,
            stop_reason="insufficient_comments",
            counts=counts,
            reasons=[
                f"Fewer than {MIN_REPORTABLE_COMMENTS} first-level Weibo comments were collected."
            ],
            readiness=readiness_payload,
        )

    if counts["distinct_authors"] < 2 and counts["keyword_buckets"] < 2:
        return _reportability_result(
            status="insufficient_data",
            can_start_analysis=False,
            stop_reason="insufficient_diversity",
            counts=counts,
            reasons=["Collected evidence lacks author or keyword diversity."],
            readiness=readiness_payload,
        )

    if comment_sample_limited:
        return _reportability_result(
            status="reportable",
            can_start_analysis=True,
            stop_reason="reportable_limited_comments",
            counts=counts,
            reasons=[
                (
                    f"Only {counts['comments']} first-level Weibo comments were collected; "
                    "treat comment-level conclusions as directional."
                )
            ],
            readiness=readiness_payload,
            sample_warnings={"comment_sample_limited": True},
        )

    return _reportability_result(
        status="reportable",
        can_start_analysis=True,
        stop_reason="reportable",
        counts=counts,
        reasons=[],
        readiness=readiness_payload,
    )


def rank_weibo_posts(
    posts: Sequence[Mapping[str, Any]] | None,
    request: Mapping[str, Any] | None,
    caps: WeiboDataCaps | None = None,
) -> list[dict[str, Any]]:
    keywords = derive_weibo_keywords(request, caps)
    ranked: list[tuple[tuple[int, int, float, int, int], dict[str, Any]]] = []

    for index, post in enumerate(posts or []):
        if not isinstance(post, Mapping):
            continue
        if isinstance(post, Mapping) and post.get("is_relevant") is False:
            continue
        normalized_post = dict(post or {})
        score = _score_weibo_post(normalized_post, keywords)
        ranked.append((score + (index,), normalized_post))

    ranked.sort(
        key=lambda item: (
            -item[0][0],
            -item[0][1],
            -item[0][2],
            -item[0][3],
            item[0][4],
        )
    )
    return [post for _score, post in ranked]


def select_weibo_posts_for_comment_expansion(
    ranked_posts: Sequence[Mapping[str, Any]] | None,
    caps: WeiboDataCaps | None = None,
) -> list[dict[str, Any]]:
    limit = max(1, int(getattr(caps, "max_selected_posts", 12) or 12))
    selected: list[dict[str, Any]] = []
    seen_content_ids: set[str] = set()

    for post in ranked_posts or []:
        content_id = _normalize_identifier(
            post.get("content_id") or post.get("note_id") or post.get("id")
        )
        if content_id and content_id in seen_content_ids:
            continue
        normalized_post = dict(post or {})
        selected.append(normalized_post)
        if content_id:
            seen_content_ids.add(content_id)
        if len(selected) >= limit:
            break

    return selected


def build_weibo_collection_bundle(
    provider: str,
    request: Mapping[str, Any] | None,
    caps: WeiboDataCaps,
    *,
    posts: Sequence[Mapping[str, Any]] | None = None,
    comments: Sequence[Mapping[str, Any]] | None = None,
    metadata: Mapping[str, Any] | None = None,
    stop_reason: str = "",
) -> WeiboCollectionBundle:
    request_payload = request if isinstance(request, Mapping) else {}
    candidate_posts = (
        list(posts)
        if posts is not None
        else list(request_payload.get("posts") or [])
    )
    candidate_comments = (
        list(comments)
        if comments is not None
        else list(request_payload.get("comments") or [])
    )

    ranked_posts = rank_weibo_posts(candidate_posts, request_payload, caps)
    analysis_posts = _select_analysis_posts(ranked_posts, caps)
    selected_posts = select_weibo_posts_for_comment_expansion(analysis_posts, caps)
    selected_comments, comment_truncated = _select_weibo_comments(
        selected_posts,
        candidate_comments,
        caps,
    )

    post_truncated = len(ranked_posts) > len(analysis_posts)
    bundle_stop_reason = stop_reason or (
        "caps reached" if post_truncated or comment_truncated else ""
    )
    compiled_task = compile_weibo_data_task(
        request_payload,
        caps,
        provider=provider,
    )
    bundle_metadata = {
        "candidate_post_count": len(candidate_posts),
        "candidate_comment_count": len(candidate_comments),
        "selected_post_count": len(selected_posts),
        "selected_comment_count": len(selected_comments),
        "post_truncated": post_truncated,
        "comment_truncated": comment_truncated,
        "caps": caps.to_dict(),
        "task": compiled_task.to_dict(),
    }
    if metadata:
        bundle_metadata.update(dict(metadata))

    return WeiboCollectionBundle(
        provider=provider,
        keywords=compiled_task.keywords,
        posts=analysis_posts,
        comments=selected_comments,
        stop_reason=bundle_stop_reason,
        metadata=bundle_metadata,
    )


def _select_analysis_posts(
    ranked_posts: Sequence[Mapping[str, Any]],
    caps: WeiboDataCaps,
) -> list[dict[str, Any]]:
    per_keyword_cap = max(1, int(caps.max_posts_per_keyword or 1))
    global_cap = max(1, int(caps.max_keywords or 1)) * per_keyword_cap
    selected: list[dict[str, Any]] = []
    keyword_counts: dict[str, int] = defaultdict(int)

    for post in ranked_posts:
        keyword = _clean_text(post.get("source_keyword")) or "__unknown__"
        if keyword_counts[keyword] >= per_keyword_cap:
            continue
        selected.append(dict(post))
        keyword_counts[keyword] += 1
        if len(selected) >= global_cap:
            break

    return selected


def _select_weibo_comments(
    selected_posts: Sequence[Mapping[str, Any]],
    comments: Sequence[Mapping[str, Any]] | None,
    caps: WeiboDataCaps,
) -> tuple[list[dict[str, Any]], bool]:
    comments_by_note_id: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for comment in comments or []:
        if isinstance(comment, Mapping) and comment.get("is_relevant") is False:
            continue
        normalized_comment = dict(comment or {})
        if not caps.allow_subcomments and _clean_text(
            normalized_comment.get("parent_comment_id")
        ):
            continue
        note_id = _normalize_identifier(
            normalized_comment.get("note_id")
            or normalized_comment.get("content_id")
            or normalized_comment.get("noteId")
        )
        if not note_id:
            continue
        comments_by_note_id[note_id].append(normalized_comment)

    selected_comments: list[dict[str, Any]] = []
    truncated = False
    per_post_cap = max(1, int(caps.max_comments_per_post or 1))
    per_post_hard_cap = max(
        per_post_cap,
        int(caps.max_comments_per_post_hard or per_post_cap),
    )

    for post in selected_posts:
        content_id = _normalize_identifier(
            post.get("content_id") or post.get("note_id") or post.get("id")
        )
        if not content_id:
            continue
        ranked_comments = sorted(
            comments_by_note_id.get(content_id, []),
            key=lambda item: (
                -_as_int(
                    item.get("comment_like_count")
                    or item.get("like_count")
                    or item.get("liked_count")
                ),
                -_parse_timestamp(item.get("create_time") or item.get("create_date_time")),
                _clean_text(item.get("comment_id") or item.get("id")),
            ),
        )
        effective_cap = min(per_post_cap, per_post_hard_cap)
        selected_slice = ranked_comments[:effective_cap]
        if len(ranked_comments) > len(selected_slice):
            truncated = True
        selected_comments.extend(selected_slice)

    return selected_comments, truncated


def _score_weibo_post(
    post: Mapping[str, Any],
    keywords: Sequence[str],
) -> tuple[int, int, float, int]:
    haystack = " ".join(
        _clean_text(post.get(field))
        for field in ("title", "content", "author", "source_keyword", "url")
    ).lower()
    relevance = 0
    for index, keyword in enumerate(keywords):
        normalized_keyword = _clean_text(keyword).lower()
        if normalized_keyword and normalized_keyword in haystack:
            relevance += (len(keywords) - index) * 100

    engagement = post.get("engagement") if isinstance(post.get("engagement"), Mapping) else {}
    hotness = (
        _as_int(engagement.get("like_count"))
        + _as_int(engagement.get("comment_count")) * 2
        + _as_int(engagement.get("share_count")) * 3
        + _as_int(engagement.get("repost_count")) * 3
    )
    hotness += _as_int(post.get("liked_count"))
    hotness += _as_int(post.get("comments_count")) * 2
    hotness += _as_int(post.get("shared_count")) * 3

    recency = _parse_timestamp(
        post.get("publish_time")
        or post.get("create_date_time")
        or post.get("create_time")
    )
    diversity = len(
        {
            value
            for value in (
                _clean_text(post.get("source_keyword")),
                _clean_text(post.get("author")),
                _clean_text(post.get("title")),
            )
            if value
        }
    )
    return relevance, hotness, recency, diversity


def _append_phrase_candidates(target: list[str], value: Any) -> None:
    text = _clean_text(value)
    if not text:
        return
    _append_unique(target, text)
    for part in _split_phrases(text):
        _append_unique(target, part)


def _append_unique(target: list[str], value: str) -> None:
    candidate = _normalize_keyword_candidate(value)
    if candidate and candidate not in target:
        target.append(candidate)


def _append_social_terms(target: list[str], *values: Any) -> None:
    haystack = " ".join(_clean_text(value).lower() for value in values if _clean_text(value))
    for term in SOCIAL_TERMS:
        if term.lower() in haystack:
            _append_unique(target, term)


def _append_subject_clue_combinations(
    target: list[str],
    subject: str,
    normalized_request: Mapping[str, Any],
) -> None:
    subject_text = _clean_text(subject)
    if not subject_text:
        return

    clues: list[str] = []
    for value in (
        normalized_request.get("weiboClue"),
        *list(normalized_request.get("knownMaterials") or []),
    ):
        for phrase in _split_phrases(_clean_text(value)):
            clue = _normalize_keyword_candidate(phrase)
            if not clue:
                continue
            if clue == subject_text or subject_text in clue:
                continue
            if clue in clues:
                continue
            clues.append(clue)

    selected: list[str] = []
    action_clues = [clue for clue in clues if _event_clue_weight(clue) >= 8]
    if action_clues:
        selected.append(
            sorted(
                action_clues,
                key=lambda clue: (-_event_clue_weight(clue), clues.index(clue)),
            )[0]
        )

    for clue in clues:
        if clue in selected:
            continue
        if _is_distinct_clue(clue):
            selected.append(clue)
            break

    for clue in clues:
        if len(selected) >= 2:
            break
        if clue not in selected:
            selected.append(clue)

    for clue in selected[:2]:
        _append_unique(target, f"{subject_text} {clue}")


def _append_anchor_event_clue_combinations(
    target: list[str],
    subject: str,
    normalized_request: Mapping[str, Any],
) -> None:
    clues = _ordered_clues(normalized_request)
    if not clues:
        return

    anchors = [
        clue
        for clue in clues
        if _looks_like_specific_anchor(clue, subject)
    ]
    if not anchors:
        return

    event_phrases = _event_phrases_from_clues(clues)
    for anchor in anchors[:2]:
        for phrase in event_phrases[:2]:
            _append_unique(target, f"{anchor} {phrase}")


def _ordered_clues(normalized_request: Mapping[str, Any]) -> list[str]:
    clues: list[str] = []
    for value in (
        normalized_request.get("weiboClue"),
        *list(normalized_request.get("knownMaterials") or []),
    ):
        for phrase in _split_phrases(_clean_text(value)):
            clue = _normalize_keyword_candidate(phrase)
            if clue and clue not in clues:
                clues.append(clue)
    return clues


def _looks_like_specific_anchor(value: str, subject: str) -> bool:
    text = _clean_text(value)
    subject_text = _clean_text(subject)
    if not text or text == subject_text:
        return False
    if _event_clue_weight(text) >= 8:
        return False
    return bool(re.search(r"[A-Za-z0-9]", text))


def _event_phrases_from_clues(clues: Sequence[str]) -> list[str]:
    group_phrases: list[str] = []
    single_phrases: list[str] = []
    response_phrases: list[str] = []
    current_group: list[str] = []
    response_clues: list[str] = []

    for clue in clues:
        if _event_clue_weight(clue) >= 8:
            if "回应" in clue:
                response_clues.append(clue)
            else:
                current_group.append(clue)
            continue
        if current_group:
            _append_event_group_phrase(group_phrases, single_phrases, current_group)
            current_group = []

    if current_group:
        _append_event_group_phrase(group_phrases, single_phrases, current_group)

    for response in response_clues:
        previous_actions = [
            clue
            for clue in clues[: clues.index(response)]
            if _event_clue_weight(clue) >= 8 and "回应" not in clue
        ]
        if previous_actions:
            _append_unique(response_phrases, f"{previous_actions[-1]}回应")
        _append_unique(response_phrases, response)

    return [*group_phrases, *response_phrases, *single_phrases]


def _append_event_group_phrase(
    group_target: list[str],
    single_target: list[str],
    group: Sequence[str],
) -> None:
    if not group:
        return
    if len(group) >= 2:
        _append_unique(group_target, "".join(group[:3]))
    for clue in group:
        _append_unique(single_target, clue)


def _should_combine_subject_clues(normalized_request: Mapping[str, Any]) -> bool:
    time_window = _clean_text(normalized_request.get("timeWindow"))
    return bool(re.search(r"20\d{2}", time_window))


def _is_distinct_clue(value: str) -> bool:
    text = _clean_text(value)
    if len(text) < 4:
        return False
    return _event_clue_weight(text) <= 4


def _event_clue_weight(value: str) -> int:
    text = _clean_text(value)
    weight = 0
    if "取消" in text:
        weight += 14
    if any(token in text for token in ("延期", "道歉", "补偿", "事故", "起火", "碰撞", "回应", "争议")):
        weight += 10
    if any(token in text for token in ("演唱会", "音乐会", "发布会", "直播", "节目", "车辆", "品牌")):
        weight += 4
    return weight


def _is_search_noise_candidate(value: str) -> bool:
    normalized = _clean_text(value).lower()
    if len(normalized) < MIN_KEYWORD_CHARS:
        return True
    if normalized in {term.lower() for term in SOCIAL_TERMS}:
        return True
    if normalized in {term.lower() for term in NOISE_KEYWORDS}:
        return True
    return False


def _split_phrases(value: str) -> list[str]:
    return [
        part.strip(" -_")
        for part in KEYWORD_SPLIT_RE.split(_clean_text(value))
        if part.strip(" -_")
    ]


def _strip_prefix(text: str, prefix: str) -> str:
    cleaned_text = _clean_text(text)
    cleaned_prefix = _clean_text(prefix)
    if not cleaned_text or not cleaned_prefix:
        return ""
    if cleaned_text.startswith(cleaned_prefix):
        return cleaned_text[len(cleaned_prefix):].strip(" -_:/|，,、")
    return ""


def _normalize_keyword_candidate(value: Any) -> str:
    candidate = _clean_text(value)
    candidate = candidate.strip(" -_:/|，,、。；;：:（）()[]【】")
    if not candidate:
        return ""
    if _is_search_noise_candidate(candidate):
        return ""
    if len(candidate) > MAX_KEYWORD_CHARS:
        return ""
    return candidate


def _extract_quoted_phrases(value: str) -> list[str]:
    phrases: list[str] = []
    for match in QUOTE_RE.finditer(_clean_text(value)):
        phrase = _normalize_keyword_candidate(match.group(1))
        if phrase and phrase not in phrases:
            phrases.append(phrase)
    return phrases


def _short_event_phrase(event: str, subject: str) -> str:
    text = _strip_prefix(event, subject)
    if not text:
        text = event
    parts = _split_phrases(text)
    for part in parts:
        candidate = _truncate_event_connector_tail(part)
        candidate = _normalize_keyword_candidate(candidate)
        if candidate:
            return candidate
    return _normalize_keyword_candidate(text)


def _preferred_short_event_phrase(
    event: str,
    subject: str,
    clue_phrases: Sequence[str],
) -> str:
    for phrase in clue_phrases:
        if phrase != subject and subject not in phrase:
            return phrase
    return _short_event_phrase(event, subject)


def _truncate_event_connector_tail(value: str) -> str:
    text = _clean_text(value)
    for connector in ("引发", "随后", "因", "出圈"):
        index = text.find(connector)
        if index > 0:
            return text[:index]
    return text


def _normalize_identifier(value: Any) -> str:
    return _clean_text(value)


def _clean_text(value: Any) -> str:
    if value is None:
        return ""
    return " ".join(str(value).strip().split())


def _normalize_profile_id(value: Any) -> str:
    normalized = _clean_text(value).lower()
    compact = normalized.replace("_", "").replace("-", "").replace(" ", "")
    aliases = {
        "genericeventrisk": "generic_event_risk",
        "generic": "generic_event_risk",
        "artistmanagement": "artist_management",
        "artist": "artist_management",
        "enterprisepr": "enterprise_pr",
        "enterprise": "enterprise_pr",
    }
    if normalized in PROFILE_IDS:
        return normalized
    return aliases.get(compact, "generic_event_risk")


def _as_int(value: Any) -> int:
    try:
        if value is None or value == "":
            return 0
        return int(float(str(value).strip()))
    except (TypeError, ValueError):
        return 0


def _parse_timestamp(value: Any) -> float:
    if value is None or value == "":
        return 0.0
    if isinstance(value, (int, float)):
        numeric = float(value)
        if numeric > 10_000_000_000:
            return numeric / 1000.0
        return numeric

    text = _clean_text(value)
    normalized = text.replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(normalized).timestamp()
    except ValueError:
        pass

    for fmt in (
        "%Y-%m-%d %H:%M:%S%z",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d",
        "%Y/%m/%d %H:%M:%S",
        "%Y/%m/%d",
    ):
        try:
            parsed = datetime.strptime(text, fmt)
        except ValueError:
            continue
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.timestamp()

    return 0.0


def _derive_tikhub_time_scope(value: Any) -> str:
    text = _clean_text(value).lower()
    if not text:
        return "auto"
    if any(token in text for token in ("24小时", "today", "day", "昨天", "今日", "今天")):
        return "day"
    if any(token in text for token in ("一周", "7天", "七天", "week")):
        return "week"
    if any(token in text for token in ("月", "month", "三个月", "90天", "最近")):
        return "month"
    return "auto"


def _has_high_hotness_core_evidence(posts: Sequence[Mapping[str, Any]]) -> bool:
    for post in posts:
        engagement = post.get("engagement") if isinstance(post.get("engagement"), Mapping) else {}
        hotness = (
            _as_int(engagement.get("like_count"))
            + _as_int(engagement.get("comment_count")) * 2
            + _as_int(engagement.get("share_count")) * 3
            + _as_int(engagement.get("repost_count")) * 3
            + _as_int(post.get("liked_count"))
            + _as_int(post.get("comments_count")) * 2
            + _as_int(post.get("shared_count")) * 3
        )
        if hotness >= 1000:
            return True
    return False


def _reportability_result(
    *,
    status: str,
    can_start_analysis: bool,
    stop_reason: str,
    counts: dict[str, int],
    reasons: list[str],
    readiness: Mapping[str, Any],
    sample_warnings: Mapping[str, Any] | None = None,
) -> WeiboReportabilityResult:
    return WeiboReportabilityResult(
        status=status,
        can_start_analysis=can_start_analysis,
        stop_reason=stop_reason,
        counts=counts,
        reasons=reasons,
        metadata={
            "readiness": dict(readiness),
            **({"sample_warnings": dict(sample_warnings)} if sample_warnings else {}),
        },
    )


__all__ = [
    "build_weibo_collection_bundle",
    "build_weibo_data_caps",
    "compile_weibo_data_task",
    "derive_weibo_keywords",
    "evaluate_weibo_reportability",
    "normalize_weibo_request",
    "rank_weibo_posts",
    "select_weibo_posts_for_comment_expansion",
    "select_weibo_provider",
]
