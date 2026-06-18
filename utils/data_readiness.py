"""Cheap checks for whether imported MediaCrawler data can support analysis."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List
from urllib.parse import quote_plus

from config import settings


@dataclass(frozen=True)
class ReadinessTable:
    table: str
    fields: tuple[str, ...]
    platform: str
    content_type: str


READINESS_TABLES: tuple[ReadinessTable, ...] = (
    ReadinessTable("weibo_note", ("content", "source_keyword"), "weibo", "note"),
    ReadinessTable("weibo_note_comment", ("content",), "weibo", "comment"),
    ReadinessTable("bilibili_video", ("title", "desc", "source_keyword"), "bilibili", "video"),
    ReadinessTable("bilibili_video_comment", ("content",), "bilibili", "comment"),
    ReadinessTable("zhihu_content", ("title", "desc", "content_text", "source_keyword"), "zhihu", "content"),
    ReadinessTable("zhihu_comment", ("content",), "zhihu", "comment"),
    ReadinessTable("kuaishou_video", ("title", "desc", "source_keyword"), "kuaishou", "video"),
    ReadinessTable("kuaishou_video_comment", ("content",), "kuaishou", "comment"),
)

STOPWORDS = {
    "about",
    "analysis",
    "brand",
    "days",
    "driving",
    "last",
    "market",
    "negative",
    "public",
    "sentiment",
    "sources",
    "timeframe",
    "what",
}


def readiness_tables_for_platforms(
    platforms: Iterable[str] | None = None,
) -> tuple[ReadinessTable, ...]:
    if not platforms:
        return READINESS_TABLES
    allowed = {
        "weibo" if str(platform).lower() in {"wb", "weibo"} else str(platform).lower()
        for platform in platforms
    }
    return tuple(table for table in READINESS_TABLES if table.platform in allowed)


def _build_postgres_dsn() -> str:
    password = quote_plus(settings.DB_PASSWORD or "")
    return (
        f"postgresql://{settings.DB_USER}:{password}"
        f"@{settings.DB_HOST}:{settings.DB_PORT}/{settings.DB_NAME}"
    )


async def fetch_all(query: str, params: list[Any] | None = None) -> list[dict[str, Any]]:
    if (settings.DB_DIALECT or "postgresql").lower() not in ("postgres", "postgresql"):
        raise RuntimeError("Data readiness check currently requires PostgreSQL.")

    try:
        return await _fetch_all_with_psycopg(query, params)
    except ModuleNotFoundError as exc:
        if exc.name != "psycopg":
            raise

    import asyncpg

    conn = await asyncpg.connect(_build_postgres_dsn())
    try:
        rows = await conn.fetch(query, *(params or []))
        return [dict(row) for row in rows]
    finally:
        await conn.close()


async def _fetch_all_with_psycopg(
    query: str,
    params: list[Any] | None = None,
) -> list[dict[str, Any]]:
    import psycopg
    from psycopg.rows import dict_row

    adapted_query, adapted_params = adapt_query_for_psycopg(query, params or [])
    conn = await psycopg.AsyncConnection.connect(
        _build_postgres_dsn(),
        row_factory=dict_row,
    )
    try:
        async with conn.cursor() as cursor:
            await cursor.execute(adapted_query, adapted_params)
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]
    finally:
        await conn.close()


def adapt_query_for_psycopg(
    query: str,
    params: list[Any],
) -> tuple[str, tuple[Any, ...]]:
    adapted_params: list[Any] = []

    def replace(match: re.Match[str]) -> str:
        index = int(match.group(0)[1:]) - 1
        adapted_params.append(params[index])
        return "%s"

    return re.sub(r"\$\d+", replace, query), tuple(adapted_params)


async def check_data_readiness(
    query: str,
    *,
    minimum_total: int = 1,
    minimum_tables: int = 1,
    platforms: Iterable[str] | None = None,
) -> Dict[str, Any]:
    query = (query or "").strip()
    terms = extract_query_terms(query)
    if not query or not terms:
        return _result(
            success=False,
            query=query,
            status="unknown",
            data_ready=False,
            minimum_total=minimum_total,
            minimum_tables=minimum_tables,
            terms=terms,
            checks=[],
            errors=["query is empty or has no searchable terms"],
        )

    checks: List[Dict[str, Any]] = []
    errors: List[str] = []
    for table in readiness_tables_for_platforms(platforms):
        try:
            count = await _count_table_matches(table, terms)
        except Exception as exc:
            errors.append(f"{table.table}: {exc}")
            checks.append(_table_check(table, 0, str(exc)))
            continue
        checks.append(_table_check(table, count, ""))

    total_matches = sum(int(check["match_count"]) for check in checks)
    matched_tables = sum(1 for check in checks if int(check["match_count"]) > 0)
    data_ready = (
        total_matches >= max(1, minimum_total)
        and matched_tables >= max(1, minimum_tables)
    )

    if data_ready:
        status = "ready"
        success = True
    elif not errors:
        status = "ready" if data_ready else "needs_data"
        success = True
    else:
        status = "unknown"
        success = False

    return _result(
        success=success,
        query=query,
        status=status,
        data_ready=data_ready,
        minimum_total=minimum_total,
        minimum_tables=minimum_tables,
        terms=terms,
        checks=checks,
        errors=errors,
    )


def extract_query_terms(query: str, *, limit: int = 6) -> list[str]:
    terms: list[str] = []
    for raw_part in re.split(r"[|,，。:：/\\()\[\]{}\"'!?？!\s]+", query.lower()):
        term = raw_part.strip("-_")
        if len(term) < 2 or term in STOPWORDS or term.isdigit():
            continue
        if term not in terms:
            terms.append(term)
        if len(terms) >= limit:
            break
    return terms


async def _count_table_matches(table: ReadinessTable, terms: Iterable[str]) -> int:
    where_clauses: list[str] = []
    params: list[str] = []
    for term_index, term in enumerate(terms):
        params.append(f"%{term}%")
        placeholder = f"${term_index + 1}"
        field_clauses = [
            f'LOWER(CAST("{field}" AS TEXT)) LIKE {placeholder}'
            for field in table.fields
        ]
        where_clauses.append("(" + " OR ".join(field_clauses) + ")")

    query = (
        f'SELECT COUNT(*) AS match_count FROM "{table.table}" '
        f'WHERE {" OR ".join(where_clauses)}'
    )
    rows = await fetch_all(query, params)
    if not rows:
        return 0
    return int(rows[0].get("match_count") or 0)


def _table_check(table: ReadinessTable, count: int, error: str) -> Dict[str, Any]:
    return {
        "table": table.table,
        "platform": table.platform,
        "content_type": table.content_type,
        "match_count": count,
        "error": error,
    }


def _result(
    *,
    success: bool,
    query: str,
    status: str,
    data_ready: bool,
    minimum_total: int,
    minimum_tables: int,
    terms: list[str],
    checks: list[Dict[str, Any]],
    errors: list[str],
) -> Dict[str, Any]:
    total_matches = sum(int(check["match_count"]) for check in checks)
    matched_tables = sum(1 for check in checks if int(check["match_count"]) > 0)
    if status == "ready":
        message = "Imported MediaCrawler data is ready for BettaFish analysis."
    elif status == "needs_data":
        message = "No imported MediaCrawler records matched the analysis query closely enough."
    else:
        message = "Data readiness could not be confirmed."

    return {
        "success": success,
        "query": query,
        "status": status,
        "data_ready": data_ready,
        "total_matches": total_matches,
        "matched_tables": matched_tables,
        "minimum_total": max(1, minimum_total),
        "minimum_tables": max(1, minimum_tables),
        "message": message,
        "terms": terms,
        "checks": checks,
        "errors": errors,
    }
