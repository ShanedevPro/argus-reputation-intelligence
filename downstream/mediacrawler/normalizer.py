"""Normalize MediaCrawler JSON records for BettaFish import."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


PLATFORM_ALIASES = {
    "bili": "bilibili",
    "bilibli": "bilibili",
    "ks": "kuaishou",
    "wb": "weibo",
}


def clean_text(value: Any) -> str:
    return "" if value is None else str(value).strip()


def normalize_platform(platform: str) -> str:
    raw = platform.strip().lower()
    return PLATFORM_ALIASES.get(raw, raw)


def as_items(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, dict):
        items = payload.get("items")
        if isinstance(items, list):
            return [item for item in items if isinstance(item, dict)]
        return [payload]
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    raise ValueError("Expected JSON object or list")


def load_json_items(path: Path) -> list[dict[str, Any]]:
    return as_items(json.loads(path.read_text(encoding="utf-8")))


def normalize_mediacrawler_item(
    platform: str,
    item: dict[str, Any],
    *,
    source_file: str = "",
) -> dict[str, Any]:
    platform = normalize_platform(platform)
    if platform == "weibo":
        title = clean_text(item.get("title"))
        content = clean_text(item.get("content"))
        author = clean_text(item.get("nickname"))
        url = clean_text(item.get("note_url"))
        content_id = clean_text(item.get("note_id"))
        publish_time = clean_text(item.get("create_date_time") or item.get("create_time"))
        content_type = "note"
        engagement = {
            "like_count": item.get("liked_count", ""),
            "comment_count": item.get("comments_count", ""),
            "share_count": item.get("shared_count", ""),
        }
    elif platform == "bilibili":
        title = clean_text(item.get("title"))
        content = clean_text(item.get("desc"))
        author = clean_text(item.get("nickname"))
        url = clean_text(item.get("video_url"))
        content_id = clean_text(item.get("video_id"))
        publish_time = clean_text(item.get("create_time"))
        content_type = clean_text(item.get("video_type")) or "video"
        engagement = {
            "like_count": item.get("liked_count", 0),
            "play_count": item.get("video_play_count", ""),
            "comment_count": item.get("video_comment", ""),
            "favorite_count": item.get("video_favorite_count", ""),
            "share_count": item.get("video_share_count", ""),
            "coin_count": item.get("video_coin_count", ""),
            "danmaku_count": item.get("video_danmaku", ""),
        }
    elif platform == "zhihu":
        title = clean_text(item.get("title"))
        content = clean_text(item.get("content_text") or item.get("content") or item.get("desc"))
        author = clean_text(item.get("user_nickname") or item.get("nickname"))
        url = clean_text(item.get("content_url") or item.get("url"))
        content_id = clean_text(item.get("content_id"))
        publish_time = clean_text(item.get("created_time"))
        content_type = clean_text(item.get("content_type")) or "content"
        engagement = {
            "voteup_count": item.get("voteup_count", 0),
            "comment_count": item.get("comment_count", 0),
        }
    elif platform == "kuaishou":
        title = clean_text(item.get("title"))
        content = clean_text(item.get("desc"))
        author = clean_text(item.get("nickname"))
        url = clean_text(item.get("video_url"))
        content_id = clean_text(item.get("video_id"))
        publish_time = clean_text(item.get("create_time"))
        content_type = clean_text(item.get("video_type")) or "video"
        engagement = {
            "like_count": item.get("liked_count", ""),
            "view_count": item.get("viewd_count", ""),
        }
    else:
        raise ValueError(f"Unsupported MediaCrawler platform: {platform}")

    return {
        "platform": platform,
        "content_id": content_id,
        "content_type": content_type,
        "title": title,
        "content": content,
        "author": author,
        "url": url,
        "publish_time": publish_time,
        "engagement": engagement,
        "source_keyword": clean_text(item.get("source_keyword")),
        "source_file": source_file,
        "is_relevant": True,
        "raw": item,
    }


def normalize_file(platform: str, path: Path) -> list[dict[str, Any]]:
    return [
        normalize_mediacrawler_item(platform, item, source_file=str(path))
        for item in load_json_items(path)
    ]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--platform", required=True, help="MediaCrawler platform, e.g. wb, bili, zhihu, ks.")
    parser.add_argument("--output", type=Path, required=True, help="Normalized JSON output path.")
    parser.add_argument("inputs", nargs="+", type=Path, help="Raw MediaCrawler JSON files.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    records: list[dict[str, Any]] = []
    for path in args.inputs:
        records.extend(normalize_file(args.platform, path))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps({"items": records}, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"output": str(args.output), "items": len(records)}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
