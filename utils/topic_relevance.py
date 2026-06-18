"""Small deterministic topic relevance checks."""

from __future__ import annotations

import json
import re
from typing import Any, Dict, Iterable, List, Mapping


ARGUS_SEARCH_ANCHOR_RE = re.compile(
    r"<ARGUS_SEARCH_ANCHOR>\s*(.*?)\s*</ARGUS_SEARCH_ANCHOR>",
    flags=re.DOTALL,
)
ARGUS_CONTEXT_JSON_RE = re.compile(
    r"<ARGUS_CONTEXT_JSON>\s*(.*?)\s*</ARGUS_CONTEXT_JSON>",
    flags=re.DOTALL,
)

WEAK_EVENT_MARKERS = (
    "争议",
    "事件",
    "风险",
    "舆情",
    "回应",
    "道歉",
    "声明",
    "补偿",
    "赔偿",
    "取消",
    "延期",
    "沟通",
    "票务",
    "演唱会",
    "事故",
    "碰撞",
    "起火",
    "维权",
)
CONTEXT_ONLY_MARKERS = (
    "节目",
    "综艺",
    "客栈",
    "演唱会",
    "活动",
    "发布会",
    "直播",
    "官微",
    "超话",
)
EVIDENCE_CONTEXT_MARKERS = (
    "道歉",
    "质疑",
    "争议",
    "不满",
    "担忧",
    "投诉",
    "维权",
    "补偿",
    "赔偿",
    "退款",
    "不公",
    "不适",
    "不舒服",
    "泄露",
    "外流",
    "起火",
    "碰撞",
    "事故",
    "延期",
    "取消",
    "回应",
    "声明",
)
EVENT_CONNECTOR_RE = re.compile(
    r"(?:并|且|后|随后|以及|和|与|因|因其|由于|关于|围绕|针对|引发|导致|造成|带来|回应|称|表示|发布|发文|宣布|出现|发生|涉及|有关)"
)
EVENT_CONNECTOR_PREFIX_RE = re.compile(
    r"^(?:并|且|后|随后|以及|和|与|因|因其|由于|关于|围绕|针对|引发|导致|造成|带来|回应|称|表示|发布|发文|宣布|出现|发生|涉及|有关)+"
)


def _normalize_text(value: Any) -> str:
    text = str(value or "").lower()
    return re.sub(r"[\s\W_]+", "", text, flags=re.UNICODE)


def _strip_intent_prefix(value: str) -> str:
    cleaned = value
    for prefix in ("帮我看看", "帮我", "看看", "分析", "研究", "关于"):
        if cleaned.startswith(prefix):
            cleaned = cleaned[len(prefix):]
    return cleaned


def _strip_event_connector_prefix(value: str) -> str:
    return EVENT_CONNECTOR_PREFIX_RE.sub("", value or "")


def _has_distinctive_signal(value: str) -> bool:
    return bool(re.search(r"[a-z0-9]", value)) or len(value) >= 5


def _is_weak_standalone_term(value: str) -> bool:
    """Return True for broad event descriptors that should not anchor relevance alone."""
    if not value:
        return True
    if not any(marker in value for marker in WEAK_EVENT_MARKERS):
        return False
    if re.search(r"[a-z0-9]", value):
        return False
    return len(value) <= 8


def _looks_like_short_person_name(value: str) -> bool:
    return bool(re.fullmatch(r"[\u4e00-\u9fff]{2,4}", value or ""))


def _add_term(terms: set[str], value: str, *, allow_weak: bool = False) -> None:
    if len(value) < 3:
        return
    if not allow_weak and _is_weak_standalone_term(value):
        return
    terms.add(value)


def extract_topic_anchor(topic_query: str) -> str:
    """Extract the short user topic from an Argus engine brief if present."""
    raw = str(topic_query or "").strip()
    if not raw:
        return ""

    match = ARGUS_SEARCH_ANCHOR_RE.search(raw)
    if match:
        anchor = match.group(1).strip()
        if anchor:
            return anchor

    context_match = ARGUS_CONTEXT_JSON_RE.search(raw)
    if context_match:
        try:
            payload = json.loads(context_match.group(1))
            query = str(payload.get("query") or "").strip()
            if query:
                return query
        except (TypeError, ValueError, json.JSONDecodeError):
            pass

    return raw


def build_topic_terms(topic_query: str) -> List[str]:
    """Return conservative anchor terms for a user topic."""
    topic_query = extract_topic_anchor(topic_query)
    normalized_query = _normalize_text(topic_query)
    if not normalized_query:
        return []

    terms = {normalized_query}
    chunks = re.findall(r"[\u4e00-\u9fffA-Za-z0-9]+", str(topic_query or "").lower())
    normalized_chunks = [_strip_intent_prefix(_normalize_text(chunk)) for chunk in chunks]
    primary_anchor = next((chunk for chunk in normalized_chunks if len(chunk) >= 2), "")

    for index, chunk in enumerate(chunks):
        normalized = _normalize_text(chunk)
        normalized = _strip_intent_prefix(normalized)
        if (
            index == 0
            and _looks_like_short_person_name(normalized)
            and any(
                len(other) >= 5 and not _is_weak_standalone_term(other)
                for other in normalized_chunks[index + 1 :]
            )
        ):
            continue

        for segment in _event_phrase_segments(normalized):
            _add_term(terms, segment)
            without_digits = re.sub(r"\d{2,4}", "", segment).strip("年月日")
            if without_digits != segment:
                _add_term(terms, without_digits)

        if len(normalized) >= 3 and (
            index == 0
            or not primary_anchor
            or primary_anchor in normalized
            or _has_distinctive_signal(normalized)
        ):
            _add_term(terms, normalized, allow_weak=index == 0)

            without_digits = re.sub(r"\d{2,4}", "", normalized).strip("年月日")
            if without_digits != normalized:
                _add_term(terms, without_digits)

        if index > 0 and primary_anchor and _is_weak_standalone_term(normalized):
            continue

        if len(normalized) >= 3 and not primary_anchor:
            terms.add(normalized)

        if "大学" in normalized:
            prefix, suffix = normalized.split("大学", 1)
            if len(prefix) >= 2:
                terms.add(f"{prefix}大学")
            if len(suffix) >= 3:
                terms.add(suffix)

        for marker in ("书院", "学院", "学校", "公司", "集团", "医院"):
            if marker in normalized:
                before = normalized.split(marker, 1)[0]
                if len(before) >= 3:
                    terms.add(f"{before}{marker}")

        for prefix, model in re.findall(
            r"([\u4e00-\u9fff]{0,6})([a-z]{1,8}\d[a-z0-9-]*)",
            normalized,
        ):
            brand_prefix = _strip_intent_prefix(prefix)[-4:]
            if len(brand_prefix) >= 2:
                terms.add(f"{brand_prefix}{model}")
            if len(model) >= 3:
                terms.add(model)

    return sorted(terms, key=len, reverse=True)


def _event_phrase_segments(value: str) -> List[str]:
    segments: List[str] = []
    for part in EVENT_CONNECTOR_RE.split(value or ""):
        normalized = _strip_event_connector_prefix(_normalize_text(part))
        if not normalized:
            continue
        if _looks_like_short_person_name(normalized):
            continue
        if normalized and normalized not in segments:
            segments.append(normalized)
    return segments


def assess_topic_relevance(topic_query: str, text: str) -> Dict[str, str]:
    topic_anchor = extract_topic_anchor(topic_query)
    terms = build_topic_terms(topic_query)
    normalized_text = _normalize_text(text)
    subject_anchor = _subject_anchor_from_topic(topic_anchor, terms)
    context_terms = [term for term in terms if _is_context_only_term(term)]
    event_terms = [term for term in terms if not _is_context_only_term(term)]
    has_subject = bool(subject_anchor and subject_anchor in normalized_text)
    has_context = any(term and term in normalized_text for term in context_terms)
    has_origin_anchor = has_subject or has_context
    has_event_term = any(
        term and term != subject_anchor and term in normalized_text
        for term in event_terms
        if not _is_short_event_phrase_requiring_origin(term, subject_anchor, context_terms)
    )
    has_evidence_context = any(
        marker in normalized_text for marker in EVIDENCE_CONTEXT_MARKERS
    )

    for term in terms:
        if term and term in normalized_text:
            if (
                _is_short_event_phrase_requiring_origin(term, subject_anchor, context_terms)
                and not has_origin_anchor
            ):
                continue
            if _is_context_only_term(term) and not (
                has_subject or has_event_term or has_evidence_context
            ):
                continue
            return {
                "relevance_status": "relevant",
                "relevance_reason": f"matched topic term: {term}",
            }
    return {
        "relevance_status": "irrelevant",
        "relevance_reason": "no anchor topic term found",
    }


def is_relevant_to_topic(topic_query: str, text: str) -> bool:
    return assess_topic_relevance(topic_query, text)["relevance_status"] == "relevant"


def _subject_anchor_from_terms(terms: List[str]) -> str:
    for term in sorted(terms, key=len):
        if _looks_like_short_person_name(term):
            return term
    return ""


def _subject_anchor_from_topic(topic_query: str, terms: List[str]) -> str:
    chunks = [
        _strip_intent_prefix(_normalize_text(chunk))
        for chunk in re.findall(r"[\u4e00-\u9fffA-Za-z0-9]+", str(topic_query or "").lower())
    ]
    for chunk in chunks:
        if _looks_like_short_person_name(chunk):
            return chunk
    return _subject_anchor_from_terms(terms)


def _is_context_only_term(term: str) -> bool:
    normalized = _normalize_text(term)
    if not normalized:
        return True
    if re.search(r"[a-z0-9]", normalized):
        return False
    if any(marker in normalized for marker in EVIDENCE_CONTEXT_MARKERS):
        return False
    return any(marker in normalized for marker in CONTEXT_ONLY_MARKERS)


def _is_short_event_phrase_requiring_origin(
    term: str,
    subject_anchor: str,
    context_terms: List[str],
) -> bool:
    normalized = _normalize_text(term)
    if not normalized or normalized == subject_anchor:
        return False
    if any(context and context in normalized for context in context_terms):
        return False
    if subject_anchor and subject_anchor in normalized:
        return False
    return len(normalized) <= 8 and any(
        marker in normalized for marker in EVIDENCE_CONTEXT_MARKERS
    )


def assess_evidence_item_relevance(
    topic_query: str,
    item: Mapping[str, Any],
) -> Dict[str, str]:
    text = " ".join(str(item.get(key) or "") for key in ("title", "content", "url"))
    return assess_topic_relevance(topic_query, text)


def filter_relevant_items(
    topic_query: str,
    items: Iterable[Mapping[str, Any]],
) -> List[Dict[str, Any]]:
    relevant: List[Dict[str, Any]] = []
    for item in items or []:
        relevance = assess_evidence_item_relevance(topic_query, item)
        if relevance["relevance_status"] != "relevant":
            continue
        enriched = dict(item)
        enriched.update(relevance)
        relevant.append(enriched)
    return relevant


def rewrite_query_if_drifted(
    generated_query: str,
    original_query: str,
    paragraph_title: str = "",
) -> tuple[str, bool]:
    original_query = extract_topic_anchor(original_query)
    generated_query = str(generated_query or "").strip()
    if not original_query:
        return generated_query, False

    if is_relevant_to_topic(original_query, generated_query):
        return generated_query, False

    anchored_query = " ".join(
        part for part in (original_query, str(paragraph_title or "").strip()) if part
    )
    return anchored_query, anchored_query != generated_query
