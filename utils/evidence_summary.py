"""Tiny evidence sidecars for engine reports."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Tuple

from utils.topic_relevance import assess_evidence_item_relevance


EvidenceItem = Dict[str, Any]
DEFAULT_MAX_EVIDENCE_ITEMS = 200
DEFAULT_MAX_SNIPPET_CHARS = 2000


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _as_mapping(value: Any) -> Dict[str, Any]:
    if isinstance(value, Mapping):
        return dict(value)

    to_dict = getattr(value, "to_dict", None)
    if callable(to_dict):
        data = to_dict()
        if isinstance(data, Mapping):
            return dict(data)

    data: Dict[str, Any] = {}
    for key in (
        "query",
        "url",
        "title",
        "content",
        "score",
        "timestamp",
        "paragraph_title",
        "search_tool",
        "has_result",
    ):
        if hasattr(value, key):
            data[key] = getattr(value, key)
    return data


def _has_text(value: Any) -> bool:
    return bool(str(value or "").strip())


def _is_real_evidence_item(item: Mapping[str, Any]) -> bool:
    if item.get("has_result") is False:
        return False
    return any(_has_text(item.get(key)) for key in ("url", "title", "content"))


def _compact_evidence_item(
    item: Mapping[str, Any],
    paragraph_title: str,
    evidence_index: int,
    relevance: Optional[Mapping[str, Any]] = None,
) -> EvidenceItem:
    compact: EvidenceItem = {"evidence_id": f"E{evidence_index}"}
    if paragraph_title:
        compact["paragraph_title"] = paragraph_title
    if relevance:
        for key in ("relevance_status", "relevance_reason"):
            value = relevance.get(key)
            if value:
                compact[key] = value

    for key in ("title", "url", "content", "score", "query", "search_tool"):
        value = item.get(key)
        if value not in ("", None, [], {}):
            compact[key] = value

    content = compact.get("content")
    if isinstance(content, str) and len(content) > DEFAULT_MAX_SNIPPET_CHARS:
        compact["content"] = content[:DEFAULT_MAX_SNIPPET_CHARS]
    if compact.get("title"):
        compact["source_title"] = compact["title"]
    if compact.get("url"):
        compact["source_url"] = compact["url"]
    snippet = compact.get("content") or compact.get("title") or ""
    if isinstance(snippet, str):
        compact["snippet"] = snippet[:DEFAULT_MAX_SNIPPET_CHARS]

    return compact


def summarize_evidence_from_paragraphs(
    paragraphs: Iterable[Any],
    max_items: int = DEFAULT_MAX_EVIDENCE_ITEMS,
    topic_query: str = "",
) -> Tuple[str, int, List[EvidenceItem]]:
    """Summarize existing engine search history without any new generation pass."""
    source_count = 0
    evidence_items: List[EvidenceItem] = []

    for paragraph in paragraphs or []:
        paragraph_data = _as_mapping(paragraph)
        paragraph_title = str(paragraph_data.get("title") or "")
        research = paragraph_data.get("research") or getattr(paragraph, "research", None)
        research_data = _as_mapping(research)
        search_history = research_data.get("search_history", [])

        for search_entry in search_history or []:
            item = _as_mapping(search_entry)
            if not _is_real_evidence_item(item):
                continue
            relevance = None
            if topic_query:
                relevance = assess_evidence_item_relevance(topic_query, item)
                if relevance["relevance_status"] != "relevant":
                    continue

            source_count += 1
            if len(evidence_items) < max_items:
                evidence_items.append(
                    _compact_evidence_item(
                        item,
                        paragraph_title,
                        source_count,
                        relevance=relevance,
                    )
                )

    evidence_status = "ready" if source_count > 0 else "no_data"
    return evidence_status, source_count, evidence_items


def write_evidence_summary(
    report_path: str | Path,
    engine_name: str,
    query: str,
    evidence_status: str,
    source_count: int,
    evidence_items: List[Mapping[str, Any]],
) -> Path:
    report_path = Path(report_path)
    sidecar_path = report_path.with_suffix(".evidence.json")
    payload = {
        "engine_name": engine_name,
        "query": query,
        "report_file": str(report_path.resolve()),
        "evidence_status": evidence_status,
        "source_count": int(source_count or 0),
        "evidence_items": [dict(item) for item in (evidence_items or [])],
        "generated_at": _now_iso(),
    }

    sidecar_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return sidecar_path


def build_evidence_summary(
    report_path: str | Path,
    engine_name: str,
    query: str,
    paragraphs: Iterable[Any],
    topic_query: str = "",
) -> Path:
    evidence_status, source_count, evidence_items = summarize_evidence_from_paragraphs(
        paragraphs,
        topic_query=topic_query,
    )
    return write_evidence_summary(
        report_path=report_path,
        engine_name=engine_name,
        query=query,
        evidence_status=evidence_status,
        source_count=source_count,
        evidence_items=evidence_items,
    )


def load_evidence_summary(sidecar_path: str | Path) -> Dict[str, Any]:
    return json.loads(Path(sidecar_path).read_text(encoding="utf-8"))
