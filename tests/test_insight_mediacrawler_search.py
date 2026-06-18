import importlib.util
import sys
import types
from datetime import date
from pathlib import Path
from types import SimpleNamespace


ROOT = Path(__file__).resolve().parents[1]


def _load_keyword_optimizer_module(monkeypatch):
    fake_pkg = types.ModuleType("InsightEngine")
    fake_pkg.__path__ = []
    fake_tools = types.ModuleType("InsightEngine.tools")
    fake_tools.__path__ = []
    fake_utils = types.ModuleType("InsightEngine.utils")
    fake_utils.__path__ = []
    fake_config = types.ModuleType("InsightEngine.utils.config")
    fake_config.settings = SimpleNamespace(
        KEYWORD_OPTIMIZER_API_KEY="test-key",
        KEYWORD_OPTIMIZER_BASE_URL="https://example.test/v1",
        KEYWORD_OPTIMIZER_MODEL_NAME="test-model",
    )
    polluted_top_level_config = types.ModuleType("config")
    polluted_top_level_config.settings = SimpleNamespace(
        REPORT_ENGINE_API_KEY="wrong-config",
    )
    fake_retry = types.ModuleType("retry_helper")
    fake_retry.SEARCH_API_RETRY_CONFIG = {}
    fake_retry.with_graceful_retry = lambda _config, default_return=None: (lambda fn: fn)

    class FakeOpenAI:
        def __init__(self, *args, **kwargs):
            pass

    fake_openai = types.ModuleType("openai")
    fake_openai.OpenAI = FakeOpenAI

    monkeypatch.setitem(sys.modules, "InsightEngine", fake_pkg)
    monkeypatch.setitem(sys.modules, "InsightEngine.tools", fake_tools)
    monkeypatch.setitem(sys.modules, "InsightEngine.utils", fake_utils)
    monkeypatch.setitem(sys.modules, "InsightEngine.utils.config", fake_config)
    monkeypatch.setitem(sys.modules, "config", polluted_top_level_config)
    monkeypatch.setitem(sys.modules, "retry_helper", fake_retry)
    monkeypatch.setitem(sys.modules, "openai", fake_openai)

    spec = importlib.util.spec_from_file_location(
        "InsightEngine.tools.keyword_optimizer",
        ROOT / "InsightEngine" / "tools" / "keyword_optimizer.py",
    )
    module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, "InsightEngine.tools.keyword_optimizer", module)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_keyword_optimizer_filters_json_and_reasoning_fragments(monkeypatch):
    keyword_module = _load_keyword_optimizer_module(monkeypatch)
    optimizer = keyword_module.KeywordOptimizer(api_key="test-key")

    keywords = optimizer._validate_keywords(
        [
            '["王鹤棣',
            "亲爱的客栈",
            "不舒服文学",
            '网络梗"]',
            "选择'王鹤棣'作为核心词",
            "最形象的说法。'不适感",
            "王鹤棣回应",
        ]
    )

    assert keywords == ["亲爱的客栈", "不舒服文学", "王鹤棣回应"]


def test_keyword_optimizer_filters_weak_standalone_terms_but_keeps_specific_terms(monkeypatch):
    keyword_module = _load_keyword_optimizer_module(monkeypatch)

    optimizer = keyword_module.KeywordOptimizer(api_key="", max_keywords=8)
    keywords = optimizer._validate_keywords(
        [
            "王鹤棣",
            "客栈",
            "不舒服",
            "争议",
            "王鹤棣不舒服",
            "不舒服文学",
            "小米SU7交付争议",
            "蓝鲸云服务数据泄露",
        ]
    )

    assert keywords == [
        "王鹤棣",
        "王鹤棣不舒服",
        "不舒服文学",
        "小米SU7交付争议",
        "蓝鲸云服务数据泄露",
    ]


def test_keyword_optimizer_rejects_semantic_drift_from_original_query(monkeypatch):
    keyword_module = _load_keyword_optimizer_module(monkeypatch)

    optimizer = keyword_module.KeywordOptimizer(api_key="", max_keywords=8)
    keywords = optimizer._validate_keywords(
        ["难受", "身体不适", "焦虑", "头晕"],
        original_query="我当时确实不舒服",
    )

    assert keywords == ["我当时确实不舒服"]


def _load_search_module(monkeypatch, dialect="postgresql"):
    fake_pkg = types.ModuleType("InsightEngine")
    fake_pkg.__path__ = []
    fake_tools = types.ModuleType("InsightEngine.tools")
    fake_tools.__path__ = []
    fake_utils = types.ModuleType("InsightEngine.utils")
    fake_utils.__path__ = []
    fake_config = types.ModuleType("InsightEngine.utils.config")
    fake_config.settings = SimpleNamespace(DB_DIALECT=dialect)
    fake_db = types.ModuleType("InsightEngine.utils.db")
    fake_db.fetch_all = lambda query, params=None: []

    monkeypatch.setitem(sys.modules, "InsightEngine", fake_pkg)
    monkeypatch.setitem(sys.modules, "InsightEngine.tools", fake_tools)
    monkeypatch.setitem(sys.modules, "InsightEngine.utils", fake_utils)
    monkeypatch.setitem(sys.modules, "InsightEngine.utils.config", fake_config)
    monkeypatch.setitem(sys.modules, "InsightEngine.utils.db", fake_db)

    spec = importlib.util.spec_from_file_location(
        "InsightEngine.tools.search",
        ROOT / "InsightEngine" / "tools" / "search.py",
    )
    module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, "InsightEngine.tools.search", module)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_search_topic_on_platform_uses_postgres_identifiers_and_named_params(monkeypatch):
    search_module = _load_search_module(monkeypatch, dialect="postgresql")
    client = search_module.MediaCrawlerDB()
    captured = []

    def fake_execute(query, params=None):
        captured.append((query, params))
        return []

    monkeypatch.setattr(client, "_execute_query", fake_execute)

    response = client.search_topic_on_platform(
        platform="weibo",
        topic="小米SU7",
        start_date="2026-02-20",
        end_date="2026-05-20",
        limit=30,
    )

    assert response.results == []
    assert all("`" not in query for query, _params in captured)
    assert all("%s" not in query for query, _params in captured)
    note_query, note_params = captured[0]
    assert 'FROM "weibo_note"' in note_query
    assert '"content" LIKE :term_0' in note_query
    assert '"source_keyword" LIKE :term_1' in note_query
    assert '"create_date_time" >= :start_time' in note_query
    assert note_params == {
        "term_0": "%小米SU7%",
        "term_1": "%小米SU7%",
        "start_time": "2026-02-20",
        "end_time": "2026-05-21",
        "limit": 30,
    }


def test_search_topic_on_platform_keeps_mysql_identifiers_with_named_params(monkeypatch):
    search_module = _load_search_module(monkeypatch, dialect="mysql")
    client = search_module.MediaCrawlerDB()
    captured = []

    def fake_execute(query, params=None):
        captured.append((query, params))
        return []

    monkeypatch.setattr(client, "_execute_query", fake_execute)

    client.search_topic_on_platform(platform="weibo", topic="小米SU7", limit=30)

    note_query, note_params = captured[0]
    assert "FROM `weibo_note`" in note_query
    assert "`content` LIKE :term_0" in note_query
    assert "%s" not in note_query
    assert note_params == {
        "term_0": "%小米SU7%",
        "term_1": "%小米SU7%",
        "limit": 30,
    }


def test_search_topic_by_date_applies_postgres_date_filter(monkeypatch):
    search_module = _load_search_module(monkeypatch, dialect="postgresql")
    client = search_module.MediaCrawlerDB()
    captured = []

    def fake_execute(query, params=None):
        captured.append((query, params))
        return []

    monkeypatch.setattr(client, "_execute_query", fake_execute)

    response = client.search_topic_by_date(
        topic="LABUBU",
        start_date="2026-02-27",
        end_date="2026-05-27",
        limit_per_table=20,
    )

    assert response.results == []
    assert all("%s" not in query for query, _params in captured)
    weibo_query, weibo_params = next(
        (query, params)
        for query, params in captured
        if 'FROM "weibo_note"' in query
    )
    assert '"content" LIKE :term_0' in weibo_query
    assert '"source_keyword" LIKE :term_1' in weibo_query
    assert '"create_date_time" >= :start_time' in weibo_query
    assert '"create_date_time" < :end_time' in weibo_query
    assert weibo_params == {
        "term_0": "%LABUBU%",
        "term_1": "%LABUBU%",
        "start_time": "2026-02-27",
        "end_time": "2026-05-28",
        "limit": 20,
    }


def test_search_topic_by_date_uses_int_params_for_postgres_zhihu_sec_str(monkeypatch):
    search_module = _load_search_module(monkeypatch, dialect="postgresql")
    client = search_module.MediaCrawlerDB()
    captured = []

    def fake_execute(query, params=None):
        captured.append((query, params))
        return []

    monkeypatch.setattr(client, "_execute_query", fake_execute)

    client.search_topic_by_date(
        topic="王鹤棣",
        start_date="2026-05-01",
        end_date="2026-05-02",
        limit_per_table=10,
    )

    zhihu_query, zhihu_params = next(
        (query, params)
        for query, params in captured
        if 'FROM "zhihu_content"' in query
    )
    assert 'CAST("created_time" AS BIGINT) >= :start_time' in zhihu_query
    assert isinstance(zhihu_params["start_time"], int)
    assert isinstance(zhihu_params["end_time"], int)


def test_search_topic_by_date_uses_date_params_for_postgres_daily_news(monkeypatch):
    search_module = _load_search_module(monkeypatch, dialect="postgresql")
    client = search_module.MediaCrawlerDB()
    captured = []

    def fake_execute(query, params=None):
        captured.append((query, params))
        return []

    monkeypatch.setattr(client, "_execute_query", fake_execute)

    client.search_topic_by_date(
        topic="王鹤棣",
        start_date="2026-05-01",
        end_date="2026-05-02",
        limit_per_table=10,
    )

    news_query, news_params = next(
        (query, params)
        for query, params in captured
        if 'FROM "daily_news"' in query
    )
    assert '"crawl_date" >= :start_time' in news_query
    assert news_params["start_time"] == date(2026, 5, 1)
    assert news_params["end_time"] == date(2026, 5, 3)


def test_search_topic_on_platform_uses_int_params_for_postgres_zhihu_sec_str(monkeypatch):
    search_module = _load_search_module(monkeypatch, dialect="postgresql")
    client = search_module.MediaCrawlerDB()
    captured = []

    def fake_execute(query, params=None):
        captured.append((query, params))
        return []

    monkeypatch.setattr(client, "_execute_query", fake_execute)

    client.search_topic_on_platform(
        platform="zhihu",
        topic="王鹤棣",
        start_date="2026-05-01",
        end_date="2026-05-02",
        limit=10,
    )

    zhihu_query, zhihu_params = captured[0]
    assert 'FROM "zhihu_content"' in zhihu_query
    assert 'CAST("created_time" AS BIGINT) >= :start_time' in zhihu_query
    assert isinstance(zhihu_params["start_time"], int)
    assert isinstance(zhihu_params["end_time"], int)


def test_get_comments_for_topic_uses_postgres_weibo_comment_query(monkeypatch):
    search_module = _load_search_module(monkeypatch, dialect="postgresql")
    client = search_module.MediaCrawlerDB()
    client._table_columns_cache.clear()
    captured = []

    def fake_execute(query, params=None):
        captured.append((query, params))
        if "information_schema.columns" in query:
            if params == {"table_name": "weibo_note_comment"}:
                return [
                    {"column_name": "content"},
                    {"column_name": "nickname"},
                    {"column_name": "create_time"},
                    {"column_name": "comment_like_count"},
                ]
            return []
        if 'FROM "weibo_note_comment"' in query:
            return [
                {
                    "platform": "weibo",
                    "content": "王鹤棣这次确实不舒服",
                    "author": "user-a",
                    "ts": "2026-05-27T10:00:00",
                    "likes": 12,
                    "source_table": "weibo_note_comment",
                }
            ]
        return []

    monkeypatch.setattr(client, "_execute_query", fake_execute)

    response = client.get_comments_for_topic("王鹤棣", limit=50)

    assert response.results_count == 1
    assert response.results[0].platform == "weibo"
    assert response.results[0].title_or_content == "王鹤棣这次确实不舒服"
    assert response.results[0].engagement == {"likes": 12}
    assert any("information_schema.columns" in query for query, _params in captured)
    assert not any("SHOW COLUMNS" in query for query, _params in captured)
    comment_query, comment_params = next(
        (query, params)
        for query, params in captured
        if 'FROM "weibo_note_comment"' in query
    )
    assert "`" not in comment_query
    assert "%s" not in comment_query
    assert '"content" LIKE :term' in comment_query
    assert '"comment_like_count" as likes' in comment_query
    assert comment_params == {"term": "%王鹤棣%", "limit": 50}
