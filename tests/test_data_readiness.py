import asyncio


def test_readiness_tables_can_be_restricted_to_weibo():
    from utils.data_readiness import readiness_tables_for_platforms

    tables = readiness_tables_for_platforms(["weibo"])

    assert {table.platform for table in tables} == {"weibo"}
    assert {table.table for table in tables} == {"weibo_note", "weibo_note_comment"}


def test_data_readiness_reports_ready_when_imported_records_match(monkeypatch):
    from utils import data_readiness

    async def fake_fetch_all(query, params=None):
        if 'FROM "weibo_note"' in query:
            return [{"match_count": 2}]
        if 'FROM "bilibili_video"' in query:
            return [{"match_count": 1}]
        return [{"match_count": 0}]

    monkeypatch.setattr(data_readiness, "fetch_all", fake_fetch_all)

    result = asyncio.run(
        data_readiness.check_data_readiness(
            "Navos | What is driving negative sentiment? | Last 30 days",
            minimum_total=2,
            minimum_tables=1,
        )
    )

    assert result["success"] is True
    assert result["status"] == "ready"
    assert result["data_ready"] is True
    assert result["total_matches"] == 3
    assert result["matched_tables"] == 2
    assert result["terms"][0] == "navos"


def test_data_readiness_reports_needs_data_when_no_records_match(monkeypatch):
    from utils import data_readiness

    async def fake_fetch_all(_query, params=None):
        return [{"match_count": 0}]

    monkeypatch.setattr(data_readiness, "fetch_all", fake_fetch_all)

    result = asyncio.run(data_readiness.check_data_readiness("Unknown Brand"))

    assert result["success"] is True
    assert result["status"] == "needs_data"
    assert result["data_ready"] is False
    assert result["total_matches"] == 0
    assert "No imported MediaCrawler records matched" in result["message"]


def test_data_readiness_still_reports_ready_when_optional_tables_fail(monkeypatch):
    from utils import data_readiness

    async def fake_fetch_all(query, params=None):
        if 'FROM "weibo_note"' in query:
            return [{"match_count": 2}]
        raise RuntimeError("relation does not exist")

    monkeypatch.setattr(data_readiness, "fetch_all", fake_fetch_all)

    result = asyncio.run(data_readiness.check_data_readiness("Navos"))

    assert result["success"] is True
    assert result["status"] == "ready"
    assert result["data_ready"] is True
    assert result["total_matches"] == 2
    assert result["errors"]


def test_data_readiness_reports_unknown_when_database_checks_fail(monkeypatch):
    from utils import data_readiness

    async def fake_fetch_all(_query, params=None):
        raise RuntimeError("database unavailable")

    monkeypatch.setattr(data_readiness, "fetch_all", fake_fetch_all)

    result = asyncio.run(data_readiness.check_data_readiness("Navos"))

    assert result["success"] is False
    assert result["status"] == "unknown"
    assert result["data_ready"] is False
    assert result["total_matches"] == 0
    assert result["errors"]


def test_data_readiness_builds_psycopg_query_placeholders():
    from utils.data_readiness import adapt_query_for_psycopg

    query, params = adapt_query_for_psycopg(
        'SELECT COUNT(*) FROM "weibo_note" WHERE "content" LIKE $1 OR "source_keyword" LIKE $2',
        ["%navos%", "%navos%"],
    )

    assert query == (
        'SELECT COUNT(*) FROM "weibo_note" '
        'WHERE "content" LIKE %s OR "source_keyword" LIKE %s'
    )
    assert params == ("%navos%", "%navos%")


def test_data_readiness_duplicates_reused_psycopg_placeholders():
    from utils.data_readiness import adapt_query_for_psycopg

    query, params = adapt_query_for_psycopg(
        'SELECT COUNT(*) FROM "weibo_note" '
        'WHERE ("content" LIKE $1 OR "source_keyword" LIKE $1) '
        'OR ("content" LIKE $2 OR "source_keyword" LIKE $2)',
        ["%navos%", "%reputation%"],
    )

    assert query == (
        'SELECT COUNT(*) FROM "weibo_note" '
        'WHERE ("content" LIKE %s OR "source_keyword" LIKE %s) '
        'OR ("content" LIKE %s OR "source_keyword" LIKE %s)'
    )
    assert params == ("%navos%", "%navos%", "%reputation%", "%reputation%")


def test_api_data_readiness_uses_backend_check(monkeypatch):
    import app

    async def fake_check(query, minimum_total=1, minimum_tables=1, platforms=None):
        assert query == "Navos"
        assert minimum_total == 2
        assert minimum_tables == 1
        assert platforms is None
        return {
            "success": True,
            "query": query,
            "status": "ready",
            "data_ready": True,
            "total_matches": 2,
            "matched_tables": 1,
            "minimum_total": minimum_total,
            "minimum_tables": minimum_tables,
            "message": "Imported MediaCrawler data is ready.",
            "terms": ["navos"],
            "checks": [],
            "errors": [],
        }

    monkeypatch.setattr(app, "check_data_readiness", fake_check, raising=False)

    response = app.app.test_client().post(
        "/api/data/readiness",
        json={"query": "Navos", "minimum_total": 2},
    )

    assert response.status_code == 200
    assert response.get_json()["data_ready"] is True


def test_api_data_readiness_accepts_platform_filter(monkeypatch):
    import app

    received = {}

    async def fake_check(query, minimum_total=1, minimum_tables=1, platforms=None):
        received["platforms"] = platforms
        return {
            "success": True,
            "query": query,
            "status": "ready",
            "data_ready": True,
            "total_matches": 2,
            "matched_tables": 1,
            "minimum_total": minimum_total,
            "minimum_tables": minimum_tables,
            "message": "Imported MediaCrawler data is ready.",
            "terms": ["navos"],
            "checks": [],
            "errors": [],
        }

    monkeypatch.setattr(app, "check_data_readiness", fake_check, raising=False)

    response = app.app.test_client().post(
        "/api/data/readiness",
        json={"query": "Navos", "platforms": ["weibo"]},
    )

    assert response.status_code == 200
    assert received["platforms"] == ["weibo"]
