from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_search_node_output_preserves_tool_date_platform_and_sentiment_fields():
    from utils.search_node_output import build_search_node_output

    output = build_search_node_output(
        {
            "search_query": "小米SU7交付争议",
            "search_tool": "search_topic_on_platform",
            "reasoning": "Need Weibo samples.",
            "platform": "weibo",
            "start_date": "2026-02-18",
            "end_date": "2026-05-18",
            "enable_sentiment": True,
        }
    )

    assert output == {
        "search_query": "小米SU7交付争议",
        "search_tool": "search_topic_on_platform",
        "reasoning": "Need Weibo samples.",
        "platform": "weibo",
        "start_date": "2026-02-18",
        "end_date": "2026-05-18",
        "enable_sentiment": True,
    }


def test_search_nodes_use_shared_output_builder():
    for relative_path in [
        "QueryEngine/nodes/search_node.py",
        "MediaEngine/nodes/search_node.py",
        "InsightEngine/nodes/search_node.py",
    ]:
        source = (ROOT / relative_path).read_text(encoding="utf-8")
        assert "build_search_node_output" in source


def test_reflection_nodes_preserve_empty_search_query_as_stop_signal(monkeypatch):
    output = '{"search_query": "", "search_tool": "", "reasoning": "已有证据足够，无需继续搜索"}'
    monkeypatch.setenv("QUERY_ENGINE_API_KEY", "test-key")
    monkeypatch.setenv("QUERY_ENGINE_MODEL_NAME", "test-model")
    monkeypatch.setenv("TAVILY_API_KEY", "test-key")
    monkeypatch.setenv("MEDIA_ENGINE_API_KEY", "test-key")
    monkeypatch.setenv("MEDIA_ENGINE_MODEL_NAME", "test-model")
    monkeypatch.setenv("BOCHA_API_KEY", "test-key")
    monkeypatch.setenv("INSIGHT_ENGINE_API_KEY", "test-key")
    monkeypatch.setenv("INSIGHT_ENGINE_MODEL_NAME", "test-model")
    monkeypatch.setenv("QUERY_ENGINE_API_KEY", "test-key")
    monkeypatch.setenv("QUERY_ENGINE_MODEL_NAME", "test-model")
    monkeypatch.setenv("REPORT_ENGINE_API_KEY", "test-key")
    monkeypatch.setenv("FORUM_HOST_API_KEY", "test-key")
    monkeypatch.setenv("KEYWORD_OPTIMIZER_API_KEY", "test-key")
    monkeypatch.setenv("TAVILY_API_KEY", "test-key")
    monkeypatch.setenv("INSIGHT_ENGINE_API_KEY", "test-key")
    monkeypatch.setenv("INSIGHT_ENGINE_MODEL_NAME", "test-model")
    monkeypatch.setenv("REPORT_ENGINE_API_KEY", "test-key")
    monkeypatch.setenv("FORUM_HOST_API_KEY", "test-key")
    monkeypatch.setenv("KEYWORD_OPTIMIZER_API_KEY", "test-key")

    from QueryEngine.nodes.search_node import ReflectionNode as QueryReflectionNode
    from MediaEngine.nodes.search_node import ReflectionNode as MediaReflectionNode
    from InsightEngine.nodes.search_node import ReflectionNode as InsightReflectionNode

    for node_class in [
        QueryReflectionNode,
        MediaReflectionNode,
        InsightReflectionNode,
    ]:
        result = node_class(llm_client=None).process_output(output)
        assert result["search_query"] == ""
        assert "无需继续搜索" in result["reasoning"]
        assert result.get("search_tool") in (None, "")
        assert result["search_query"] != "深度研究补充信息"


def test_reflection_nodes_fallback_without_traceback_on_non_json_model_output(capsys, monkeypatch):
    output = "The request was rejected because it was considered high risk"
    monkeypatch.setenv("QUERY_ENGINE_API_KEY", "test-key")
    monkeypatch.setenv("QUERY_ENGINE_MODEL_NAME", "test-model")
    monkeypatch.setenv("TAVILY_API_KEY", "test-key")
    monkeypatch.setenv("MEDIA_ENGINE_API_KEY", "test-key")
    monkeypatch.setenv("MEDIA_ENGINE_MODEL_NAME", "test-model")
    monkeypatch.setenv("BOCHA_API_KEY", "test-key")
    monkeypatch.setenv("INSIGHT_ENGINE_API_KEY", "test-key")
    monkeypatch.setenv("INSIGHT_ENGINE_MODEL_NAME", "test-model")
    monkeypatch.setenv("REPORT_ENGINE_API_KEY", "test-key")
    monkeypatch.setenv("FORUM_HOST_API_KEY", "test-key")
    monkeypatch.setenv("KEYWORD_OPTIMIZER_API_KEY", "test-key")

    from QueryEngine.nodes.search_node import ReflectionNode as QueryReflectionNode
    from MediaEngine.nodes.search_node import ReflectionNode as MediaReflectionNode
    from InsightEngine.nodes.search_node import ReflectionNode as InsightReflectionNode

    for node_class in [
        QueryReflectionNode,
        MediaReflectionNode,
        InsightReflectionNode,
    ]:
        result = node_class(llm_client=None).process_output(output)
        assert result["search_query"] == "深度研究补充信息"
        assert "解析失败" in result["reasoning"]

    captured = capsys.readouterr()
    combined_output = captured.out + captured.err
    assert "Traceback" not in combined_output
    assert "AttributeError" not in combined_output


def test_agents_skip_reflection_search_when_query_is_empty():
    for relative_path in [
        "QueryEngine/agent.py",
        "MediaEngine/agent.py",
        "InsightEngine/agent.py",
    ]:
        source = (ROOT / relative_path).read_text(encoding="utf-8")
        assert "if not search_query.strip()" in source
        assert "跳过本轮反思搜索" in source


def test_agents_treat_reflection_generation_failure_as_optional(monkeypatch):
    class ParagraphResearch:
        latest_summary = "已有初始总结"

    class Paragraph:
        title = "段落"
        content = "内容"
        research = ParagraphResearch()

    class State:
        paragraphs = [Paragraph()]

    class FailingReflectionNode:
        def run(self, _input):
            raise RuntimeError("temporary llm failure")

    class Config:
        MAX_REFLECTIONS = 1

    monkeypatch.setenv("QUERY_ENGINE_API_KEY", "test-key")
    monkeypatch.setenv("QUERY_ENGINE_MODEL_NAME", "test-model")
    monkeypatch.setenv("TAVILY_API_KEY", "test-key")
    monkeypatch.setenv("MEDIA_ENGINE_API_KEY", "test-key")
    monkeypatch.setenv("MEDIA_ENGINE_MODEL_NAME", "test-model")
    monkeypatch.setenv("BOCHA_API_KEY", "test-key")
    monkeypatch.setenv("INSIGHT_ENGINE_API_KEY", "test-key")
    monkeypatch.setenv("INSIGHT_ENGINE_MODEL_NAME", "test-model")
    monkeypatch.setenv("REPORT_ENGINE_API_KEY", "test-key")
    monkeypatch.setenv("FORUM_HOST_API_KEY", "test-key")
    monkeypatch.setenv("KEYWORD_OPTIMIZER_API_KEY", "test-key")

    from QueryEngine.agent import DeepSearchAgent as QueryAgent
    from MediaEngine.agent import DeepSearchAgent as MediaAgent
    from InsightEngine.agent import DeepSearchAgent as InsightAgent

    for agent_class in [QueryAgent, MediaAgent, InsightAgent]:
        agent = object.__new__(agent_class)
        agent.state = State()
        agent.config = Config()
        agent.reflection_node = FailingReflectionNode()

        def fail_search(*_args, **_kwargs):
            raise AssertionError("reflection search should not run after generation failure")

        agent.execute_search_tool = fail_search
        agent._reflection_loop(0)


def test_agents_apply_configured_paragraph_limit(monkeypatch):
    from types import SimpleNamespace

    monkeypatch.setenv("QUERY_ENGINE_API_KEY", "test-key")
    monkeypatch.setenv("QUERY_ENGINE_MODEL_NAME", "test-model")
    monkeypatch.setenv("TAVILY_API_KEY", "test-key")
    monkeypatch.setenv("MEDIA_ENGINE_API_KEY", "test-key")
    monkeypatch.setenv("MEDIA_ENGINE_MODEL_NAME", "test-model")
    monkeypatch.setenv("BOCHA_API_KEY", "test-key")
    monkeypatch.setenv("INSIGHT_ENGINE_API_KEY", "test-key")
    monkeypatch.setenv("INSIGHT_ENGINE_MODEL_NAME", "test-model")
    monkeypatch.setenv("REPORT_ENGINE_API_KEY", "test-key")
    monkeypatch.setenv("FORUM_HOST_API_KEY", "test-key")
    monkeypatch.setenv("KEYWORD_OPTIMIZER_API_KEY", "test-key")

    from QueryEngine.agent import DeepSearchAgent as QueryAgent
    from MediaEngine.agent import DeepSearchAgent as MediaAgent
    from InsightEngine.agent import DeepSearchAgent as InsightAgent

    for agent_class in [QueryAgent, MediaAgent, InsightAgent]:
        agent = object.__new__(agent_class)
        agent.config = SimpleNamespace(MAX_PARAGRAPHS=2)
        agent.state = SimpleNamespace(
            paragraphs=[
                SimpleNamespace(title="一"),
                SimpleNamespace(title="二"),
                SimpleNamespace(title="三"),
            ]
        )

        agent._limit_report_paragraphs()

        assert [paragraph.title for paragraph in agent.state.paragraphs] == ["一", "二"]


def test_insight_auto_sentiment_budget_limits_repeated_expensive_runs(monkeypatch):
    from types import SimpleNamespace

    monkeypatch.setenv("INSIGHT_ENGINE_API_KEY", "test-key")
    monkeypatch.setenv("INSIGHT_ENGINE_MODEL_NAME", "test-model")
    monkeypatch.setenv("KEYWORD_OPTIMIZER_API_KEY", "test-key")

    from InsightEngine.agent import DeepSearchAgent as InsightAgent

    agent = object.__new__(InsightAgent)
    agent.config = SimpleNamespace(MAX_AUTO_SENTIMENT_SEARCHES=1)
    agent._auto_sentiment_runs = 0

    assert agent._should_run_auto_sentiment(True, 5) is True
    assert agent._should_run_auto_sentiment(True, 5) is False
    assert agent._should_run_auto_sentiment(False, 5) is False
    assert agent._should_run_auto_sentiment(True, 0) is False


def test_insight_agent_uses_configured_keyword_optimizer_instance(monkeypatch):
    from types import SimpleNamespace

    monkeypatch.setenv("INSIGHT_ENGINE_API_KEY", "test-key")
    monkeypatch.setenv("INSIGHT_ENGINE_MODEL_NAME", "test-model")
    monkeypatch.setenv("KEYWORD_OPTIMIZER_API_KEY", "global-key")

    import InsightEngine.agent as insight_agent_module
    from InsightEngine.agent import DeepSearchAgent as InsightAgent

    created = []

    class FakeKeywordOptimizer:
        def __init__(self, **kwargs):
            created.append(kwargs)

        def optimize_keywords(self, original_query, context=""):
            return SimpleNamespace(
                original_query=original_query,
                optimized_keywords=["配置关键词"],
                reasoning=context,
                success=True,
                error_message="",
            )

    class FakeLLMClient:
        def __init__(self, **_kwargs):
            pass

        def get_model_info(self):
            return {}

    class FakeSearchAgency:
        def search_topic_globally(self, topic, limit_per_table):
            assert topic == "配置关键词"
            return SimpleNamespace(
                results=[],
                results_count=0,
                parameters={"limit_per_table": limit_per_table},
            )

    monkeypatch.setattr(insight_agent_module, "KeywordOptimizer", FakeKeywordOptimizer)
    monkeypatch.setattr(insight_agent_module, "LLMClient", FakeLLMClient)
    monkeypatch.setattr(insight_agent_module, "MediaCrawlerDB", FakeSearchAgency)

    config = SimpleNamespace(
        INSIGHT_ENGINE_API_KEY="insight-key",
        INSIGHT_ENGINE_MODEL_NAME="insight-model",
        INSIGHT_ENGINE_BASE_URL="https://example.test",
        KEYWORD_OPTIMIZER_API_KEY="instance-key",
        KEYWORD_OPTIMIZER_BASE_URL="https://keyword.example.test",
        KEYWORD_OPTIMIZER_MODEL_NAME="keyword-model",
        KEYWORD_OPTIMIZER_MAX_KEYWORDS=3,
        OUTPUT_DIR="/tmp/argus-test-insight",
        DEFAULT_SEARCH_TOPIC_GLOBALLY_LIMIT_PER_TABLE=7,
        MAX_AUTO_SENTIMENT_SEARCHES=1,
    )

    agent = InsightAgent(config)
    result = agent.execute_search_tool(
        "search_topic_globally",
        "王鹤棣 不舒服文学",
        enable_sentiment=False,
    )

    assert created == [
        {
            "api_key": "instance-key",
            "base_url": "https://keyword.example.test",
            "model_name": "keyword-model",
            "max_keywords": 3,
        }
    ]
    assert result.parameters["optimized_keywords"] == ["配置关键词"]


def test_insight_agent_filters_search_results_outside_argus_time_window(monkeypatch):
    from datetime import datetime
    from types import SimpleNamespace

    monkeypatch.setenv("INSIGHT_ENGINE_API_KEY", "test-key")
    monkeypatch.setenv("INSIGHT_ENGINE_MODEL_NAME", "test-model")
    monkeypatch.setenv("KEYWORD_OPTIMIZER_API_KEY", "test-key")

    import InsightEngine.agent as insight_agent_module
    from InsightEngine.agent import DeepSearchAgent as InsightAgent

    monkeypatch.setattr(insight_agent_module, "ENABLE_CLUSTERING", False)

    may_result = SimpleNamespace(
        title_or_content="王鹤棣在亲爱的客栈回应我当时确实不舒服",
        url="https://weibo.test/may",
        publish_time=datetime(2026, 5, 28, 12, 0),
        hotness_score=10,
        platform="weibo",
        content_type="note",
        author_nickname="u1",
        engagement={},
    )
    june_result = SimpleNamespace(
        title_or_content="王鹤棣六月新剧路透",
        url="https://weibo.test/june",
        publish_time=datetime(2026, 6, 4, 12, 0),
        hotness_score=99,
        platform="weibo",
        content_type="note",
        author_nickname="u2",
        engagement={},
    )

    agent = object.__new__(InsightAgent)
    agent.config = SimpleNamespace(
        DEFAULT_SEARCH_TOPIC_GLOBALLY_LIMIT_PER_TABLE=50,
        MAX_AUTO_SENTIMENT_SEARCHES=1,
    )
    agent._auto_sentiment_runs = 0
    agent._argus_context = "timeWindow: 2026年5月1日至2026年5月29日"
    agent.keyword_optimizer = SimpleNamespace(
        optimize_keywords=lambda **_kwargs: SimpleNamespace(
            optimized_keywords=["王鹤棣"],
            reasoning="test",
        )
    )
    agent.search_agency = SimpleNamespace(
        search_topic_globally=lambda **_kwargs: SimpleNamespace(
            results=[june_result, may_result],
            parameters={},
        )
    )

    response = agent.execute_search_tool(
        "search_topic_globally",
        "王鹤棣",
        enable_sentiment=False,
    )

    assert [result.url for result in response.results] == ["https://weibo.test/may"]


def test_query_agent_avoids_single_day_tavily_date_ranges_after_argus_clamp(monkeypatch):
    from types import SimpleNamespace

    monkeypatch.setenv("QUERY_ENGINE_API_KEY", "test-key")
    monkeypatch.setenv("QUERY_ENGINE_MODEL_NAME", "test-model")
    monkeypatch.setenv("TAVILY_API_KEY", "test-key")

    from QueryEngine.agent import DeepSearchAgent as QueryAgent

    agent = object.__new__(QueryAgent)
    agent._argus_context = "timeWindow: 2026年5月1日至2026年5月29日"
    agent.search_agency = SimpleNamespace()
    calls = []

    def basic_search_news(query, max_results=7):
        calls.append(("basic", query, max_results))
        return SimpleNamespace(results=[])

    def search_news_by_date(query, start_date, end_date):
        calls.append(("date", query, start_date, end_date))
        raise AssertionError("single-day date searches should fall back before Tavily")

    agent.search_agency.basic_search_news = basic_search_news
    agent.search_agency.search_news_by_date = search_news_by_date

    response = agent.execute_search_tool(
        "search_news_by_date",
        "王鹤棣 不舒服 文学 颁奖 节目 安排 原因",
        start_date="2026-05-29",
        end_date="2026-05-29",
    )

    assert response.results == []
    assert calls == [
        ("basic", "王鹤棣 不舒服 文学 颁奖 节目 安排 原因", 7)
    ]


def test_query_agent_rewrites_recent_search_tools_for_historical_argus_window(monkeypatch):
    from types import SimpleNamespace

    monkeypatch.setenv("QUERY_ENGINE_API_KEY", "test-key")
    monkeypatch.setenv("QUERY_ENGINE_MODEL_NAME", "test-model")
    monkeypatch.setenv("TAVILY_API_KEY", "test-key")

    from QueryEngine.agent import DeepSearchAgent as QueryAgent

    agent = object.__new__(QueryAgent)
    agent._argus_context = (
        "<ARGUS_CONTEXT_JSON>"
        '{"research_request":{"timeWindow":"2022年12月23日至2023年1月5日"}}'
        "</ARGUS_CONTEXT_JSON>"
    )
    calls = []

    def basic_search_news(query, max_results=7):
        calls.append(("basic", query, max_results))
        return SimpleNamespace(results=[])

    def search_news_last_week(query):
        calls.append(("last_week", query))
        raise AssertionError("historical Argus windows should not use recent news search")

    agent.search_agency = SimpleNamespace(
        basic_search_news=basic_search_news,
        search_news_last_week=search_news_last_week,
    )

    response = agent.execute_search_tool(
        "search_news_last_week",
        "袁娅维 成都演唱会取消",
    )

    assert response.results == []
    assert calls == [("basic", "袁娅维 成都演唱会取消", 7)]


def test_media_agent_rewrites_recent_search_tools_for_historical_argus_window(monkeypatch):
    from types import SimpleNamespace

    monkeypatch.setenv("MEDIA_ENGINE_API_KEY", "test-key")
    monkeypatch.setenv("MEDIA_ENGINE_MODEL_NAME", "test-model")
    monkeypatch.setenv("BOCHA_API_KEY", "test-key")
    monkeypatch.setenv("INSIGHT_ENGINE_API_KEY", "test-key")
    monkeypatch.setenv("INSIGHT_ENGINE_MODEL_NAME", "test-model")
    monkeypatch.setenv("QUERY_ENGINE_API_KEY", "test-key")
    monkeypatch.setenv("QUERY_ENGINE_MODEL_NAME", "test-model")
    monkeypatch.setenv("REPORT_ENGINE_API_KEY", "test-key")
    monkeypatch.setenv("FORUM_HOST_API_KEY", "test-key")
    monkeypatch.setenv("KEYWORD_OPTIMIZER_API_KEY", "test-key")
    monkeypatch.setenv("TAVILY_API_KEY", "test-key")

    from MediaEngine.agent import DeepSearchAgent as MediaAgent

    agent = object.__new__(MediaAgent)
    agent._argus_context = (
        "<ARGUS_CONTEXT_JSON>"
        '{"research_request":{"timeWindow":"2022年12月23日至2023年1月5日"}}'
        "</ARGUS_CONTEXT_JSON>"
    )
    calls = []

    def comprehensive_search(query, max_results=10):
        calls.append(("comprehensive", query, max_results))
        return SimpleNamespace(webpages=[])

    def search_last_week(query):
        calls.append(("last_week", query))
        raise AssertionError("historical Argus windows should not use recent search")

    agent.search_agency = SimpleNamespace(
        comprehensive_search=comprehensive_search,
        search_last_week=search_last_week,
    )

    response = agent.execute_search_tool(
        "search_last_week",
        "袁娅维 成都演唱会取消",
        max_results=10,
    )

    assert response.webpages == []
    assert calls == [("comprehensive", "袁娅维 成都演唱会取消", 10)]
