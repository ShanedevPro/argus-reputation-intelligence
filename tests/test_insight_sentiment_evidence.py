import os
import importlib.util
import sys
import types
from pathlib import Path

os.environ.setdefault("KEYWORD_OPTIMIZER_API_KEY", "test-key")


REPO_ROOT = Path(__file__).parents[1]


def _load_search_class():
    spec = importlib.util.spec_from_file_location(
        "insight_state_under_test",
        REPO_ROOT / "InsightEngine" / "state" / "state.py",
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.Search


def _load_agent_class(monkeypatch):
    package = types.ModuleType("InsightEngine")
    package.__path__ = [str(REPO_ROOT / "InsightEngine")]
    monkeypatch.setitem(sys.modules, "InsightEngine", package)

    llms = types.ModuleType("InsightEngine.llms")
    llms.LLMClient = object
    monkeypatch.setitem(sys.modules, "InsightEngine.llms", llms)

    nodes = types.ModuleType("InsightEngine.nodes")
    for name in (
        "FirstSearchNode",
        "FirstSummaryNode",
        "ReflectionNode",
        "ReflectionSummaryNode",
        "ReportFormattingNode",
        "ReportStructureNode",
    ):
        setattr(nodes, name, object)
    monkeypatch.setitem(sys.modules, "InsightEngine.nodes", nodes)

    state = types.ModuleType("InsightEngine.state")
    state.State = object
    monkeypatch.setitem(sys.modules, "InsightEngine.state", state)

    tools = types.ModuleType("InsightEngine.tools")
    tools.KeywordOptimizer = object
    for name in (
        "DBResponse",
        "MediaCrawlerDB",
        "keyword_optimizer",
        "multilingual_sentiment_analyzer",
    ):
        setattr(tools, name, object())
    monkeypatch.setitem(sys.modules, "InsightEngine.tools", tools)

    insight_utils = types.ModuleType("InsightEngine.utils")
    insight_utils.format_search_results_for_prompt = lambda *_args, **_kwargs: ""
    monkeypatch.setitem(sys.modules, "InsightEngine.utils", insight_utils)

    config = types.ModuleType("InsightEngine.utils.config")
    config.Settings = object
    config.settings = object()
    monkeypatch.setitem(sys.modules, "InsightEngine.utils.config", config)

    evidence_summary = types.ModuleType("utils.evidence_summary")
    evidence_summary.build_evidence_summary = lambda *_args, **_kwargs: {}
    monkeypatch.setitem(sys.modules, "utils.evidence_summary", evidence_summary)

    topic_relevance = types.ModuleType("utils.topic_relevance")
    topic_relevance.extract_topic_anchor = lambda *_args, **_kwargs: {}
    topic_relevance.filter_relevant_items = lambda items, *_args, **_kwargs: items
    topic_relevance.rewrite_query_if_drifted = lambda query, *_args, **_kwargs: query
    monkeypatch.setitem(sys.modules, "utils.topic_relevance", topic_relevance)

    spec = importlib.util.spec_from_file_location(
        "InsightEngine.agent",
        REPO_ROOT / "InsightEngine" / "agent.py",
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.DeepSearchAgent


def test_search_state_serializes_response_parameters():
    Search = _load_search_class()
    search = Search(query="王鹤棣 不舒服文学", content="样本内容")
    search.parameters = {
        "sentiment_analysis": {
            "total_analyzed": 3,
            "sentiment_distribution": {"negative": 2, "neutral": 1},
        }
    }

    restored = Search.from_dict(search.to_dict())

    assert restored.parameters["sentiment_analysis"]["total_analyzed"] == 3


def test_extract_sentiment_evidence_from_search_history(monkeypatch):
    Search = _load_search_class()
    DeepSearchAgent = _load_agent_class(monkeypatch)
    agent = object.__new__(DeepSearchAgent)
    search = Search(query="王鹤棣 不舒服文学", content="样本内容")
    search.parameters = {
        "sentiment_analysis": {
            "total_analyzed": 3,
            "sentiment_distribution": {"negative": 2, "neutral": 1},
            "summary": "主要情感倾向为 negative",
        }
    }
    paragraphs = [
        type(
            "Paragraph",
            (),
            {
                "title": "微博情绪",
                "research": type(
                    "Research",
                    (),
                    {"search_history": [search]},
                )(),
            },
        )()
    ]

    evidence = agent._extract_sentiment_evidence(paragraphs)

    assert evidence["total_analyzed"] == 3
    assert evidence["sentiment_distribution"]["negative"] == 2
    assert evidence["summary"]


def test_extract_sentiment_evidence_deduplicates_response_level_payloads(monkeypatch):
    Search = _load_search_class()
    DeepSearchAgent = _load_agent_class(monkeypatch)
    agent = object.__new__(DeepSearchAgent)
    sentiment_payload = {
        "total_analyzed": 50,
        "sentiment_distribution": {"positive": 16, "negative": 3},
        "summary": "共分析50条内容，主要情感倾向为 positive",
    }
    searches = []
    for index in range(3):
        search = Search(query="王鹤棣 不舒服文学", content=f"样本内容 {index}")
        search.parameters = {"sentiment_analysis": dict(sentiment_payload)}
        searches.append(search)

    paragraphs = [
        type(
            "Paragraph",
            (),
            {
                "title": "微博情绪",
                "research": type("Research", (), {"search_history": searches})(),
            },
        )()
    ]

    evidence = agent._extract_sentiment_evidence(paragraphs)

    assert evidence["total_analyzed"] == 50
    assert evidence["sentiment_distribution"] == {"positive": 16, "negative": 3}
