"""Structured Weibo evidence manifest for Argus report workflows."""

from __future__ import annotations

import re
from datetime import date, datetime, timezone
from typing import Any, Mapping, Sequence


MAX_KEY_POSTS = 20
MAX_KEY_COMMENTS = 40
MAX_SNIPPET_CHARS = 500
MIN_SIGNAL_CHARS = 3
MIN_COMMENT_CONTEXT_CHARS = 6
WEAK_SIGNAL_ONLY_SCORE = 2
EVENT_RELEVANCE_MIN_SCORE = 3
GENERIC_EVENT_WORDS = {
    "事件",
    "争议",
    "微博",
    "热搜",
    "话题",
    "讨论",
    "出圈",
    "节目",
    "回应",
    "发酵",
}
GENERIC_EVIDENCE_MARKERS = (
    "质疑",
    "担忧",
    "不满",
    "道歉",
    "补偿",
    "赔偿",
    "退款",
    "投诉",
    "维权",
    "责任",
    "回应",
    "声明",
    "解释",
    "影响",
    "风险",
    "问题",
    "处理",
    "外流",
    "泄露",
    "隐私",
    "安全",
    "事故",
    "伤亡",
    "取消",
    "延期",
    "不合适",
    "失望",
    "追问",
    "争论",
    "风波",
)
EVIDENCE_CONTEXT_RE = re.compile(
    r"(?:引发|导致|造成|带来|出现).{0,8}(?:争议|讨论|质疑|担忧|不满|风险|关注)"
    r"|被.{0,8}(?:删除|删改|剪掉|剪辑|质疑|指责|批评|吐槽|曝光|追问|调侃)"
)
LEADING_SIGNAL_PARTICLES = (
    "我当时",
    "当时",
    "自己",
    "说自己",
    "我",
    "我们",
    "真的",
)
PHRASE_SPLIT_RE = re.compile(r"[|,，。:：/\\()\[\]{}\"'!?？!；;\s、]+")
FULL_DATE_RE = re.compile(
    r"(20\d{2})\s*(?:年|-|/|\.)\s*(\d{1,2})\s*(?:月|-|/|\.)\s*(\d{1,2})"
)
CHINESE_MONTH_DAY_AFTER_RANGE_RE = re.compile(
    r"(?:至|到|~|～|—|–|-)\s*(\d{1,2})\s*月\s*(\d{1,2})"
)


def build_weibo_evidence_manifest(
    *,
    bundle: Any,
    readiness: Mapping[str, Any] | None = None,
    reportability: Mapping[str, Any] | None = None,
    import_result: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    posts = [
        dict(item)
        for item in getattr(bundle, "posts", []) or []
        if isinstance(item, Mapping)
    ]
    comments = [
        dict(item)
        for item in getattr(bundle, "comments", []) or []
        if isinstance(item, Mapping)
    ]
    metadata = dict(getattr(bundle, "metadata", {}) or {})
    keywords = [
        str(item).strip()
        for item in getattr(bundle, "keywords", []) or []
        if str(item).strip()
    ]

    research_request = _extract_research_request(metadata)
    post_relevance = _build_post_relevance(posts, research_request, keywords)

    return {
        "manifest_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "provider": str(getattr(bundle, "provider", "") or ""),
        "research_request": research_request,
        "sample_boundary": {
            "platform": "weibo",
            "comment_depth": "first_level_only",
            "represents": "collected_weibo_sample_only",
            "warning": (
                "This sample does not represent all public opinion or all Weibo "
                "discussion."
            ),
        },
        "counts": {
            "posts": len(posts),
            "comments": len(comments),
            "authors": _count_authors(posts, comments),
            "keywords": len(keywords),
        },
        "keywords": keywords,
        "collection_rounds": list(metadata.get("collection_rounds") or []),
        "stop_reason": str(
            metadata.get("fallback_stop_reason")
            or getattr(bundle, "stop_reason", "")
            or ""
        ),
        "readiness": dict(readiness or {}),
        "reportability": dict(reportability or {}),
        "import_result": dict(import_result or {}),
        "key_posts": [
            _compact_post(post)
            for post in _rank_posts(posts, research_request, keywords)[:MAX_KEY_POSTS]
        ],
        "key_comments": [
            _compact_comment(comment)
            for comment in _rank_comments(
                comments,
                research_request,
                keywords,
                post_relevance,
            )[:MAX_KEY_COMMENTS]
        ],
        "provider_errors": list(metadata.get("errors") or []),
        "truncation": {
            "post_truncated": bool(
                metadata.get("post_truncated") or metadata.get("post_cap_truncated")
            ),
            "comment_truncated": bool(metadata.get("comment_truncated")),
        },
    }


def _extract_research_request(metadata: Mapping[str, Any]) -> dict[str, Any]:
    task = metadata.get("task") if isinstance(metadata.get("task"), Mapping) else {}
    task_metadata = (
        task.get("metadata") if isinstance(task.get("metadata"), Mapping) else {}
    )
    request = (
        task_metadata.get("request")
        if isinstance(task_metadata.get("request"), Mapping)
        else {}
    )
    return dict(request)


def _count_authors(
    posts: Sequence[Mapping[str, Any]],
    comments: Sequence[Mapping[str, Any]],
) -> int:
    authors: set[str] = set()
    for item in [*posts, *comments]:
        author = str(
            item.get("author_id")
            or item.get("user_id")
            or item.get("author")
            or item.get("nickname")
            or ""
        ).strip()
        if author:
            authors.add(author)
    return len(authors)


def _rank_posts(
    posts: Sequence[Mapping[str, Any]],
    research_request: Mapping[str, Any],
    keywords: Sequence[str],
) -> list[Mapping[str, Any]]:
    eligible = [
        post
        for post in posts
        if _post_relevance_score(post, research_request, keywords) >= EVENT_RELEVANCE_MIN_SCORE
    ]
    return sorted(
        eligible,
        key=lambda item: (
            _post_relevance_score(item, research_request, keywords),
            _engagement_score(item),
            str(item.get("publish_time") or item.get("create_date_time") or ""),
        ),
        reverse=True,
    )


def _rank_comments(
    comments: Sequence[Mapping[str, Any]],
    research_request: Mapping[str, Any],
    keywords: Sequence[str],
    post_relevance: Mapping[str, int],
) -> list[Mapping[str, Any]]:
    eligible = [
        comment
        for comment in comments
        if _comment_relevance_score(comment, research_request, keywords, post_relevance)
        >= EVENT_RELEVANCE_MIN_SCORE
    ]
    return sorted(
        eligible,
        key=lambda item: (
            _comment_relevance_score(item, research_request, keywords, post_relevance),
            _engagement_score(item),
            str(item.get("create_date_time") or item.get("create_time") or ""),
        ),
        reverse=True,
    )


def _compact_post(post: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "source_id": str(post.get("content_id") or post.get("note_id") or ""),
        "source_url": str(post.get("url") or ""),
        "source_keyword": str(post.get("source_keyword") or ""),
        "author_name": str(post.get("author") or post.get("nickname") or ""),
        "created_at": str(post.get("publish_time") or post.get("create_date_time") or ""),
        "content": _snippet(post.get("content") or post.get("title") or ""),
        "engagement": _engagement_payload(post),
        "evidence_kind": "weibo_post",
    }


def _compact_comment(comment: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "source_id": str(comment.get("comment_id") or ""),
        "parent_source_id": str(comment.get("note_id") or ""),
        "author_name": str(comment.get("nickname") or ""),
        "created_at": str(comment.get("create_date_time") or ""),
        "content": _snippet(comment.get("content") or ""),
        "engagement": {"like_count": _as_int(comment.get("comment_like_count"))},
        "evidence_kind": "weibo_comment",
    }


def _engagement_score(item: Mapping[str, Any]) -> int:
    engagement = _engagement_payload(item)
    return (
        _as_int(engagement.get("like_count"))
        + _as_int(engagement.get("comment_count")) * 2
        + _as_int(engagement.get("share_count")) * 3
        + _as_int(engagement.get("repost_count")) * 3
        + _as_int(item.get("comment_like_count"))
        + _as_int(item.get("like_count"))
    )


def _engagement_payload(item: Mapping[str, Any]) -> dict[str, int]:
    engagement = item.get("engagement") if isinstance(item.get("engagement"), Mapping) else {}
    return {
        "like_count": _as_int(engagement.get("like_count") or item.get("liked_count") or item.get("like_count")),
        "comment_count": _as_int(engagement.get("comment_count") or item.get("comments_count") or item.get("comment_count")),
        "share_count": _as_int(engagement.get("share_count") or item.get("shared_count") or item.get("share_count")),
        "repost_count": _as_int(engagement.get("repost_count") or item.get("reposts_count") or item.get("repost_count")),
    }


def _build_post_relevance(
    posts: Sequence[Mapping[str, Any]],
    research_request: Mapping[str, Any],
    keywords: Sequence[str],
) -> dict[str, int]:
    relevance: dict[str, int] = {}
    for post in posts:
        source_id = str(post.get("content_id") or post.get("note_id") or "").strip()
        if source_id:
            relevance[source_id] = _post_relevance_score(post, research_request, keywords)
    return relevance


def _post_relevance_score(
    post: Mapping[str, Any],
    research_request: Mapping[str, Any],
    keywords: Sequence[str],
) -> int:
    if not _item_in_research_time_window(
        post,
        research_request,
        ("publish_time", "create_date_time", "create_time"),
    ):
        return 0

    body_text = " ".join(
        str(value or "")
        for value in (
            post.get("content"),
            post.get("title"),
        )
    )
    source_keyword = str(post.get("source_keyword") or "")
    searchable_text = " ".join([body_text, source_keyword])
    if not _has_specific_event_signal(searchable_text, research_request, keywords):
        return 0
    if not _has_subject_or_context_anchor(body_text, research_request, keywords):
        return 0

    body_score = _text_relevance_score(body_text, research_request, keywords)
    if body_score < EVENT_RELEVANCE_MIN_SCORE:
        return 0

    source_keyword_score = _text_relevance_score(
        str(post.get("source_keyword") or ""),
        research_request,
        keywords,
    )
    keyword_boost = 1 if source_keyword_score >= EVENT_RELEVANCE_MIN_SCORE else 0
    return body_score + keyword_boost


def _comment_relevance_score(
    comment: Mapping[str, Any],
    research_request: Mapping[str, Any],
    keywords: Sequence[str],
    post_relevance: Mapping[str, int],
) -> int:
    if not _item_in_research_time_window(
        comment,
        research_request,
        ("create_date_time", "create_time", "publish_time"),
    ):
        return 0

    text_score = _text_relevance_score(
        str(comment.get("content") or ""),
        research_request,
        keywords,
    )
    if text_score >= EVENT_RELEVANCE_MIN_SCORE:
        return text_score

    parent_id = str(comment.get("note_id") or comment.get("parent_source_id") or "").strip()
    parent_score = int(post_relevance.get(parent_id) or 0)
    if (
        parent_score >= EVENT_RELEVANCE_MIN_SCORE
        and _comment_has_context_signal(
            str(comment.get("content") or ""),
            research_request,
            keywords,
        )
    ):
        return max(EVENT_RELEVANCE_MIN_SCORE, parent_score - 1)
    return 0


def _text_relevance_score(
    value: str,
    research_request: Mapping[str, Any],
    keywords: Sequence[str],
) -> int:
    text = _normalize_text(value)
    if not text:
        return 0

    subject = _normalize_text(research_request.get("affectedSubject"))
    event_signals = _event_signals(research_request, keywords)
    score = 0
    if subject and subject in text:
        score += WEAK_SIGNAL_ONLY_SCORE
    for signal in event_signals:
        if signal in text:
            if _is_specific_event_signal(signal):
                score += 4 if len(signal) >= 6 else 3
            else:
                score += 1
    for cue in _generic_evidence_markers():
        if cue and cue in text:
            score += 2
    if _has_evidence_context(text):
        score += 2
    return score


def _has_specific_event_signal(
    value: str,
    research_request: Mapping[str, Any],
    keywords: Sequence[str],
) -> bool:
    text = _normalize_text(value)
    if not text:
        return False
    if any(
        signal in text and _is_specific_event_signal(signal)
        for signal in _event_signals(research_request, keywords)
    ):
        return True
    return _has_evidence_context(text)


def _has_subject_or_context_anchor(
    value: str,
    research_request: Mapping[str, Any],
    keywords: Sequence[str],
) -> bool:
    text = _normalize_text(value)
    if not text:
        return False

    subject = _normalize_text(research_request.get("affectedSubject"))
    if subject and subject in text:
        return True

    return any(anchor in text for anchor in _context_anchors(research_request, keywords))


def _context_anchors(
    research_request: Mapping[str, Any],
    keywords: Sequence[str],
) -> list[str]:
    subject = _normalize_text(research_request.get("affectedSubject"))
    anchors: list[str] = []
    for raw in keywords:
        signal = _clean_signal(str(raw or ""), subject)
        if (
            signal
            and signal not in anchors
            and not _is_specific_event_signal(signal)
            and signal not in GENERIC_EVENT_WORDS
        ):
            anchors.append(signal)
    return anchors


def _is_specific_event_signal(signal: str) -> bool:
    normalized = _normalize_text(signal)
    if not normalized:
        return False
    if normalized in GENERIC_EVENT_WORDS:
        return False
    if len(normalized) >= MIN_SIGNAL_CHARS:
        return True
    return any(marker in normalized for marker in _generic_evidence_markers())


def _event_signals(
    research_request: Mapping[str, Any],
    keywords: Sequence[str],
) -> list[str]:
    raw_values = [
        research_request.get("eventOrIssue"),
        research_request.get("weiboClue"),
        *keywords,
    ]
    subject = _normalize_text(research_request.get("affectedSubject"))
    signals: list[str] = []
    for raw in raw_values:
        text = _normalize_text(raw)
        if not text:
            continue
        for candidate in [
            text,
            *_split_signal_phrases(text),
            *_event_signal_variants(text),
        ]:
            signal = _clean_signal(candidate, subject)
            if signal and signal not in signals:
                signals.append(signal)
    return signals


def _comment_has_context_signal(
    value: str,
    research_request: Mapping[str, Any],
    keywords: Sequence[str],
) -> bool:
    text = _normalize_text(value)
    if not text:
        return False

    event_signals = _event_signals(research_request, keywords)
    if any(signal in text for signal in event_signals):
        return True

    if len(text) < MIN_COMMENT_CONTEXT_CHARS:
        return False

    subject = _normalize_text(research_request.get("affectedSubject"))
    if subject and subject in text:
        return True
    return _has_evidence_context(text) or any(
        marker in text for marker in _generic_evidence_markers()
    )


def _split_signal_phrases(value: str) -> list[str]:
    return [
        part
        for part in PHRASE_SPLIT_RE.split(value)
        if part
    ]


def _generic_evidence_markers() -> tuple[str, ...]:
    return tuple(
        marker
        for marker in (_normalize_text(item) for item in GENERIC_EVIDENCE_MARKERS)
        if marker
    )


def _has_evidence_context(text: str) -> bool:
    normalized = _normalize_text(text)
    return bool(normalized and EVIDENCE_CONTEXT_RE.search(normalized))


def _event_signal_variants(value: str) -> list[str]:
    text = _normalize_text(value)
    variants: list[str] = []
    for marker in _generic_evidence_markers():
        if not marker or marker not in text:
            continue
        start = max(0, text.find(marker) - 4)
        end = min(len(text), text.find(marker) + len(marker) + 4)
        variants.append(text[start:end])
        variants.append(marker)
    return variants


def _item_in_research_time_window(
    item: Mapping[str, Any],
    research_request: Mapping[str, Any],
    timestamp_fields: Sequence[str],
) -> bool:
    window = _research_time_window_dates(research_request)
    if not window:
        return True

    observed_date = _first_item_date(item, timestamp_fields)
    if observed_date is None:
        return True

    start, end = window
    return start <= observed_date <= end


def _research_time_window_dates(
    research_request: Mapping[str, Any],
) -> tuple[date, date] | None:
    raw_window = str((research_request or {}).get("timeWindow") or "").strip()
    if not raw_window:
        return None

    matches = list(FULL_DATE_RE.finditer(raw_window))
    parsed_dates = [_date_from_match(match) for match in matches]
    parsed_dates = [item for item in parsed_dates if item is not None]
    if len(parsed_dates) >= 2:
        start, end = parsed_dates[0], parsed_dates[-1]
        return (start, end) if start <= end else (end, start)

    if len(matches) == 1 and parsed_dates:
        first = parsed_dates[0]
        suffix = raw_window[matches[0].end():]
        month_day = CHINESE_MONTH_DAY_AFTER_RANGE_RE.search(suffix)
        if month_day:
            try:
                second = date(first.year, int(month_day.group(1)), int(month_day.group(2)))
            except ValueError:
                second = None
            if second:
                return (first, second) if first <= second else (second, first)

    return None


def _first_item_date(
    item: Mapping[str, Any],
    timestamp_fields: Sequence[str],
) -> date | None:
    for field in timestamp_fields:
        parsed = _parse_date_value(item.get(field))
        if parsed:
            return parsed
    return None


def _parse_date_value(value: Any) -> date | None:
    text = str(value or "").strip()
    if not text:
        return None
    match = FULL_DATE_RE.search(text)
    if not match:
        return None
    return _date_from_match(match)


def _date_from_match(match: re.Match[str]) -> date | None:
    try:
        return date(int(match.group(1)), int(match.group(2)), int(match.group(3)))
    except ValueError:
        return None


def _clean_signal(value: str, subject: str = "") -> str:
    signal = _normalize_text(value)
    if subject:
        signal = signal.replace(subject, "")
    signal = _strip_signal_particles(signal)
    signal = signal.strip()
    if len(signal) < MIN_SIGNAL_CHARS:
        return ""
    if signal in GENERIC_EVENT_WORDS:
        return ""
    if signal.isdigit():
        return ""
    return signal


def _strip_signal_particles(signal: str) -> str:
    previous = signal
    while previous:
        next_signal = previous
        for particle in LEADING_SIGNAL_PARTICLES:
            if next_signal.startswith(particle) and len(next_signal) > len(particle) + 1:
                next_signal = next_signal[len(particle):]
                break
        if next_signal == previous:
            return previous
        previous = next_signal
    return signal


def _normalize_text(value: Any) -> str:
    return re.sub(r"\s+", "", str(value or "")).strip()


def _as_int(value: Any) -> int:
    try:
        return int(float(value or 0))
    except (TypeError, ValueError):
        return 0


def _snippet(value: Any) -> str:
    return str(value or "").strip()[:MAX_SNIPPET_CHARS]
