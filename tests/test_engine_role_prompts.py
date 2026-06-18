from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def read_source(relative_path: str) -> str:
    return (ROOT / relative_path).read_text(encoding="utf-8")


def import_prompt_constant(relative_path: str, constant_name: str) -> str:
    import importlib.util

    path = ROOT / relative_path
    spec = importlib.util.spec_from_file_location(
        f"prompt_test_{relative_path.replace('/', '_')}", path
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return getattr(module, constant_name)


def test_query_engine_prompt_defines_fact_timeline_desk_role():
    source = read_source("QueryEngine/prompts/prompts.py")

    assert "Fact & Timeline Desk" in source
    assert "Confirmed facts" in source
    assert "Timeline" in source
    assert "Uncertain facts" in source
    assert "Evidence gaps" in source


def test_query_engine_prompt_requires_source_bound_confirmed_facts():
    source = read_source("QueryEngine/prompts/prompts.py")

    assert "Only place a claim in Confirmed facts when a retrieved source directly supports the full claim" in source
    assert "Every Confirmed facts bullet must include a source name or evidence marker" in source
    assert "Move unsupported numbers, dates, causal claims, or single-source rumors to Uncertain facts or Evidence gaps" in source
    assert "Use source titles or URLs instead of generic source numbers" in source
    assert "Keep out-of-window background facts out of Confirmed facts" in source
    assert "Prefer fewer confirmed bullets over unsupported detail" in source
    assert "Do not reconstruct multi-day social-media timelines unless each date and action is directly visible in retrieved source text" in source


def test_media_engine_prompt_defines_media_narrative_desk_role():
    source = read_source("MediaEngine/prompts/prompts.py")

    assert "Media & Narrative Desk" in source
    assert "信源构成" in source
    assert "叙事框架" in source
    assert "跨平台传播信号" in source


def test_media_engine_prompt_requires_source_bound_narratives():
    source = read_source("MediaEngine/prompts/prompts.py")

    assert "Every narrative frame must name the retrieved source titles or domains that support it" in source
    assert "Avoid aggregate labels like high visibility, widespread, trust crisis, or collapse unless multiple retrieved sources directly support that wording" in source
    assert "Do not include exact counts, percentages, rankings, or recall volumes unless the retrieved source text directly contains them" in source
    assert "Phrase frames as retrieved-source observations, not as market, audience, or public-opinion conclusions" in source
    assert "Avoid broad words such as many, large volume, heat, improvement, or crisis unless they are quoted or counted by retrieved sources" in source


def test_media_engine_prompt_requires_chinese_user_facing_sections():
    source = read_source("MediaEngine/prompts/prompts.py")

    assert "All user-facing section titles and summaries must be written in Chinese" in source
    assert "媒体可见性" in source
    assert "信源构成" in source
    assert "叙事框架" in source
    assert "跨平台传播信号" in source
    assert "叙事分歧" in source
    assert "证据缺口" in source


def test_query_engine_prompt_requires_chinese_user_facing_sections():
    source = read_source("QueryEngine/prompts/prompts.py")

    assert "All user-facing section titles and summaries must be written in Chinese" in source
    assert "已确认事实" in source
    assert "时间线" in source
    assert "官方 / 媒体信源" in source
    assert "不确定事实" in source
    assert "矛盾说法" in source
    assert "证据缺口" in source


def test_query_engine_user_facing_generation_prompts_require_chinese():
    for constant_name in [
        "SYSTEM_PROMPT_FIRST_SUMMARY",
        "SYSTEM_PROMPT_REFLECTION_SUMMARY",
        "SYSTEM_PROMPT_REPORT_FORMATTING",
    ]:
        prompt = import_prompt_constant("QueryEngine/prompts/prompts.py", constant_name)
        assert "All user-facing section titles and summaries must be written in Chinese" in prompt


def test_insight_engine_prompt_defines_weibo_reaction_role():
    source = read_source("InsightEngine/prompts/prompts.py")

    assert "Weibo Reaction & Risk Signals Desk" in source
    assert "within collected Weibo samples" in source
    assert "available Weibo records" in source
    assert "retrieved comments/posts" in source
    assert "does not represent all public opinion" in source


def test_insight_engine_prompt_requires_chinese_user_facing_sections():
    source = read_source("InsightEngine/prompts/prompts.py")

    assert "All user-facing section titles and summaries must be written in Chinese" in source
    assert "微博样本范围" in source
    assert "情绪与立场模式" in source
    assert "主要争议点" in source
    assert "责任归因" in source
    assert "升温 / 降温信号" in source
    assert "谣言或信息缺口信号" in source
    assert "证据缺口" in source


def test_engine_search_prompts_keep_queries_event_specific():
    for path in [
        "QueryEngine/prompts/prompts.py",
        "MediaEngine/prompts/prompts.py",
        "InsightEngine/prompts/prompts.py",
    ]:
        source = read_source(path)

        assert "Search queries must use concrete event, subject, source, or claim terms from the input context" in source
        assert "Do not use generic labels such as negative event, controversy, or risk brief as the search query" in source


def test_media_engine_user_facing_generation_prompts_require_chinese():
    for constant_name in [
        "SYSTEM_PROMPT_FIRST_SUMMARY",
        "SYSTEM_PROMPT_REFLECTION_SUMMARY",
        "SYSTEM_PROMPT_REPORT_FORMATTING",
    ]:
        prompt = import_prompt_constant("MediaEngine/prompts/prompts.py", constant_name)
        assert "All user-facing section titles and summaries must be written in Chinese" in prompt


def test_insight_engine_user_facing_generation_prompts_require_chinese():
    for constant_name in [
        "SYSTEM_PROMPT_FIRST_SUMMARY",
        "SYSTEM_PROMPT_REFLECTION_SUMMARY",
        "SYSTEM_PROMPT_REPORT_FORMATTING",
    ]:
        prompt = import_prompt_constant("InsightEngine/prompts/prompts.py", constant_name)
        assert "All user-facing section titles and summaries must be written in Chinese" in prompt


def test_insight_structure_prompt_is_planning_only_before_retrieval():
    source = read_source("InsightEngine/prompts/prompts.py")

    assert "planning only" in source
    assert "do not state findings before retrieval" in source
    assert (
        "no sample counts, percentages, representative quotes, or concrete dates before evidence"
        in source
    )
    assert "需要引用的数据类型（评论数、转发数、情感分布等）" not in source


def test_forum_engine_prompt_defines_synthesis_conflict_review_role():
    source = read_source("ForumEngine/llm_host.py")

    assert "Synthesis & Conflict Review Desk" in source
    assert "flag conflicts" in source
    assert "does not independently verify facts" in source
    assert "Questions for final brief" in source


def test_engine_prompts_use_clear_english_stage_framing():
    for path in [
        "QueryEngine/prompts/prompts.py",
        "MediaEngine/prompts/prompts.py",
        "InsightEngine/prompts/prompts.py",
    ]:
        source = read_source(path)

        assert "Stage goal:" in source
        assert "Evidence rule:" in source
        assert "Desk boundary:" in source
        assert "Return only the JSON object" in source
        assert "你的任务不是" not in source
        assert "不负责撰写完整" not in source


def test_query_and_media_prompts_avoid_broad_report_pressure():
    for path in [
        "QueryEngine/prompts/prompts.py",
        "MediaEngine/prompts/prompts.py",
    ]:
        source = read_source(path)

        assert "This is a planning stage" in source
        assert "final risk level" in source
        assert "response advice" in source
        assert "风险等级" not in source
        assert "应对建议" not in source
        assert "撰写标准" not in source
        assert "分析深度要求" not in source


def test_insight_prompts_require_sample_supported_metrics():
    source = read_source("InsightEngine/prompts/prompts.py")

    assert "Use counts, engagement metrics, quotes, dates, and sentiment percentages only when they appear in the retrieved data" in source
    assert "Never infer all-public opinion from collected samples" in source
    assert "The goal is not to represent all public opinion" in source
    assert "代表性用户" not in source
    assert "情感分布比例" not in source
    assert "新增具体数据" not in source
