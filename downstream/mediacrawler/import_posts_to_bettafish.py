#!/usr/bin/env python3
"""Import normalized MediaCrawler post/video/content records into BettaFish."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_ENV_FILES = (
    ROOT / ".env",
    ROOT / "upstream/betta-fish/.env",
    ROOT / "downstream/docker/runtime/config/app.env",
    ROOT / "downstream/docker/host.env",
    ROOT / "downstream/docker/local.env",
)


def load_env_value(key: str) -> str:
    value = os.getenv(key)
    if value:
        return value
    for env_file in DEFAULT_ENV_FILES:
        if not env_file.exists():
            continue
        for line in env_file.read_text(encoding="utf-8", errors="ignore").splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#") or "=" not in stripped:
                continue
            name, raw_value = stripped.split("=", 1)
            if name.strip() == key:
                return raw_value.strip().strip('"').strip("'")
    return ""


def build_dsn() -> str:
    if os.getenv("DATABASE_URL"):
        return os.getenv("DATABASE_URL", "")
    host = load_env_value("DB_HOST") or "127.0.0.1"
    port = load_env_value("DB_PORT") or "5432"
    user = load_env_value("DB_USER")
    password = load_env_value("DB_PASSWORD")
    db_name = load_env_value("DB_NAME")
    return f"postgresql://{user}:{password}@{host}:{port}/{db_name}"


def now_ms() -> int:
    return int(datetime.now(timezone.utc).timestamp() * 1000)


def as_int(value: Any, default: int = 0) -> int:
    try:
        if value is None or value == "":
            return default
        return int(float(value))
    except (TypeError, ValueError):
        return default


def as_text(value: Any) -> str:
    return "" if value is None else str(value)


def _raw(record: dict[str, Any]) -> dict[str, Any]:
    raw = record.get("raw")
    return raw if isinstance(raw, dict) else {}


def prepare_weibo_note(record: dict[str, Any]) -> dict[str, Any]:
    raw = _raw(record)
    engagement = record.get("engagement") or {}
    ts = now_ms()
    return {
        "user_id": as_text(raw.get("user_id")),
        "nickname": as_text(record.get("author") or raw.get("nickname")),
        "avatar": as_text(raw.get("avatar")),
        "gender": as_text(raw.get("gender")),
        "profile_url": as_text(raw.get("profile_url")),
        "ip_location": as_text(raw.get("ip_location")),
        "add_ts": ts,
        "last_modify_ts": ts,
        "note_id": as_int(record.get("content_id") or raw.get("note_id")),
        "content": as_text(record.get("content") or raw.get("content")).strip(),
        "create_time": as_int(raw.get("create_time")),
        "create_date_time": as_text(record.get("publish_time") or raw.get("create_date_time")),
        "liked_count": as_text(engagement.get("like_count", raw.get("liked_count", ""))),
        "comments_count": as_text(engagement.get("comment_count", raw.get("comments_count", ""))),
        "shared_count": as_text(engagement.get("share_count", raw.get("shared_count", ""))),
        "note_url": as_text(record.get("url") or raw.get("note_url")),
        "source_keyword": as_text(record.get("source_keyword") or raw.get("source_keyword")),
    }


def prepare_bilibili_video(record: dict[str, Any]) -> dict[str, Any]:
    raw = _raw(record)
    engagement = record.get("engagement") or {}
    ts = now_ms()
    return {
        "video_id": as_int(record.get("content_id") or raw.get("video_id")),
        "video_url": as_text(record.get("url") or raw.get("video_url")),
        "user_id": as_int(raw.get("user_id")),
        "nickname": as_text(record.get("author") or raw.get("nickname")),
        "avatar": as_text(raw.get("avatar")),
        "liked_count": as_int(engagement.get("like_count", raw.get("liked_count"))),
        "add_ts": ts,
        "last_modify_ts": ts,
        "video_type": as_text(record.get("content_type") or raw.get("video_type") or "video"),
        "title": as_text(record.get("title") or raw.get("title")),
        "desc": as_text(record.get("content") or raw.get("desc")),
        "create_time": as_int(record.get("publish_time") or raw.get("create_time")),
        "disliked_count": as_text(raw.get("disliked_count")),
        "video_play_count": as_text(engagement.get("play_count", raw.get("video_play_count", ""))),
        "video_favorite_count": as_text(engagement.get("favorite_count", raw.get("video_favorite_count", ""))),
        "video_share_count": as_text(engagement.get("share_count", raw.get("video_share_count", ""))),
        "video_coin_count": as_text(engagement.get("coin_count", raw.get("video_coin_count", ""))),
        "video_danmaku": as_text(engagement.get("danmaku_count", raw.get("video_danmaku", ""))),
        "video_comment": as_text(engagement.get("comment_count", raw.get("video_comment", ""))),
        "video_cover_url": as_text(raw.get("video_cover_url")),
        "source_keyword": as_text(record.get("source_keyword") or raw.get("source_keyword")),
    }


def prepare_zhihu_content(record: dict[str, Any]) -> dict[str, Any]:
    raw = _raw(record)
    engagement = record.get("engagement") or {}
    ts = now_ms()
    return {
        "content_id": as_text(record.get("content_id") or raw.get("content_id")),
        "content_type": as_text(record.get("content_type") or raw.get("content_type") or "content"),
        "content_text": as_text(record.get("content") or raw.get("content_text")),
        "content_url": as_text(record.get("url") or raw.get("content_url")),
        "question_id": as_text(raw.get("question_id")),
        "title": as_text(record.get("title") or raw.get("title")),
        "desc": as_text(raw.get("desc")),
        "created_time": as_text(record.get("publish_time") or raw.get("created_time")),
        "updated_time": as_text(raw.get("updated_time")),
        "voteup_count": as_int(engagement.get("voteup_count", raw.get("voteup_count"))),
        "comment_count": as_int(engagement.get("comment_count", raw.get("comment_count"))),
        "source_keyword": as_text(record.get("source_keyword") or raw.get("source_keyword")),
        "user_id": as_text(raw.get("user_id")),
        "user_link": as_text(raw.get("user_link")),
        "user_nickname": as_text(record.get("author") or raw.get("user_nickname")),
        "user_avatar": as_text(raw.get("user_avatar")),
        "user_url_token": as_text(raw.get("user_url_token")),
        "add_ts": ts,
        "last_modify_ts": ts,
    }


def prepare_kuaishou_video(record: dict[str, Any]) -> dict[str, Any]:
    raw = _raw(record)
    engagement = record.get("engagement") or {}
    ts = now_ms()
    return {
        "user_id": as_text(raw.get("user_id")),
        "nickname": as_text(record.get("author") or raw.get("nickname")),
        "avatar": as_text(raw.get("avatar")),
        "add_ts": ts,
        "last_modify_ts": ts,
        "video_id": as_text(record.get("content_id") or raw.get("video_id")),
        "video_type": as_text(record.get("content_type") or raw.get("video_type") or "video"),
        "title": as_text(record.get("title") or raw.get("title")),
        "desc": as_text(record.get("content") or raw.get("desc")),
        "create_time": as_int(record.get("publish_time") or raw.get("create_time")),
        "liked_count": as_text(engagement.get("like_count", raw.get("liked_count", ""))),
        "viewd_count": as_text(engagement.get("view_count", raw.get("viewd_count", ""))),
        "video_url": as_text(record.get("url") or raw.get("video_url")),
        "video_cover_url": as_text(raw.get("video_cover_url")),
        "video_play_url": as_text(raw.get("video_play_url")),
        "source_keyword": as_text(record.get("source_keyword") or raw.get("source_keyword")),
    }


def load_records(paths: list[Path], relevant_only: bool = True) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for path in paths:
        payload = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(payload, dict):
            items = payload.get("items", [])
        elif isinstance(payload, list):
            items = payload
        else:
            raise ValueError(f"Expected JSON object/list in {path}")
        for item in items:
            if not isinstance(item, dict):
                continue
            if relevant_only and item.get("is_relevant") is False:
                continue
            records.append(item)
    return records


async def upsert_weibo_note(conn: Any, record: dict[str, Any]) -> str:
    values = prepare_weibo_note(record)
    if not values["note_id"] or not values["content"]:
        return "skipped_invalid"
    existing_id = await conn.fetchval("SELECT id FROM weibo_note WHERE note_id=$1 LIMIT 1", values["note_id"])
    if existing_id:
        await conn.execute(
            """
            UPDATE weibo_note SET user_id=$1, nickname=$2, avatar=$3, gender=$4,
                profile_url=$5, ip_location=$6, last_modify_ts=$7, content=$8,
                create_time=$9, create_date_time=$10, liked_count=$11,
                comments_count=$12, shared_count=$13, note_url=$14,
                source_keyword=$15
            WHERE id=$16
            """,
            values["user_id"], values["nickname"], values["avatar"], values["gender"],
            values["profile_url"], values["ip_location"], values["last_modify_ts"],
            values["content"], values["create_time"], values["create_date_time"],
            values["liked_count"], values["comments_count"], values["shared_count"],
            values["note_url"], values["source_keyword"], existing_id,
        )
        return "updated"
    await conn.execute(
        """
        INSERT INTO weibo_note
            (user_id, nickname, avatar, gender, profile_url, ip_location, add_ts,
             last_modify_ts, note_id, content, create_time, create_date_time,
             liked_count, comments_count, shared_count, note_url, source_keyword)
        VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16,$17)
        """,
        values["user_id"], values["nickname"], values["avatar"], values["gender"],
        values["profile_url"], values["ip_location"], values["add_ts"], values["last_modify_ts"],
        values["note_id"], values["content"], values["create_time"], values["create_date_time"],
        values["liked_count"], values["comments_count"], values["shared_count"],
        values["note_url"], values["source_keyword"],
    )
    return "inserted"


async def upsert_bilibili_video(conn: Any, record: dict[str, Any]) -> str:
    values = prepare_bilibili_video(record)
    if not values["video_id"] or not values["title"]:
        return "skipped_invalid"
    existing_id = await conn.fetchval("SELECT id FROM bilibili_video WHERE video_id=$1 LIMIT 1", values["video_id"])
    if existing_id:
        await conn.execute(
            """
            UPDATE bilibili_video SET video_url=$1, user_id=$2, nickname=$3,
                avatar=$4, liked_count=$5, last_modify_ts=$6, video_type=$7,
                title=$8, "desc"=$9, create_time=$10, disliked_count=$11,
                video_play_count=$12, video_favorite_count=$13,
                video_share_count=$14, video_coin_count=$15, video_danmaku=$16,
                video_comment=$17, video_cover_url=$18, source_keyword=$19
            WHERE id=$20
            """,
            values["video_url"], values["user_id"], values["nickname"], values["avatar"],
            values["liked_count"], values["last_modify_ts"], values["video_type"],
            values["title"], values["desc"], values["create_time"], values["disliked_count"],
            values["video_play_count"], values["video_favorite_count"],
            values["video_share_count"], values["video_coin_count"], values["video_danmaku"],
            values["video_comment"], values["video_cover_url"], values["source_keyword"],
            existing_id,
        )
        return "updated"
    await conn.execute(
        """
        INSERT INTO bilibili_video
            (video_id, video_url, user_id, nickname, avatar, liked_count, add_ts,
             last_modify_ts, video_type, title, "desc", create_time, disliked_count,
             video_play_count, video_favorite_count, video_share_count, video_coin_count,
             video_danmaku, video_comment, video_cover_url, source_keyword)
        VALUES
            ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16,$17,$18,$19,$20,$21)
        """,
        values["video_id"], values["video_url"], values["user_id"], values["nickname"],
        values["avatar"], values["liked_count"], values["add_ts"], values["last_modify_ts"],
        values["video_type"], values["title"], values["desc"], values["create_time"],
        values["disliked_count"], values["video_play_count"], values["video_favorite_count"],
        values["video_share_count"], values["video_coin_count"], values["video_danmaku"],
        values["video_comment"], values["video_cover_url"], values["source_keyword"],
    )
    return "inserted"


async def upsert_zhihu_content(conn: Any, record: dict[str, Any]) -> str:
    values = prepare_zhihu_content(record)
    if not values["content_id"] or not values["content_text"]:
        return "skipped_invalid"
    existing_id = await conn.fetchval("SELECT id FROM zhihu_content WHERE content_id=$1 LIMIT 1", values["content_id"])
    if existing_id:
        await conn.execute(
            """
            UPDATE zhihu_content SET content_type=$1, content_text=$2, content_url=$3,
                question_id=$4, title=$5, "desc"=$6, created_time=$7,
                updated_time=$8, voteup_count=$9, comment_count=$10,
                source_keyword=$11, user_id=$12, user_link=$13, user_nickname=$14,
                user_avatar=$15, user_url_token=$16, last_modify_ts=$17
            WHERE id=$18
            """,
            values["content_type"], values["content_text"], values["content_url"],
            values["question_id"], values["title"], values["desc"], values["created_time"],
            values["updated_time"], values["voteup_count"], values["comment_count"],
            values["source_keyword"], values["user_id"], values["user_link"],
            values["user_nickname"], values["user_avatar"], values["user_url_token"],
            values["last_modify_ts"], existing_id,
        )
        return "updated"
    await conn.execute(
        """
        INSERT INTO zhihu_content
            (content_id, content_type, content_text, content_url, question_id, title,
             "desc", created_time, updated_time, voteup_count, comment_count,
             source_keyword, user_id, user_link, user_nickname, user_avatar,
             user_url_token, add_ts, last_modify_ts)
        VALUES
            ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16,$17,$18,$19)
        """,
        values["content_id"], values["content_type"], values["content_text"],
        values["content_url"], values["question_id"], values["title"], values["desc"],
        values["created_time"], values["updated_time"], values["voteup_count"],
        values["comment_count"], values["source_keyword"], values["user_id"],
        values["user_link"], values["user_nickname"], values["user_avatar"],
        values["user_url_token"], values["add_ts"], values["last_modify_ts"],
    )
    return "inserted"


async def upsert_kuaishou_video(conn: Any, record: dict[str, Any]) -> str:
    values = prepare_kuaishou_video(record)
    if not values["video_id"] or not values["title"]:
        return "skipped_invalid"
    existing_id = await conn.fetchval("SELECT id FROM kuaishou_video WHERE video_id=$1 LIMIT 1", values["video_id"])
    if existing_id:
        await conn.execute(
            """
            UPDATE kuaishou_video SET user_id=$1, nickname=$2, avatar=$3,
                last_modify_ts=$4, video_type=$5, title=$6, "desc"=$7,
                create_time=$8, liked_count=$9, viewd_count=$10, video_url=$11,
                video_cover_url=$12, video_play_url=$13, source_keyword=$14
            WHERE id=$15
            """,
            values["user_id"], values["nickname"], values["avatar"], values["last_modify_ts"],
            values["video_type"], values["title"], values["desc"], values["create_time"],
            values["liked_count"], values["viewd_count"], values["video_url"],
            values["video_cover_url"], values["video_play_url"], values["source_keyword"],
            existing_id,
        )
        return "updated"
    await conn.execute(
        """
        INSERT INTO kuaishou_video
            (user_id, nickname, avatar, add_ts, last_modify_ts, video_id, video_type,
             title, "desc", create_time, liked_count, viewd_count, video_url,
             video_cover_url, video_play_url, source_keyword)
        VALUES
            ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16)
        """,
        values["user_id"], values["nickname"], values["avatar"], values["add_ts"],
        values["last_modify_ts"], values["video_id"], values["video_type"], values["title"],
        values["desc"], values["create_time"], values["liked_count"], values["viewd_count"],
        values["video_url"], values["video_cover_url"], values["video_play_url"],
        values["source_keyword"],
    )
    return "inserted"


async def import_records(paths: list[Path], dsn: str, relevant_only: bool = True) -> dict[str, Any]:
    from downstream.mediacrawler.db_adapter import connect_postgres

    records = load_records(paths, relevant_only=relevant_only)
    conn = await connect_postgres(dsn)
    counts: dict[str, int] = {"seen": len(records), "inserted": 0, "updated": 0, "skipped_invalid": 0}
    try:
        for record in records:
            platform = as_text(record.get("platform"))
            if platform == "weibo":
                status = await upsert_weibo_note(conn, record)
            elif platform == "bilibili":
                status = await upsert_bilibili_video(conn, record)
            elif platform == "zhihu":
                status = await upsert_zhihu_content(conn, record)
            elif platform == "kuaishou":
                status = await upsert_kuaishou_video(conn, record)
            else:
                status = "skipped_invalid"
            counts[status] = counts.get(status, 0) + 1
        for table in ["weibo_note", "bilibili_video", "zhihu_content", "kuaishou_video"]:
            counts[table] = await conn.fetchval(f"SELECT count(*) FROM {table}")
    finally:
        await conn.close()
    return {"inputs": [str(path) for path in paths], "counts": counts}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dsn", default=build_dsn())
    parser.add_argument("--include-irrelevant", action="store_true")
    parser.add_argument("inputs", nargs="+", type=Path)
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    print(
        json.dumps(
            asyncio.run(import_records(args.inputs, args.dsn, relevant_only=not args.include_irrelevant)),
            ensure_ascii=False,
            indent=2,
        )
    )
