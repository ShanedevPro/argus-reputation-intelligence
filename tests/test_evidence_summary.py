from pathlib import Path


def test_evidence_summary_round_trip(tmp_path):
    from utils.evidence_summary import load_evidence_summary, write_evidence_summary

    report_path = tmp_path / "report_demo.md"
    report_path.write_text("# demo", encoding="utf-8")

    sidecar = write_evidence_summary(
        report_path=report_path,
        engine_name="insight",
        query="清华大学苏世民书院",
        evidence_status="ready",
        source_count=2,
        evidence_items=[{"title": "source A", "url": "https://example.com/a"}],
    )

    loaded = load_evidence_summary(sidecar)
    assert loaded["engine_name"] == "insight"
    assert loaded["evidence_status"] == "ready"
    assert loaded["source_count"] == 2


def test_evidence_summary_carries_traceable_snippets():
    from utils.evidence_summary import summarize_evidence_from_paragraphs

    paragraphs = [
        {
            "title": "学院背景",
            "research": {
                "search_history": [
                    {
                        "title": "清华大学苏世民书院简介",
                        "url": "https://example.com/schwarzman",
                        "content": "清华大学苏世民书院位于清华大学，项目为全球领导力教育项目。",
                        "query": "清华大学苏世民书院",
                    }
                ]
            },
        }
    ]

    status, source_count, items = summarize_evidence_from_paragraphs(paragraphs)

    assert status == "ready"
    assert source_count == 1
    assert items[0]["evidence_id"] == "E1"
    assert items[0]["source_title"] == "清华大学苏世民书院简介"
    assert items[0]["source_url"] == "https://example.com/schwarzman"
    assert "全球领导力教育项目" in items[0]["snippet"]


def test_insight_evidence_summary_counts_only_topic_relevant_sources():
    from utils.evidence_summary import summarize_evidence_from_paragraphs

    paragraphs = [
        {
            "title": "事件背景",
            "research": {
                "search_history": [
                    {
                        "title": "清华大学苏世民书院简介",
                        "url": "https://example.com/schwarzman",
                        "content": "清华大学苏世民书院位于清华大学。",
                        "query": "清华大学苏世民书院 事件背景",
                    },
                    {
                        "title": "马士基败诉：中转港超期用箱费谁来买单？",
                        "url": "https://example.com/shipping",
                        "content": "航运合同纠纷与教育项目无关。",
                        "query": "中远海运 怎么了 出事了",
                    },
                ]
            },
        }
    ]

    status, source_count, items = summarize_evidence_from_paragraphs(
        paragraphs,
        topic_query="清华大学苏世民书院",
    )

    assert status == "ready"
    assert source_count == 1
    assert items[0]["source_title"] == "清华大学苏世民书院简介"
    assert items[0]["relevance_status"] == "relevant"
    assert "苏世民书院" in items[0]["relevance_reason"]


def test_insight_evidence_summary_marks_no_data_when_all_sources_are_irrelevant():
    from utils.evidence_summary import summarize_evidence_from_paragraphs

    paragraphs = [
        {
            "title": "事件背景",
            "research": {
                "search_history": [
                    {
                        "title": "马士基败诉：中转港超期用箱费谁来买单？",
                        "url": "https://example.com/shipping",
                        "content": "航运合同纠纷与港口用箱费争议。",
                        "query": "中远海运 怎么了 出事了",
                    }
                ]
            },
        }
    ]

    status, source_count, items = summarize_evidence_from_paragraphs(
        paragraphs,
        topic_query="清华大学苏世民书院",
    )

    assert status == "no_data"
    assert source_count == 0
    assert items == []


def test_evidence_summary_filters_event_risk_query_by_product_anchor():
    from utils.evidence_summary import summarize_evidence_from_paragraphs

    paragraphs = [
        {
            "title": "关键时间线",
            "research": {
                "search_history": [
                    {
                        "title": "小米SU7排单延期争议",
                        "url": "https://example.com/xiaomi-su7",
                        "content": "博主质疑小米SU7排单延期，小米高管回应交付中心变更。",
                    },
                    {
                        "title": "理想i6延迟交付",
                        "url": "https://example.com/li-auto",
                        "content": "理想i6因核心零部件产能准备不足导致订单延迟交付。",
                    },
                ]
            },
        }
    ]

    status, source_count, items = summarize_evidence_from_paragraphs(
        paragraphs,
        topic_query="分析小米SU7交付争议最近三个月微博舆情风险",
    )

    assert status == "ready"
    assert source_count == 1
    assert items[0]["source_title"] == "小米SU7排单延期争议"


def test_evidence_summary_keeps_enough_items_for_traceability_by_default():
    from utils.evidence_summary import summarize_evidence_from_paragraphs

    paragraphs = [
        {
            "title": "证据追溯材料",
            "research": {
                "search_history": [
                    {
                        "title": f"小米SU7交付争议来源{i}",
                        "url": f"https://example.com/{i}",
                        "content": f"小米SU7交付争议证据片段{i}",
                    }
                    for i in range(75)
                ]
            },
        }
    ]

    status, source_count, items = summarize_evidence_from_paragraphs(
        paragraphs,
        topic_query="分析小米SU7交付争议最近三个月微博舆情风险",
    )

    assert status == "ready"
    assert source_count == 75
    assert len(items) == 75


def test_evidence_summary_keeps_long_enough_snippet_for_late_claim_support():
    from utils.evidence_summary import summarize_evidence_from_paragraphs

    late_support = "风云XTony发布微博称被小米骗了定金，并预约其他品牌试驾。"
    paragraphs = [
        {
            "title": "证据追溯材料",
            "research": {
                "search_history": [
                    {
                        "title": "雷军天要塌了，小米主管报警抓SU7 Ultra车主",
                        "url": "https://example.com/xiaomi-su7",
                        "content": "小米SU7交付争议。" + ("背景材料。" * 120) + late_support,
                    }
                ]
            },
        }
    ]

    status, source_count, items = summarize_evidence_from_paragraphs(
        paragraphs,
        topic_query="分析小米SU7交付争议最近三个月微博舆情风险",
    )

    assert status == "ready"
    assert source_count == 1
    assert late_support in items[0]["snippet"]
