from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def read_prompt_source(relative_path: str) -> str:
    return (ROOT / relative_path).read_text(encoding="utf-8")


def test_engine_summary_prompts_allow_insufficient_evidence():
    sources = [
        read_prompt_source("InsightEngine/prompts/prompts.py"),
        read_prompt_source("MediaEngine/prompts/prompts.py"),
        read_prompt_source("QueryEngine/prompts/prompts.py"),
    ]

    for source in sources:
        assert "insufficient" in source.lower()
        assert "evidence gap" in source.lower() or "evidence gaps" in source.lower()


def test_report_engine_prompts_keep_uncertainty_explicit():
    source = read_prompt_source("ReportEngine/prompts/prompts.py")

    assert "信息不足" in source
    assert "保留不确定" in source
    assert "不得臆造" in source
