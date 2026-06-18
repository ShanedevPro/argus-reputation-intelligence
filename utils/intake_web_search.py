from typing import Any
from urllib.parse import urlparse

from config import settings


class IntakeWebSearchConfigError(RuntimeError):
    """Raised when no configured search provider can be created."""


class IntakeWebSearchRuntimeError(RuntimeError):
    """Raised when the configured search provider fails at request time."""


def load_agent_from_config():
    from MediaEngine.tools.search import load_agent_from_config as load_agent

    return load_agent()


def clamp_max_results(value: Any, default: int, hard_max: int) -> int:
    try:
        limit = default if value is None else int(value)
    except (TypeError, ValueError):
        limit = default

    return max(1, min(limit, hard_max))


def run_intake_web_search(query: str, max_results: int | None = None) -> dict[str, Any]:
    clean_query = str(query or "").strip()
    if not clean_query:
        raise ValueError("Search query cannot be empty.")

    limit = clamp_max_results(
        max_results,
        default=settings.INTAKE_WEB_SEARCH_DEFAULT_RESULTS,
        hard_max=settings.INTAKE_WEB_SEARCH_MAX_RESULTS,
    )

    try:
        client = load_agent_from_config()
    except Exception as exc:
        raise IntakeWebSearchConfigError(
            "Search provider is not configured."
        ) from exc

    try:
        response = client.web_search_only(clean_query, max_results=limit)
    except Exception as exc:
        raise IntakeWebSearchRuntimeError(
            "Search provider request failed."
        ) from exc

    return {
        "success": True,
        "query": clean_query,
        "provider": settings.SEARCH_TOOL_TYPE,
        "results": [_normalize_webpage(item) for item in getattr(response, "webpages", [])],
        "answer": getattr(response, "answer", None),
    }


def _normalize_webpage(item: Any) -> dict[str, Any]:
    url = _get_value(item, "url")
    return {
        "title": _get_value(item, "name") or _get_value(item, "title") or url,
        "url": url,
        "snippet": _get_value(item, "snippet") or _get_value(item, "summary") or "",
        "published_at": _get_value(item, "date_last_crawled")
        or _get_value(item, "published_at"),
        "source": _get_value(item, "display_url") or _source_from_url(url),
    }


def _get_value(item: Any, key: str) -> Any:
    if isinstance(item, dict):
        return item.get(key)
    return getattr(item, key, None)


def _source_from_url(url: str | None) -> str | None:
    if not url:
        return None
    parsed = urlparse(url)
    return parsed.netloc or None
