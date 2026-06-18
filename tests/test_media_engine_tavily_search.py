def _set_required_media_env(monkeypatch):
    for key in [
        "INSIGHT_ENGINE_API_KEY",
        "MEDIA_ENGINE_API_KEY",
        "QUERY_ENGINE_API_KEY",
        "REPORT_ENGINE_API_KEY",
        "FORUM_HOST_API_KEY",
        "KEYWORD_OPTIMIZER_API_KEY",
        "TAVILY_API_KEY",
    ]:
        monkeypatch.setenv(key, "test-key")


def test_media_search_uses_package_config_when_top_level_config_is_polluted(monkeypatch):
    import importlib.util
    import sys
    import types
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    fake_pkg = types.ModuleType("MediaEngine")
    fake_pkg.__path__ = []
    fake_tools = types.ModuleType("MediaEngine.tools")
    fake_tools.__path__ = []
    fake_utils = types.ModuleType("MediaEngine.utils")
    fake_utils.__path__ = []
    fake_config = types.ModuleType("MediaEngine.utils.config")
    fake_config.settings = types.SimpleNamespace(
        BOCHA_BASE_URL="https://package-config.example/web-search",
        BOCHA_WEB_SEARCH_API_KEY="package-bocha-key",
        TAVILY_API_KEY="package-tavily-key",
        ANSPIRE_BASE_URL="https://package-config.example/anspire",
        ANSPIRE_API_KEY="package-anspire-key",
        SEARCH_TOOL_TYPE="TavilyAPI",
    )
    polluted_top_level_config = types.ModuleType("config")
    polluted_top_level_config.settings = types.SimpleNamespace(
        BOCHA_BASE_URL="https://wrong.example",
        BOCHA_WEB_SEARCH_API_KEY="wrong-key",
        SEARCH_TOOL_TYPE="BochaAPI",
    )
    fake_retry = types.ModuleType("retry_helper")
    fake_retry.SEARCH_API_RETRY_CONFIG = {}
    fake_retry.with_graceful_retry = lambda _config, default_return=None: (lambda fn: fn)
    fake_tavily = types.ModuleType("tavily")

    class FakeTavilyClient:
        def __init__(self, api_key):
            self.api_key = api_key

    fake_tavily.TavilyClient = FakeTavilyClient

    monkeypatch.setitem(sys.modules, "MediaEngine", fake_pkg)
    monkeypatch.setitem(sys.modules, "MediaEngine.tools", fake_tools)
    monkeypatch.setitem(sys.modules, "MediaEngine.utils", fake_utils)
    monkeypatch.setitem(sys.modules, "MediaEngine.utils.config", fake_config)
    monkeypatch.setitem(sys.modules, "config", polluted_top_level_config)
    monkeypatch.setitem(sys.modules, "retry_helper", fake_retry)
    monkeypatch.setitem(sys.modules, "tavily", fake_tavily)

    spec = importlib.util.spec_from_file_location(
        "MediaEngine.tools.search",
        root / "MediaEngine" / "tools" / "search.py",
    )
    module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, "MediaEngine.tools.search", module)
    assert spec.loader is not None
    spec.loader.exec_module(module)

    assert module.BochaMultimodalSearch.BOCHA_BASE_URL == "https://package-config.example/web-search"
    assert module.load_agent_from_config().__class__.__name__ == "TavilyMultimodalSearch"


def test_settings_accept_tavily_search_tool_type(monkeypatch):
    _set_required_media_env(monkeypatch)

    from config import Settings as RootSettings
    from MediaEngine.utils.config import Settings as MediaSettings

    assert RootSettings(SEARCH_TOOL_TYPE="TavilyAPI").SEARCH_TOOL_TYPE == "TavilyAPI"
    assert MediaSettings(SEARCH_TOOL_TYPE="TavilyAPI").SEARCH_TOOL_TYPE == "TavilyAPI"


def test_tavily_multimodal_search_maps_response_to_bocha_shape(monkeypatch):
    _set_required_media_env(monkeypatch)

    from MediaEngine.tools import search as search_module

    calls = []

    class FakeTavilyClient:
        def __init__(self, api_key):
            self.api_key = api_key

        def search(self, **kwargs):
            calls.append(kwargs)
            return {
                "answer": "Singapore EV charging is expanding steadily.",
                "results": [
                    {
                        "title": "EV charging outlook",
                        "url": "https://example.com/outlook",
                        "content": "Market outlook and sentiment summary.",
                        "published_date": "2026-05-01",
                    }
                ],
                "images": [
                    {
                        "url": "https://example.com/charger.jpg",
                        "description": "EV charger",
                        "source_url": "https://example.com/gallery",
                    }
                ],
            }

    monkeypatch.setattr(search_module, "TavilyClient", FakeTavilyClient, raising=False)

    search = search_module.TavilyMultimodalSearch(api_key="tvly-test")
    response = search.comprehensive_search("Singapore EV charging", max_results=3)

    assert calls[0]["query"] == "Singapore EV charging"
    assert calls[0]["max_results"] == 3
    assert calls[0]["include_images"] is True
    assert response.query == "Singapore EV charging"
    assert response.answer == "Singapore EV charging is expanding steadily."
    assert response.webpages[0].name == "EV charging outlook"
    assert response.webpages[0].url == "https://example.com/outlook"
    assert response.webpages[0].snippet == "Market outlook and sentiment summary."
    assert response.webpages[0].date_last_crawled == "2026-05-01"
    assert response.images[0].content_url == "https://example.com/charger.jpg"
    assert response.images[0].host_page_url == "https://example.com/gallery"


def test_bocha_web_search_response_maps_to_bocha_shape(monkeypatch):
    _set_required_media_env(monkeypatch)

    from MediaEngine.tools import search as search_module

    calls = []

    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "code": 200,
                "msg": None,
                "data": {
                    "webPages": {
                        "value": [
                            {
                                "name": "Xiaomi SU7 delivery dispute",
                                "url": "https://example.com/su7",
                                "displayUrl": "example.com/su7",
                                "snippet": "Owners discussed delayed delivery windows.",
                                "summary": "A concise summary of the delivery dispute.",
                                "dateLastCrawled": "2026-05-17T10:00:00+08:00",
                            }
                        ]
                    },
                    "images": {
                        "value": [
                            {
                                "name": "SU7 delivery chart",
                                "contentUrl": "https://example.com/chart.jpg",
                                "hostPageUrl": "https://example.com/gallery",
                                "thumbnailUrl": "https://example.com/thumb.jpg",
                                "width": 640,
                                "height": 360,
                            }
                        ]
                    },
                },
            }

    def fake_post(url, headers=None, json=None, timeout=None):
        calls.append({"url": url, "json": json, "timeout": timeout})
        return FakeResponse()

    monkeypatch.setattr(search_module.requests, "post", fake_post)

    search = search_module.BochaMultimodalSearch(api_key="bocha-test")
    response = search.comprehensive_search("小米SU7交付争议", max_results=3)

    assert calls == [
        {
            "url": "https://api.bocha.cn/v1/web-search",
            "json": {
                "query": "小米SU7交付争议",
                "count": 3,
                "summary": True,
            },
            "timeout": 30,
        }
    ]
    assert response.query == "小米SU7交付争议"
    assert response.answer == "A concise summary of the delivery dispute."
    assert response.webpages[0].name == "Xiaomi SU7 delivery dispute"
    assert response.webpages[0].url == "https://example.com/su7"
    assert response.webpages[0].snippet == "A concise summary of the delivery dispute."
    assert response.webpages[0].display_url == "example.com/su7"
    assert response.webpages[0].date_last_crawled == "2026-05-17T10:00:00+08:00"
    assert response.images[0].content_url == "https://example.com/chart.jpg"
    assert response.images[0].host_page_url == "https://example.com/gallery"


def test_create_agent_selects_tavily_agent(monkeypatch):
    _set_required_media_env(monkeypatch)

    from MediaEngine import agent as agent_module

    settings = type("FakeSettings", (), {"SEARCH_TOOL_TYPE": "TavilyAPI"})()

    class FakeBochaAgent:
        def __init__(self, config):
            self.config = config

    class FakeAnspireAgent:
        def __init__(self, config):
            self.config = config

    class FakeTavilyAgent:
        def __init__(self, config):
            self.config = config

    monkeypatch.setattr(agent_module, "Settings", lambda: settings)
    monkeypatch.setattr(agent_module, "DeepSearchAgent", FakeBochaAgent)
    monkeypatch.setattr(agent_module, "AnspireSearchAgent", FakeAnspireAgent)
    monkeypatch.setattr(agent_module, "TavilySearchAgent", FakeTavilyAgent, raising=False)

    agent = agent_module.create_agent()

    assert isinstance(agent, FakeTavilyAgent)
    assert agent.config is settings
