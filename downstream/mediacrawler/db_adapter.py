"""Small PostgreSQL adapter for MediaCrawler import scripts."""

from __future__ import annotations

import re
from typing import Any


def _normalize_postgres_dsn(dsn: str) -> str:
    cleaned = (dsn or "").strip()
    if cleaned.startswith("postgresql+asyncpg://"):
        return "postgresql://" + cleaned[len("postgresql+asyncpg://") :]
    if cleaned.startswith("postgresql+psycopg://"):
        return "postgresql://" + cleaned[len("postgresql+psycopg://") :]
    return cleaned


async def connect_postgres(dsn: str) -> Any:
    normalized_dsn = _normalize_postgres_dsn(dsn)
    try:
        import asyncpg

        return await asyncpg.connect(normalized_dsn)
    except ModuleNotFoundError as exc:
        if exc.name != "asyncpg":
            raise

    import psycopg
    from psycopg.rows import dict_row

    conn = await psycopg.AsyncConnection.connect(normalized_dsn, row_factory=dict_row)
    return PsycopgCompatConnection(conn)


class PsycopgCompatConnection:
    def __init__(self, conn: Any):
        self._conn = conn

    async def fetchval(self, query: str, *params: Any) -> Any:
        async with self._conn.cursor() as cursor:
            await cursor.execute(_adapt_query(query), params)
            row = await cursor.fetchone()
        if not row:
            return None
        if isinstance(row, dict):
            return next(iter(row.values()), None)
        return row[0]

    async def execute(self, query: str, *params: Any) -> str:
        async with self._conn.cursor() as cursor:
            await cursor.execute(_adapt_query(query), params)
            status = getattr(cursor, "statusmessage", "") or ""
        await self._conn.commit()
        return status

    async def close(self) -> None:
        await self._conn.close()


def _adapt_query(query: str) -> str:
    return re.sub(r"\$\d+", "%s", query)
