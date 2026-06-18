import importlib.util
import sys
import types
from pathlib import Path
from types import SimpleNamespace


def test_insight_engine_imports_without_optional_clustering_dependencies(monkeypatch):
    package = types.ModuleType("InsightEngine")
    package.__path__ = [str(Path(__file__).parents[1] / "InsightEngine")]
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

    utils = types.ModuleType("InsightEngine.utils")
    utils.format_search_results_for_prompt = lambda *_args, **_kwargs: ""
    monkeypatch.setitem(sys.modules, "InsightEngine.utils", utils)

    config = types.ModuleType("InsightEngine.utils.config")
    config.Settings = object
    config.settings = object()
    monkeypatch.setitem(sys.modules, "InsightEngine.utils.config", config)

    evidence_summary = types.ModuleType("utils.evidence_summary")
    evidence_summary.build_evidence_summary = lambda *_args, **_kwargs: {}
    monkeypatch.setitem(sys.modules, "utils.evidence_summary", evidence_summary)

    topic_relevance = types.ModuleType("utils.topic_relevance")
    topic_relevance.extract_topic_anchor = lambda query: query
    topic_relevance.filter_relevant_items = lambda items, *_args, **_kwargs: items
    topic_relevance.rewrite_query_if_drifted = lambda query, *_args, **_kwargs: query
    monkeypatch.setitem(sys.modules, "utils.topic_relevance", topic_relevance)

    spec = importlib.util.spec_from_file_location(
        "InsightEngine.agent",
        Path(__file__).parents[1] / "InsightEngine" / "agent.py",
    )
    assert spec is not None
    assert spec.loader is not None
    agent_module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(agent_module)

    monkeypatch.setattr(agent_module, "np", None)
    monkeypatch.setattr(agent_module, "KMeans", None)
    monkeypatch.setattr(agent_module, "SentenceTransformer", None)

    agent = agent_module.DeepSearchAgent.__new__(agent_module.DeepSearchAgent)
    results = [
        SimpleNamespace(title_or_content="low", hotness_score=1),
        SimpleNamespace(title_or_content="high", hotness_score=10),
        SimpleNamespace(title_or_content="medium", hotness_score=5),
    ]

    sampled = agent._cluster_and_sample_results(
        results,
        max_results=2,
        results_per_cluster=1,
    )

    assert [item.title_or_content for item in sampled] == ["high", "medium"]


def test_clustering_model_loads_local_files_only(monkeypatch):
    package = types.ModuleType("InsightEngine")
    package.__path__ = [str(Path(__file__).parents[1] / "InsightEngine")]
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

    utils = types.ModuleType("InsightEngine.utils")
    utils.format_search_results_for_prompt = lambda *_args, **_kwargs: ""
    monkeypatch.setitem(sys.modules, "InsightEngine.utils", utils)

    config = types.ModuleType("InsightEngine.utils.config")
    config.Settings = object
    config.settings = object()
    monkeypatch.setitem(sys.modules, "InsightEngine.utils.config", config)

    evidence_summary = types.ModuleType("utils.evidence_summary")
    evidence_summary.build_evidence_summary = lambda *_args, **_kwargs: {}
    monkeypatch.setitem(sys.modules, "utils.evidence_summary", evidence_summary)

    topic_relevance = types.ModuleType("utils.topic_relevance")
    topic_relevance.extract_topic_anchor = lambda query: query
    topic_relevance.filter_relevant_items = lambda items, *_args, **_kwargs: items
    topic_relevance.rewrite_query_if_drifted = lambda query, *_args, **_kwargs: query
    monkeypatch.setitem(sys.modules, "utils.topic_relevance", topic_relevance)

    spec = importlib.util.spec_from_file_location(
        "InsightEngine.agent",
        Path(__file__).parents[1] / "InsightEngine" / "agent.py",
    )
    assert spec is not None
    assert spec.loader is not None
    agent_module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(agent_module)

    captured = {}

    class FakeSentenceTransformer:
        def __init__(self, model_name, **kwargs):
            captured["model_name"] = model_name
            captured["kwargs"] = kwargs

    monkeypatch.setattr(agent_module, "SentenceTransformer", FakeSentenceTransformer)

    agent = agent_module.DeepSearchAgent.__new__(agent_module.DeepSearchAgent)
    agent._clustering_model = None

    model = agent._get_clustering_model()

    assert isinstance(model, FakeSentenceTransformer)
    assert captured["kwargs"]["local_files_only"] is True
