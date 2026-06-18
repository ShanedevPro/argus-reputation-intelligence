"""Shared helpers for normalizing search-node LLM output."""

from __future__ import annotations

from typing import Any, Dict, Mapping


OPTIONAL_SEARCH_OUTPUT_FIELDS = (
    "search_tool",
    "start_date",
    "end_date",
    "time_period",
    "platform",
    "limit",
    "enable_sentiment",
)


def build_search_node_output(result: Mapping[str, Any]) -> Dict[str, Any]:
    """Preserve the fields downstream agents need to choose tools correctly."""
    output: Dict[str, Any] = {
        "search_query": str(result.get("search_query") or ""),
        "reasoning": str(result.get("reasoning") or ""),
    }
    for field in OPTIONAL_SEARCH_OUTPUT_FIELDS:
        if field in result and result[field] not in (None, ""):
            output[field] = result[field]
    return output


def is_search_node_mapping(result: Any) -> bool:
    """Return True only for structured search-node output objects."""
    return isinstance(result, Mapping)
