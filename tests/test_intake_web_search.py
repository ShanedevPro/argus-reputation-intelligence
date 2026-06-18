from types import SimpleNamespace


def test_clamp_max_results_uses_default_and_bounds_values():
    from utils.intake_web_search import clamp_max_results

    assert clamp_max_results(None, default=5, hard_max=8) == 5
    assert clamp_max_results(0, default=5, hard_max=8) == 1
    assert clamp_max_results(99, default=5, hard_max=8) == 8
    assert clamp_max_results("bad", default=5, hard_max=8) == 5


def test_run_intake_web_search_normalizes_provider_results(monkeypatch):
    from utils import intake_web_search

    calls = []

    class FakeClient:
        provider_name = "FakeSearchClient"

        def web_search_only(self, query, max_results):
            calls.append((query, max_results))
            return SimpleNamespace(
                answer="A concise search answer.",
                webpages=[
                    SimpleNamespace(
                        name="First result",
                        url="https://example.com/first",
                        snippet="First snippet",
                        display_url="example.com",
                        date_last_crawled="2026-05-29",
                    ),
                    SimpleNamespace(
                        name="Second result",
                        url="https://example.com/second",
                        snippet="Second snippet",
                        display_url=None,
                        date_last_crawled=None,
                    ),
                ],
            )

    monkeypatch.setattr(intake_web_search, "load_agent_from_config", lambda: FakeClient())
    monkeypatch.setattr(
        intake_web_search.settings, "SEARCH_TOOL_TYPE", "BochaAPI", raising=False
    )
    monkeypatch.setattr(
        intake_web_search.settings,
        "INTAKE_WEB_SEARCH_DEFAULT_RESULTS",
        5,
        raising=False,
    )
    monkeypatch.setattr(
        intake_web_search.settings, "INTAKE_WEB_SEARCH_MAX_RESULTS", 8, raising=False
    )

    result = intake_web_search.run_intake_web_search("王鹤棣 最近争议", 99)

    assert calls == [("王鹤棣 最近争议", 8)]
    assert result == {
        "success": True,
        "query": "王鹤棣 最近争议",
        "provider": "BochaAPI",
        "results": [
            {
                "title": "First result",
                "url": "https://example.com/first",
                "snippet": "First snippet",
                "published_at": "2026-05-29",
                "source": "example.com",
            },
            {
                "title": "Second result",
                "url": "https://example.com/second",
                "snippet": "Second snippet",
                "published_at": None,
                "source": "example.com",
            },
        ],
        "answer": "A concise search answer.",
    }


def test_api_intake_web_search_rejects_empty_query():
    import app

    response = app.app.test_client().post(
        "/api/intake/web-search",
        json={"query": "   "},
    )

    assert response.status_code == 400
    payload = response.get_json()
    assert payload["success"] is False
    assert "query" in payload["message"].lower()


def test_api_intake_web_search_returns_normalized_results(monkeypatch):
    import app

    def fake_run(query, max_results=None):
        assert query == "王鹤棣 最近争议"
        assert max_results == 7
        return {
            "success": True,
            "query": query,
            "provider": "BochaAPI",
            "results": [
                {
                    "title": "First result",
                    "url": "https://example.com/first",
                    "snippet": "First snippet",
                    "published_at": None,
                    "source": "example.com",
                }
            ],
            "answer": None,
        }

    monkeypatch.setattr(app, "run_intake_web_search", fake_run, raising=False)

    response = app.app.test_client().post(
        "/api/intake/web-search",
        json={"query": "王鹤棣 最近争议", "max_results": 7},
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["success"] is True
    assert payload["provider"] == "BochaAPI"
    assert payload["results"][0]["title"] == "First result"


def test_api_intake_web_search_reports_missing_provider_config(monkeypatch):
    import app

    def fake_run(_query, max_results=None):
        raise app.IntakeWebSearchConfigError(
            "Search provider is not configured. Missing API key."
        )

    monkeypatch.setattr(app, "run_intake_web_search", fake_run, raising=False)

    response = app.app.test_client().post(
        "/api/intake/web-search",
        json={"query": "王鹤棣 最近争议"},
    )

    assert response.status_code == 503
    payload = response.get_json()
    assert payload["success"] is False
    assert "configured" in payload["message"]
    assert "sk-" not in payload["message"]


def test_api_intake_web_search_reports_provider_runtime_failure(monkeypatch):
    import app

    def fake_run(_query, max_results=None):
        raise app.IntakeWebSearchRuntimeError("Search provider request failed.")

    monkeypatch.setattr(app, "run_intake_web_search", fake_run, raising=False)

    response = app.app.test_client().post(
        "/api/intake/web-search",
        json={"query": "王鹤棣 最近争议"},
    )

    assert response.status_code == 502
    payload = response.get_json()
    assert payload["success"] is False
    assert "failed" in payload["message"]
