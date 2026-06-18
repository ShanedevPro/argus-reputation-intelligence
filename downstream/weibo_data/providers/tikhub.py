"""TikHub-backed Weibo data prep provider."""

from __future__ import annotations

import html
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from typing import Any, Callable, Mapping, Sequence

from .base import WeiboCollectionBundle, WeiboDataCaps
from utils.topic_relevance import is_relevant_to_topic


class TikHubProviderSetupError(RuntimeError):
    """Raised when TikHub provider dependencies or credentials are missing."""


@dataclass(frozen=True)
class TikHubWeiboProvider:
    base_url: str = ""
    api_key: str = field(default="", repr=False)
    timeout: int = 10
    pages_per_keyword: int = 3
    search_type: str = "1"
    client: Any | None = None
    client_factory: Callable[..., Any] | None = None
    name: str = "tikhub"

    def collect(
        self,
        request: Mapping[str, Any],
        caps: WeiboDataCaps,
    ) -> WeiboCollectionBundle:
        client = self._build_client()
        if hasattr(client, "__enter__"):
            with client as active_client:
                return self._collect_with_client(active_client, request, caps)
        return self._collect_with_client(client, request, caps)

    def _build_client(self) -> Any:
        if self.client is not None:
            return self.client
        if self.client_factory is not None:
            return self.client_factory(**self._client_kwargs())
        if not self.api_key:
            raise TikHubProviderSetupError("TIKHUB_API_KEY is required for TikHub Weibo data prep")
        try:
            from tikhub import TikHub
        except ModuleNotFoundError as exc:
            raise TikHubProviderSetupError("tikhub SDK is not installed") from exc
        return TikHub(**self._client_kwargs())

    def _client_kwargs(self) -> dict[str, Any]:
        kwargs: dict[str, Any] = {
            "api_key": self.api_key,
            "timeout": self.timeout,
            "parse_response": False,
        }
        if self.base_url:
            kwargs["base_url"] = self.base_url
        return kwargs

    def _collect_with_client(
        self,
        client: Any,
        request: Mapping[str, Any],
        caps: WeiboDataCaps,
    ) -> WeiboCollectionBundle:
        from utils.weibo_data_prep import (
            build_weibo_collection_bundle,
            compile_weibo_data_task,
            rank_weibo_posts,
            select_weibo_posts_for_comment_expansion,
        )

        task = compile_weibo_data_task(
            request,
            caps,
            provider=self.name,
            pages_per_keyword=self.pages_per_keyword,
            search_type=self.search_type,
        )
        raw_posts: list[dict[str, Any]] = []
        raw_post_count = 0
        irrelevant_post_count = 0
        errors: list[dict[str, str]] = []
        search_calls: list[dict[str, Any]] = []
        keyword_post_counts: dict[str, int] = {}
        post_cap_truncated = False
        relevance_query = _relevance_query(task.keywords, request)
        time_range = _request_time_range(request)
        search_endpoint = _search_endpoint(client, request)
        out_of_window_post_count = 0

        for keyword in task.keywords:
            keyword_posts: list[dict[str, Any]] = []
            for page in range(1, int(task.search["pages_per_keyword"]) + 1):
                if len(keyword_posts) >= caps.max_posts_per_keyword:
                    post_cap_truncated = True
                    break
                params, call_record = _search_params(
                    keyword=keyword,
                    page=page,
                    search_type=_search_type(
                        task.search.get("search_type"),
                        search_endpoint,
                        time_range,
                    ),
                    time_scope=_search_time_scope(
                        task.search.get("time_scope"),
                        search_endpoint,
                        time_range,
                    ),
                    endpoint=search_endpoint,
                )
                search_calls.append(call_record)
                try:
                    raw = _fetch_search(client, search_endpoint, params)
                except Exception as exc:
                    if _is_recoverable_search_error(exc):
                        errors.append(
                            {
                                "stage": "search",
                                "keyword": keyword,
                                "page": str(page),
                                "message": str(exc),
                            }
                        )
                        continue
                    raise TikHubProviderSetupError(f"TikHub search failed: {exc}") from exc
                cards = _extract_search_cards(raw)
                raw_post_count += len(cards)
                remaining = max(0, caps.max_posts_per_keyword - len(keyword_posts))
                if len(cards) > remaining:
                    post_cap_truncated = True
                normalized_posts = [_normalize_search_card(card, keyword) for card in cards]
                relevant_posts = [
                    post
                    for post in normalized_posts
                    if _post_is_topic_relevant(post, relevance_query)
                ]
                irrelevant_post_count += len(normalized_posts) - len(relevant_posts)
                relevant_posts, filtered_count = _filter_posts_by_time_window(
                    relevant_posts,
                    time_range,
                )
                out_of_window_post_count += filtered_count
                keyword_posts.extend(relevant_posts[:remaining])
            keyword_post_counts[keyword] = len(keyword_posts)
            raw_posts.extend(keyword_posts)

        deduped_posts = _dedupe_posts(raw_posts)
        if not deduped_posts:
            return build_weibo_collection_bundle(
                self.name,
                request,
                caps,
                posts=[],
                comments=[],
                metadata={
                    "task": task.to_dict(),
                    "endpoints": {
                        "search": search_endpoint,
                        "comments": "weibo_web.fetch_post_comments",
                    },
                    "search_calls": search_calls,
                    "raw_post_count": raw_post_count,
                    "deduped_post_count": 0,
                    "irrelevant_post_count": irrelevant_post_count,
                    "out_of_window_post_count": out_of_window_post_count,
                    "time_window_filter": _time_window_filter_metadata(time_range),
                    "raw_comment_count": 0,
                    "keyword_post_counts": keyword_post_counts,
                    "post_cap_truncated": post_cap_truncated,
                    "errors": errors,
                },
                stop_reason="zero_results",
            )

        ranked_posts = rank_weibo_posts(deduped_posts, request, caps)
        selected_posts = select_weibo_posts_for_comment_expansion(ranked_posts, caps)
        comments: list[dict[str, Any]] = []
        comment_calls: list[dict[str, Any]] = []
        raw_comment_count = 0
        comment_collection_failed = False

        for post in selected_posts:
            post_id = _clean_text(post.get("source_post_id") or post.get("content_id") or post.get("note_id"))
            mid = _clean_text(post.get("mid") or post_id)
            if not post_id:
                continue
            post_comments: list[dict[str, Any]] = []
            max_id: str | None = None
            max_id_type = 0
            max_pages = _max_comment_pages(caps)

            for _page_index in range(max_pages):
                params = {
                    "post_id": post_id,
                    "mid": mid,
                    "max_id": max_id,
                    "max_id_type": max_id_type,
                }
                comment_calls.append(params)
                try:
                    raw = client.weibo_web.fetch_post_comments(**params)
                except Exception as exc:  # Preserve posts and comments already collected.
                    comment_collection_failed = True
                    errors.append(
                        {
                            "stage": "comments",
                            "post_id": post_id,
                            "message": str(exc),
                        }
                    )
                    break
                raw_items = _extract_comment_items(raw)
                raw_comment_count += len(raw_items)
                post_comments.extend(_normalize_comment(item, post_id) for item in raw_items)
                if len(post_comments) >= caps.max_comments_per_post:
                    break
                next_max_id, next_max_id_type = _extract_comment_cursor(raw)
                if not next_max_id:
                    break
                max_id = next_max_id
                max_id_type = next_max_id_type

            comments.extend(post_comments[: caps.max_comments_per_post])

        stop_reason = "comment_collection_failed" if comment_collection_failed else ""
        return build_weibo_collection_bundle(
            self.name,
            request,
            caps,
            posts=deduped_posts,
            comments=comments,
            metadata={
                "task": task.to_dict(),
                "endpoints": {
                    "search": search_endpoint,
                    "comments": "weibo_web.fetch_post_comments",
                },
                "search_calls": search_calls,
                "comment_calls": comment_calls,
                "raw_post_count": raw_post_count,
                "deduped_post_count": len(deduped_posts),
                "irrelevant_post_count": irrelevant_post_count,
                "out_of_window_post_count": out_of_window_post_count,
                "time_window_filter": _time_window_filter_metadata(time_range),
                "raw_comment_count": raw_comment_count,
                "keyword_post_counts": keyword_post_counts,
                "post_cap_truncated": post_cap_truncated,
                "errors": errors,
            },
            stop_reason=stop_reason,
        )


def _request_time_range(request: Mapping[str, Any]) -> tuple[int, int] | None:
    time_window = _clean_text(request.get("timeWindow"))
    if not time_window:
        return None

    explicit_range = _explicit_time_range_seconds(time_window)
    if explicit_range:
        return explicit_range

    month_range = re.search(
        r"(20\d{2})\s*年\s*(\d{1,2})\s*月?\s*(?:至|到|-|—|~)\s*(?:(20\d{2})\s*年\s*)?(\d{1,2})\s*月",
        time_window,
    )
    if month_range:
        start_year = int(month_range.group(1))
        start_month = int(month_range.group(2))
        end_year = int(month_range.group(3) or start_year)
        end_month = int(month_range.group(4))
        return _month_range_seconds(start_year, start_month, end_year, end_month)

    lowered = time_window.lower()
    if any(token in lowered for token in ("24小时", "today", "day", "昨天", "今日", "今天")):
        return _relative_range_seconds(days=2)
    if any(token in lowered for token in ("一周", "7天", "七天", "week")):
        return _relative_range_seconds(days=7)
    if any(token in lowered for token in ("一年", "year", "365天")):
        return _relative_range_seconds(days=365)
    if any(token in lowered for token in ("三个月", "90天", "month", "最近")):
        return _relative_range_seconds(days=90)

    return None


def _explicit_time_range_seconds(time_window: str) -> tuple[int, int] | None:
    day_range = _explicit_day_range_seconds(time_window)
    if day_range:
        return day_range

    month_range = re.search(
        r"(20\d{2})\s*年\s*(\d{1,2})\s*月?\s*(?:至|到|-|—|~)\s*(?:(20\d{2})\s*年\s*)?(\d{1,2})\s*月",
        time_window,
    )
    if month_range:
        start_year = int(month_range.group(1))
        start_month = int(month_range.group(2))
        end_year = int(month_range.group(3) or start_year)
        end_month = int(month_range.group(4))
        return _month_range_seconds(start_year, start_month, end_year, end_month)

    return None


def _explicit_day_range_seconds(time_window: str) -> tuple[int, int] | None:
    iso_dates = re.findall(r"20\d{2}-\d{1,2}-\d{1,2}", time_window)
    if len(iso_dates) >= 2:
        return _day_range_seconds(iso_dates[0], iso_dates[-1])

    chinese_dates = re.findall(
        r"(20\d{2})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日?",
        time_window,
    )
    if len(chinese_dates) >= 2:
        start = "-".join(chinese_dates[0])
        end = "-".join(chinese_dates[-1])
        return _day_range_seconds(start, end)

    first = re.search(
        r"(20\d{2})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日?",
        time_window,
    )
    if first:
        suffix = time_window[first.end():]
        second = re.search(
            r"(?:至|到|~|～|—|–|-)\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日?",
            suffix,
        )
        if second:
            start = "-".join(first.groups())
            end = f"{first.group(1)}-{second.group(1)}-{second.group(2)}"
            return _day_range_seconds(start, end)

    return None


def _day_range_seconds(start_value: str, end_value: str) -> tuple[int, int] | None:
    try:
        start = datetime.strptime(start_value, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        end = datetime.strptime(end_value, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    except ValueError:
        return None
    if start > end:
        start, end = end, start
    end_exclusive = end + timedelta(days=1)
    return int(start.timestamp()), int(end_exclusive.timestamp())


def _relative_range_seconds(days: int) -> tuple[int, int]:
    now = datetime.now(timezone.utc)
    start = now - timedelta(days=days)
    end = now + timedelta(days=1)
    return int(start.timestamp()), int(end.timestamp())


def _month_range_seconds(
    start_year: int,
    start_month: int,
    end_year: int,
    end_month: int,
) -> tuple[int, int] | None:
    try:
        start = datetime(start_year, start_month, 1, tzinfo=timezone.utc)
        if end_month == 12:
            end = datetime(end_year + 1, 1, 1, tzinfo=timezone.utc)
        else:
            end = datetime(end_year, end_month + 1, 1, tzinfo=timezone.utc)
    except ValueError:
        return None
    return int(start.timestamp()), int(end.timestamp())


def _filter_posts_by_time_window(
    posts: Sequence[Mapping[str, Any]],
    time_range: tuple[int, int] | None,
) -> tuple[list[dict[str, Any]], int]:
    if time_range is None:
        return [dict(post) for post in posts], 0

    start_ts, end_ts = time_range
    kept: list[dict[str, Any]] = []
    filtered_count = 0
    for post in posts:
        raw = post.get("raw") if isinstance(post.get("raw"), Mapping) else {}
        timestamp = _parse_time_seconds(
            post.get("publish_time")
            or post.get("create_date_time")
            or post.get("create_time")
            or raw.get("create_date_time")
            or raw.get("create_time")
        )
        if timestamp and start_ts <= timestamp < end_ts:
            kept.append(dict(post))
        else:
            filtered_count += 1
    return kept, filtered_count


def _time_window_filter_metadata(time_range: tuple[int, int] | None) -> dict[str, Any] | None:
    if time_range is None:
        return None
    start_ts, end_ts = time_range
    return {
        "start": datetime.fromtimestamp(start_ts, timezone.utc).strftime("%Y-%m-%d"),
        "end_exclusive": datetime.fromtimestamp(end_ts, timezone.utc).strftime("%Y-%m-%d"),
    }


def _extract_search_cards(raw: Any) -> list[dict[str, Any]]:
    if not isinstance(raw, Mapping):
        return []
    data = raw.get("data") if isinstance(raw.get("data"), Mapping) else {}
    nested_data = data.get("data") if isinstance(data.get("data"), Mapping) else {}
    roots = (
        nested_data.get("cards")
        or data.get("cards")
        or data.get("items")
        or raw.get("cards")
        or []
    )
    cards: list[dict[str, Any]] = []

    def walk(value: Any) -> None:
        if isinstance(value, Mapping):
            if _extract_mblog(value):
                cards.append(dict(value))
            for key in ("card_group", "cards", "items", "data"):
                children = value.get(key)
                if isinstance(children, list):
                    for child in children:
                        walk(child)
                elif isinstance(children, Mapping):
                    walk(children)
        elif isinstance(value, list):
            for item in value:
                walk(item)

    walk(roots)
    return cards


def _is_recoverable_search_error(exc: Exception) -> bool:
    message = str(exc).lower()
    if "401" in message or "403" in message or "quota" in message or "unauthorized" in message:
        return False
    return "400" in message or "bad request" in message


def _normalize_search_card(card: Mapping[str, Any], keyword: str) -> dict[str, Any]:
    mblog = _extract_mblog(card)
    user = mblog.get("user") if isinstance(mblog.get("user"), Mapping) else {}
    post_id = _clean_text(mblog.get("id") or mblog.get("mid"))
    mid = _clean_text(mblog.get("mid") or post_id)
    author_id = _clean_text(user.get("id") or user.get("idstr"))
    status_code = _clean_text(mblog.get("mblogid") or mblog.get("bid"))
    url = _clean_text(card.get("scheme"))
    if not url and author_id and status_code:
        url = f"https://weibo.com/{author_id}/{status_code}"

    return {
        "platform": "weibo",
        "content_id": post_id,
        "note_id": post_id,
        "source_post_id": post_id,
        "mid": mid,
        "title": "",
        "content": _clean_html_text(mblog.get("text") or mblog.get("text_raw")),
        "author": _clean_html_text(user.get("screen_name") or user.get("name")),
        "author_id": author_id,
        "url": url,
        "publish_time": _format_time(mblog.get("created_at")),
        "source_keyword": _clean_text(keyword),
        "engagement": {
            "like_count": _as_int(mblog.get("attitudes_count")),
            "comment_count": _as_int(mblog.get("comments_count")),
            "share_count": _as_int(mblog.get("reposts_count")),
            "repost_count": _as_int(mblog.get("reposts_count")),
        },
        "raw": {
            "user_id": author_id,
            "nickname": _clean_html_text(user.get("screen_name") or user.get("name")),
            "avatar": _clean_text(user.get("profile_image_url") or user.get("avatar_hd")),
            "profile_url": _clean_text(user.get("profile_url")),
            "note_id": post_id,
            "content": _clean_html_text(mblog.get("text") or mblog.get("text_raw")),
            "create_time": _parse_time_seconds(mblog.get("created_at")),
            "create_date_time": _format_time(mblog.get("created_at")),
            "liked_count": _as_int(mblog.get("attitudes_count")),
            "comments_count": _as_int(mblog.get("comments_count")),
            "shared_count": _as_int(mblog.get("reposts_count")),
            "note_url": url,
            "source_keyword": _clean_text(keyword),
        },
    }


def _extract_comment_items(raw: Any) -> list[dict[str, Any]]:
    if not isinstance(raw, Mapping):
        return []
    items = (((raw.get("data") or {}).get("data") or {}).get("data") or [])
    return [item for item in items if isinstance(item, Mapping)]


def _search_endpoint(client: Any, request: Mapping[str, Any] | None = None) -> str:
    weibo_web = getattr(client, "weibo_web", None)
    if weibo_web is not None and hasattr(weibo_web, "fetch_search"):
        time_window = _clean_text((request or {}).get("timeWindow"))
        explicit_range = _explicit_time_range_seconds(time_window) if time_window else None
        if explicit_range and _is_historical_range(explicit_range):
            return "weibo_web.fetch_search"

    weibo_app = getattr(client, "weibo_app", None)
    if weibo_app is not None and hasattr(weibo_app, "fetch_search_all"):
        return "weibo_app.fetch_search_all"
    return "weibo_web.fetch_search"


def _is_historical_range(time_range: tuple[int, int]) -> bool:
    _start_ts, end_ts = time_range
    historical_cutoff = datetime.now(timezone.utc) - timedelta(days=7)
    return datetime.fromtimestamp(end_ts, timezone.utc) < historical_cutoff


def _search_params(
    *,
    keyword: str,
    page: int,
    search_type: Any,
    time_scope: Any,
    endpoint: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    if endpoint == "weibo_app.fetch_search_all":
        params = {
            "query": keyword,
            "page": page,
            "search_type": _optional_int(search_type),
        }
        return params, {
            "endpoint": endpoint,
            "query": keyword,
            "page": page,
            "search_type": params["search_type"],
        }

    params = {
        "keyword": keyword,
        "page": page,
        "search_type": _clean_text(search_type),
        "time_scope": _none_if_auto(time_scope),
    }
    return params, {
        "endpoint": endpoint,
        "keyword": keyword,
        "page": page,
        "search_type": params["search_type"],
        "time_scope": params["time_scope"] or time_scope,
    }


def _search_time_scope(
    task_time_scope: Any,
    endpoint: str,
    time_range: tuple[int, int] | None,
) -> Any:
    if endpoint == "weibo_web.fetch_search" and time_range and _is_historical_range(time_range):
        return None
    return task_time_scope


def _search_type(
    task_search_type: Any,
    endpoint: str,
    time_range: tuple[int, int] | None,
) -> Any:
    if endpoint == "weibo_web.fetch_search" and time_range and _is_historical_range(time_range):
        return "1"
    return task_search_type


def _fetch_search(client: Any, endpoint: str, params: Mapping[str, Any]) -> Any:
    if endpoint == "weibo_app.fetch_search_all":
        return client.weibo_app.fetch_search_all(**params)
    return client.weibo_web.fetch_search(**params)


def _extract_mblog(card: Mapping[str, Any]) -> dict[str, Any]:
    for key in ("mblog", "status"):
        value = card.get(key)
        if isinstance(value, Mapping):
            return dict(value)
    if any(key in card for key in ("id", "mid", "text", "text_raw")):
        return dict(card)
    return {}


def _relevance_query(keywords: Sequence[str], request: Mapping[str, Any]) -> str:
    parts = [
        _clean_text(request.get("affectedSubject")),
        _clean_text(request.get("eventOrIssue")),
        *[_clean_text(keyword) for keyword in keywords],
    ]
    return " ".join(part for part in parts if part)


def _post_is_topic_relevant(post: Mapping[str, Any], topic_query: str) -> bool:
    haystack = " ".join(
        _clean_text(post.get(field))
        for field in ("title", "content", "author", "url")
    )
    return is_relevant_to_topic(topic_query, haystack)


def _extract_comment_cursor(raw: Any) -> tuple[str | None, int]:
    if not isinstance(raw, Mapping):
        return None, 0
    payload = ((raw.get("data") or {}).get("data") or {})
    max_id = _clean_text(payload.get("max_id"))
    if not max_id or max_id == "0":
        return None, 0
    return max_id, _as_int(payload.get("max_id_type"))


def _max_comment_pages(caps: WeiboDataCaps) -> int:
    hard_cap = max(
        int(caps.max_comments_per_post or 1),
        int(caps.max_comments_per_post_hard or caps.max_comments_per_post or 1),
    )
    return max(1, min(5, (hard_cap // 10) + 2))


def _normalize_comment(item: Mapping[str, Any], note_id: str) -> dict[str, Any]:
    user = item.get("user") if isinstance(item.get("user"), Mapping) else {}
    return {
        "comment_id": _clean_text(item.get("id") or item.get("idstr")),
        "note_id": _clean_text(note_id),
        "content": _clean_html_text(item.get("text") or item.get("text_raw")),
        "create_time": _parse_time_seconds(item.get("created_at")),
        "create_date_time": _format_time(item.get("created_at")),
        "comment_like_count": _as_int(item.get("like_count") or item.get("liked_count")),
        "sub_comment_count": _as_int(item.get("total_number") or item.get("comments_count")),
        "parent_comment_id": _clean_text(item.get("parent_comment_id")),
        "user_id": _clean_text(user.get("id") or user.get("idstr")),
        "nickname": _clean_html_text(user.get("screen_name") or user.get("name")),
        "avatar": _clean_text(user.get("profile_image_url") or user.get("avatar_hd")),
        "profile_url": _clean_text(user.get("profile_url")),
        "raw": dict(item),
    }


def _dedupe_posts(posts: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    deduped: list[dict[str, Any]] = []
    for post in posts:
        keys = [
            f"id:{_clean_text(post.get('content_id') or post.get('note_id'))}",
            f"url:{_clean_text(post.get('url'))}",
            f"text:{_near_text_key(post.get('content'))}",
        ]
        if any(key and key in seen for key in keys):
            continue
        normalized = dict(post)
        deduped.append(normalized)
        for key in keys:
            if key and not key.endswith(":"):
                seen.add(key)
    return deduped


def _none_if_auto(value: Any) -> str | None:
    text = _clean_text(value)
    if not text or text == "auto":
        return None
    return text


def _near_text_key(value: Any) -> str:
    return re.sub(r"\W+", "", _clean_html_text(value).lower())[:80]


def _clean_html_text(value: Any) -> str:
    text = html.unescape(_clean_text(value))
    text = re.sub(r"<[^>]+>", "", text)
    return " ".join(text.split())


def _clean_text(value: Any) -> str:
    if value is None:
        return ""
    return " ".join(str(value).strip().split())


def _optional_int(value: Any) -> int | None:
    text = _clean_text(value)
    if not text:
        return None
    try:
        return int(text)
    except ValueError:
        return None


def _as_int(value: Any) -> int:
    try:
        if value is None or value == "":
            return 0
        return int(float(str(value).strip()))
    except (TypeError, ValueError):
        return 0


def _format_time(value: Any) -> str:
    seconds = _parse_time_seconds(value)
    if not seconds:
        return _clean_text(value)
    return datetime.fromtimestamp(seconds, timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def _parse_time_seconds(value: Any) -> int:
    if value is None or value == "":
        return 0
    if isinstance(value, (int, float)) or str(value).isdigit():
        numeric = int(float(value))
        if numeric > 10_000_000_000:
            numeric //= 1000
        return numeric
    text = _clean_text(value)
    try:
        parsed = parsedate_to_datetime(text)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return int(parsed.timestamp())
    except (TypeError, ValueError):
        pass
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return int(parsed.timestamp())
    except ValueError:
        return 0
