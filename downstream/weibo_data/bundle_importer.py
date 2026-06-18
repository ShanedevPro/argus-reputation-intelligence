"""Import canonical Weibo bundles into the existing BettaFish tables."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any, Iterable, Mapping

from downstream.mediacrawler.db_adapter import connect_postgres
from downstream.mediacrawler.import_comments_to_bettafish import (
    insert_weibo_comment,
    prepare_weibo_comment,
)
from downstream.mediacrawler.import_posts_to_bettafish import (
    upsert_weibo_note,
)


def _ensure_path_list(paths: Iterable[Path]) -> list[Path]:
    return [Path(path) for path in paths]


def _load_payload(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(payload, dict):
        if "posts" in payload or "comments" in payload:
            return payload
        if _is_comment_item(payload):
            return {
                "provider": str(payload.get("provider") or "mediacrawler"),
                "posts": [],
                "comments": [_normalize_comment_item(payload)],
                "stop_reason": str(payload.get("stop_reason") or ""),
                "metadata": dict(payload.get("metadata") or {}),
            }
        if _is_post_item(payload):
            return {
                "provider": str(payload.get("provider") or "mediacrawler"),
                "posts": [_normalize_post_item(payload)],
                "comments": [],
                "stop_reason": str(payload.get("stop_reason") or ""),
                "metadata": dict(payload.get("metadata") or {}),
            }
        items = payload.get("items")
        if isinstance(items, list):
            posts, comments = _split_items(items)
            return {
                "provider": str(payload.get("provider") or "mediacrawler"),
                "posts": posts,
                "comments": comments,
                "stop_reason": str(payload.get("stop_reason") or ""),
                "metadata": dict(payload.get("metadata") or {}),
            }
        return payload
    if isinstance(payload, list):
        posts, comments = _split_items(payload)
        return {
            "provider": "mediacrawler",
            "posts": posts,
            "comments": comments,
            "stop_reason": "",
            "metadata": {},
        }
    raise ValueError(f"Unsupported Weibo bundle format in {path}")


def _split_items(items: Iterable[Mapping[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    posts: list[dict[str, Any]] = []
    comments: list[dict[str, Any]] = []
    for item in items:
        if not isinstance(item, Mapping):
            continue
        if item.get("is_relevant") is False:
            continue
        normalized = dict(item)
        if _is_comment_item(normalized):
            comments.append(_normalize_comment_item(normalized))
        elif _is_post_item(normalized):
            posts.append(_normalize_post_item(normalized))
    return posts, comments


def _is_comment_item(item: Mapping[str, Any]) -> bool:
    return bool(item.get("comment_id") or item.get("parent_comment_id"))


def _is_post_item(item: Mapping[str, Any]) -> bool:
    return bool(item.get("content_id") or item.get("note_id") or item.get("title") or item.get("content"))


def _normalize_post_item(item: Mapping[str, Any]) -> dict[str, Any]:
    normalized = dict(item)
    if not normalized.get("content_id") and normalized.get("note_id"):
        normalized["content_id"] = normalized["note_id"]
    if not normalized.get("platform"):
        normalized["platform"] = "weibo"
    return normalized


def _normalize_comment_item(item: Mapping[str, Any]) -> dict[str, Any]:
    normalized = dict(item)
    if not normalized.get("note_id") and normalized.get("content_id"):
        normalized["note_id"] = normalized["content_id"]
    if not normalized.get("comment_like_count") and normalized.get("like_count") is not None:
        normalized["comment_like_count"] = normalized.get("like_count")
    return normalized


async def import_weibo_bundle(
    paths: Iterable[Path],
    dsn: str,
    *,
    relevant_only: bool = True,
) -> dict[str, Any]:
    path_list = _ensure_path_list(paths)
    conn = await connect_postgres(dsn)
    counts: dict[str, int] = {
        "seen_posts": 0,
        "seen_comments": 0,
        "inserted": 0,
        "updated": 0,
        "skipped_duplicate": 0,
        "skipped_invalid": 0,
        "post_inserted": 0,
        "post_updated": 0,
        "post_skipped_invalid": 0,
        "comment_inserted": 0,
        "comment_skipped_duplicate": 0,
        "comment_skipped_invalid": 0,
    }
    provider = ""

    try:
        for path in path_list:
            bundle = _load_payload(path)
            provider = provider or str(bundle.get("provider") or "mediacrawler")
            posts = list(bundle.get("posts") or [])
            comments = list(bundle.get("comments") or [])
            if relevant_only:
                posts = [item for item in posts if item.get("is_relevant") is not False]
                comments = [item for item in comments if item.get("is_relevant") is not False]

            counts["seen_posts"] += len(posts)
            counts["seen_comments"] += len(comments)

            for post in posts:
                status = await upsert_weibo_note(conn, _normalize_post_item(post))
                counts[status] = counts.get(status, 0) + 1
                counts[f"post_{status}"] = counts.get(f"post_{status}", 0) + 1

            for comment in comments:
                normalized_comment = _normalize_comment_item(comment)
                status = await insert_weibo_comment(
                    conn,
                    prepare_weibo_comment(normalized_comment),
                )
                counts[status] = counts.get(status, 0) + 1
                counts[f"comment_{status}"] = counts.get(f"comment_{status}", 0) + 1

        counts["weibo_note"] = int(await conn.fetchval("SELECT count(*) FROM weibo_note") or 0)
        counts["weibo_note_comment"] = int(
            await conn.fetchval("SELECT count(*) FROM weibo_note_comment") or 0
        )
    finally:
        await conn.close()

    return {
        "provider": provider or "mediacrawler",
        "inputs": [str(path) for path in path_list],
        "counts": counts,
    }


def import_weibo_bundle_sync(
    paths: Iterable[Path],
    dsn: str,
    *,
    relevant_only: bool = True,
) -> dict[str, Any]:
    return asyncio.run(import_weibo_bundle(paths, dsn, relevant_only=relevant_only))
