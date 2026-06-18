"""Shared query-parameter parsing for embedded Streamlit engine views."""

from dataclasses import dataclass
from typing import Any, Mapping


TRUE_VALUES = {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class QueryContext:
    query: str
    auto_search: bool
    preview_only: bool

    @property
    def should_start_research(self) -> bool:
        return bool(self.query.strip()) and self.auto_search and not self.preview_only


def _first_value(value: Any) -> str:
    if isinstance(value, (list, tuple)):
        if not value:
            return ""
        value = value[0]
    if value is None:
        return ""
    return str(value)


def _as_bool(value: Any) -> bool:
    return _first_value(value).strip().lower() in TRUE_VALUES


def parse_query_context(query_params: Mapping[str, Any]) -> QueryContext:
    return QueryContext(
        query=_first_value(query_params.get("query", "")).strip(),
        auto_search=_as_bool(query_params.get("auto_search", "false")),
        preview_only=_as_bool(query_params.get("preview_only", "false")),
    )


def get_streamlit_query_context(st_module: Any) -> QueryContext:
    try:
        query_params = st_module.query_params
    except AttributeError:
        query_params = st_module.experimental_get_query_params()
    return parse_query_context(query_params)
