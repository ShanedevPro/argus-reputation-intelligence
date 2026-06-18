#!/usr/bin/env python3
"""Import MediaCrawler comment JSON into BettaFish comment tables."""

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


def load_comment_items(paths: list[Path]) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for path in paths:
        payload = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(payload, dict):
            payload = [payload]
        if not isinstance(payload, list):
            raise ValueError(f"Expected JSON object/list in {path}")
        items.extend(item for item in payload if isinstance(item, dict))
    return items


def prepare_weibo_comment(item: dict[str, Any]) -> dict[str, Any]:
    ts = now_ms()
    return {
        "user_id": as_text(item.get("user_id")),
        "nickname": as_text(item.get("nickname")),
        "avatar": as_text(item.get("avatar")),
        "gender": as_text(item.get("gender")),
        "profile_url": as_text(item.get("profile_url")),
        "ip_location": as_text(item.get("ip_location")),
        "add_ts": ts,
        "last_modify_ts": ts,
        "comment_id": as_int(item.get("comment_id")),
        "note_id": as_int(item.get("note_id")),
        "content": as_text(item.get("content")).strip(),
        "create_time": as_int(item.get("create_time")),
        "create_date_time": as_text(item.get("create_date_time")),
        "comment_like_count": as_text(item.get("comment_like_count")),
        "sub_comment_count": as_text(item.get("sub_comment_count")),
        "parent_comment_id": as_text(item.get("parent_comment_id")),
    }


def prepare_bilibili_comment(item: dict[str, Any]) -> dict[str, Any]:
    ts = now_ms()
    return {
        "user_id": as_text(item.get("user_id")),
        "nickname": as_text(item.get("nickname")),
        "sex": as_text(item.get("sex")),
        "sign": as_text(item.get("sign")),
        "avatar": as_text(item.get("avatar")),
        "add_ts": ts,
        "last_modify_ts": ts,
        "comment_id": as_int(item.get("comment_id")),
        "video_id": as_int(item.get("video_id")),
        "content": as_text(item.get("content")).strip(),
        "create_time": as_int(item.get("create_time")),
        "sub_comment_count": as_text(item.get("sub_comment_count")),
        "parent_comment_id": as_text(item.get("parent_comment_id")),
        "like_count": as_text(item.get("like_count")),
    }


async def insert_weibo_comment(conn: Any, values: dict[str, Any]) -> str:
    if not values["comment_id"] or not values["note_id"] or not values["content"]:
        return "skipped_invalid"
    exists = await conn.fetchval(
        "SELECT id FROM weibo_note_comment WHERE comment_id=$1 LIMIT 1",
        values["comment_id"],
    )
    if exists:
        return "skipped_duplicate"
    await conn.execute(
        """
        INSERT INTO weibo_note_comment
            (user_id, nickname, avatar, gender, profile_url, ip_location, add_ts,
             last_modify_ts, comment_id, note_id, content, create_time,
             create_date_time, comment_like_count, sub_comment_count,
             parent_comment_id)
        VALUES
            ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16)
        """,
        values["user_id"], values["nickname"], values["avatar"], values["gender"],
        values["profile_url"], values["ip_location"], values["add_ts"], values["last_modify_ts"],
        values["comment_id"], values["note_id"], values["content"], values["create_time"],
        values["create_date_time"], values["comment_like_count"], values["sub_comment_count"],
        values["parent_comment_id"],
    )
    return "inserted"


async def insert_bilibili_comment(conn: Any, values: dict[str, Any]) -> str:
    if not values["comment_id"] or not values["video_id"] or not values["content"]:
        return "skipped_invalid"
    exists = await conn.fetchval(
        "SELECT id FROM bilibili_video_comment WHERE comment_id=$1 LIMIT 1",
        values["comment_id"],
    )
    if exists:
        return "skipped_duplicate"
    await conn.execute(
        """
        INSERT INTO bilibili_video_comment
            (user_id, nickname, sex, sign, avatar, add_ts, last_modify_ts,
             comment_id, video_id, content, create_time, sub_comment_count,
             parent_comment_id, like_count)
        VALUES
            ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14)
        """,
        values["user_id"], values["nickname"], values["sex"], values["sign"],
        values["avatar"], values["add_ts"], values["last_modify_ts"], values["comment_id"],
        values["video_id"], values["content"], values["create_time"], values["sub_comment_count"],
        values["parent_comment_id"], values["like_count"],
    )
    return "inserted"


async def import_comments(platform: str, paths: list[Path], dsn: str) -> dict[str, Any]:
    from downstream.mediacrawler.db_adapter import connect_postgres

    items = load_comment_items(paths)
    conn = await connect_postgres(dsn)
    counts = {"seen": len(items), "inserted": 0, "skipped_duplicate": 0, "skipped_invalid": 0}
    try:
        for item in items:
            if platform == "weibo":
                result = await insert_weibo_comment(conn, prepare_weibo_comment(item))
            elif platform == "bilibili":
                result = await insert_bilibili_comment(conn, prepare_bilibili_comment(item))
            else:
                raise ValueError(f"Unsupported platform: {platform}")
            counts[result] += 1
        table = "weibo_note_comment" if platform == "weibo" else "bilibili_video_comment"
        counts["table_count"] = await conn.fetchval(f"SELECT count(*) FROM {table}")
    finally:
        await conn.close()
    return {"platform": platform, "inputs": [str(path) for path in paths], "counts": counts}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--platform", choices=["weibo", "bilibili"], required=True)
    parser.add_argument("--dsn", default=build_dsn())
    parser.add_argument("inputs", nargs="+", type=Path)
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    print(json.dumps(asyncio.run(import_comments(args.platform, args.inputs, args.dsn)), ensure_ascii=False, indent=2))
