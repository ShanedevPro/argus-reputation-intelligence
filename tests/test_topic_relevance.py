def test_relevant_insight_result_matches_anchor_topic():
    from utils.topic_relevance import assess_topic_relevance

    result = assess_topic_relevance(
        topic_query="清华大学苏世民书院",
        text="清华大学苏世民书院发布项目介绍，说明学院培养目标与课程安排。",
    )

    assert result["relevance_status"] == "relevant"
    assert "苏世民书院" in result["relevance_reason"]


def test_unrelated_insight_result_is_rejected():
    from utils.topic_relevance import assess_topic_relevance

    result = assess_topic_relevance(
        topic_query="清华大学苏世民书院",
        text="马士基败诉：中转港超期用箱费谁来买单？",
    )

    assert result["relevance_status"] == "irrelevant"


def test_drifted_insight_query_is_rewritten_to_original_topic():
    from utils.topic_relevance import rewrite_query_if_drifted

    rewritten, changed = rewrite_query_if_drifted(
        generated_query="中远海运 怎么了 出事了",
        original_query="清华大学苏世民书院",
        paragraph_title="背景与事件概述",
    )

    assert changed is True
    assert rewritten == "清华大学苏世民书院 背景与事件概述"


def test_drifted_query_uses_argus_search_anchor_not_full_engine_brief():
    from utils.research_brief_builder import build_common_research_context, build_engine_brief
    from utils.topic_relevance import extract_topic_anchor, rewrite_query_if_drifted

    context = build_common_research_context(
        query="王鹤棣 不舒服文学 2026年5月",
        research_request={
            "eventOrIssue": "王鹤棣在亲爱的客栈2026颁奖环节感到不适并回应我当时确实不舒服",
            "affectedSubject": "王鹤棣",
            "timeWindow": "2026年5月1日至2026年5月29日",
            "profileId": "artist_management",
        },
        evidence_manifest={
            "counts": {"posts": 29, "comments": 69},
            "sample_boundary": {"platform": "weibo"},
            "keywords": ["亲爱的客栈2026", "不舒服文学"],
        },
        data_prep_task_id="crawl_1",
    )
    brief = build_engine_brief("query", context)

    assert extract_topic_anchor(brief) == "王鹤棣 亲爱的客栈2026 不舒服文学"

    rewritten, changed = rewrite_query_if_drifted(
        generated_query="Mango TV edits deletions Wang Hedi Wu Zelin award ceremony",
        original_query=brief,
        paragraph_title="Uncertain Facts",
    )

    assert changed is True
    assert rewritten == "王鹤棣 亲爱的客栈2026 不舒服文学 Uncertain Facts"
    assert "ARGUS_CONTEXT_JSON" not in rewritten
    assert "data_prep_task_id" not in rewritten


def test_event_risk_query_matches_product_anchor_not_generic_delivery():
    from utils.topic_relevance import assess_topic_relevance

    relevant = assess_topic_relevance(
        topic_query="分析小米SU7交付争议最近三个月微博舆情风险",
        text="博主质疑小米SU7排单延期，小米高管回应交付中心变更。",
    )
    unrelated = assess_topic_relevance(
        topic_query="分析小米SU7交付争议最近三个月微博舆情风险",
        text="理想i6因核心零部件产能准备不足导致订单延迟交付。",
    )

    assert relevant["relevance_status"] == "relevant"
    assert "小米su7" in relevant["relevance_reason"]
    assert unrelated["relevance_status"] == "irrelevant"


def test_artist_event_relevance_requires_specific_anchor_not_generic_concert_terms():
    from utils.topic_relevance import assess_topic_relevance

    topic = "袁娅维 2022年成都惊奇无限假期演唱会延期或取消 袁娅维 演唱会取消 袁娅维 惊奇无限假期"

    unrelated = assess_topic_relevance(
        topic_query=topic,
        text="补偿方案公布！歌手周深正在治疗休养！工作室就演唱会取消再次道歉",
    )
    subject_relevant = assess_topic_relevance(
        topic_query=topic,
        text="袁娅维再次就成都演出取消道歉，将全额补偿歌迷交通住宿费。",
    )
    event_title_relevant = assess_topic_relevance(
        topic_query=topic,
        text="关于惊奇无限假期成都站延期及补偿安排的公告。",
    )

    assert unrelated["relevance_status"] == "irrelevant"
    assert subject_relevant["relevance_status"] == "relevant"
    assert event_title_relevant["relevance_status"] == "relevant"


def test_artist_event_relevance_rejects_subject_only_fan_or_promo_posts():
    from utils.topic_relevance import assess_topic_relevance

    topic = "王鹤棣 亲爱的客栈2026 我当时确实不舒服 不舒服文学"

    unrelated = assess_topic_relevance(
        topic_query=topic,
        text="王鹤棣高德地图代言人，跟着扫街榜打卡新加坡取景地。",
    )
    event_relevant = assess_topic_relevance(
        topic_query=topic,
        text="网友讨论王鹤棣在亲爱的客栈2026回应：我当时确实不舒服。",
    )
    subject_event_relevant = assess_topic_relevance(
        topic_query=topic,
        text="这里王鹤棣明显不舒服了，亲爱的客栈这段颁奖引发争议。",
    )

    assert unrelated["relevance_status"] == "irrelevant"
    assert event_relevant["relevance_status"] == "relevant"
    assert subject_event_relevant["relevance_status"] == "relevant"


def test_artist_event_relevance_rejects_context_only_program_discussion():
    from utils.topic_relevance import assess_topic_relevance

    topic = "王鹤棣 亲爱的客栈2026 我当时确实不舒服 不舒服文学"

    program_only = assess_topic_relevance(
        topic_query=topic,
        text="看亲爱的客栈就开始喜欢阚清子了，今天偶然搜一下才发现原来早就关注她了。",
    )
    subject_context = assess_topic_relevance(
        topic_query=topic,
        text="亲爱的客栈官微下面有用户要求给王鹤棣道歉，认为节目处理不公。",
    )
    event_phrase = assess_topic_relevance(
        topic_query=topic,
        text="不舒服文学继续发酵，有网友回看王鹤棣在节目里的回应。",
    )

    assert program_only["relevance_status"] == "irrelevant"
    assert subject_context["relevance_status"] == "relevant"
    assert event_phrase["relevance_status"] == "relevant"


def test_artist_event_relevance_rejects_meme_derivatives_without_origin_anchor():
    from utils.topic_relevance import assess_topic_relevance

    topic = "王鹤棣 亲爱的客栈2026 我当时确实不舒服 不舒服文学"

    derivative = assess_topic_relevance(
        topic_query=topic,
        text="范丞丞超话里也开始玩不舒服文学，主打一个随性舒服就靠近。",
    )
    origin_subject = assess_topic_relevance(
        topic_query=topic,
        text="王鹤棣在凌晨两点发微博称我当时确实不舒服，不舒服文学由此出圈。",
    )
    origin_context = assess_topic_relevance(
        topic_query=topic,
        text="亲爱的客栈收官风波后，不舒服文学继续被讨论。",
    )

    assert derivative["relevance_status"] == "irrelevant"
    assert origin_subject["relevance_status"] == "relevant"
    assert origin_context["relevance_status"] == "relevant"


def test_long_confirmed_event_sentence_exposes_short_event_anchors():
    from utils.topic_relevance import assess_topic_relevance, build_topic_terms

    topic = (
        "王鹤棣 王鹤棣在亲爱的客栈2026颁奖环节感到不适并回应"
        "我当时确实不舒服，引发不舒服文学。"
    )

    terms = build_topic_terms(topic)
    event_relevant = assess_topic_relevance(
        topic_query=topic,
        text="王鹤棣回应我当时确实不舒服，不舒服文学继续发酵。",
    )
    subject_only = assess_topic_relevance(
        topic_query=topic,
        text="王鹤棣高德地图代言人，跟着扫街榜打卡新加坡取景地。",
    )

    assert "我当时确实不舒服" in terms
    assert "不舒服文学" in terms
    assert event_relevant["relevance_status"] == "relevant"
    assert subject_only["relevance_status"] == "irrelevant"


def test_argus_brief_anchor_uses_event_keywords_not_full_sentence_only():
    from utils.research_brief_builder import build_common_research_context, build_engine_brief
    from utils.topic_relevance import assess_topic_relevance, extract_topic_anchor

    context = build_common_research_context(
        query="王鹤棣在亲爱的客栈2026中因颁奖环节感到不适随后发微博回应我当时确实不舒服引发不舒服文学出圈",
        research_request={
            "eventOrIssue": "王鹤棣在《亲爱的客栈2026》中因颁奖环节感到不适并发微博回应‘我当时确实不舒服’，引发‘不舒服文学’出圈",
            "affectedSubject": "王鹤棣",
            "timeWindow": "2026年5月1日至2026年5月29日",
            "profileId": "artist_management",
        },
        evidence_manifest={
            "counts": {"posts": 43, "comments": 12},
            "sample_boundary": {"platform": "weibo"},
            "keywords": ["亲爱的客栈2026", "我当时确实不舒服", "不舒服文学"],
        },
        data_prep_task_id="crawl_1",
    )
    brief = build_engine_brief("insight", context)
    anchor = extract_topic_anchor(brief)

    assert anchor == "王鹤棣 亲爱的客栈2026 我当时确实不舒服 不舒服文学"
    assert assess_topic_relevance(anchor, "网友讨论王鹤棣回应：我当时确实不舒服")[
        "relevance_status"
    ] == "relevant"


def test_argus_brief_exposes_confirmed_time_window_for_engine_tools():
    from utils.argus_engine_context import extract_argus_time_window
    from utils.research_brief_builder import build_common_research_context, build_engine_brief

    context = build_common_research_context(
        query="王鹤棣 不舒服文学",
        research_request={
            "eventOrIssue": "不舒服文学",
            "affectedSubject": "王鹤棣",
            "timeWindow": "2026年5月1日至2026年5月29日",
            "profileId": "artist_management",
        },
        evidence_manifest={
            "counts": {"posts": 43, "comments": 12},
            "keywords": ["亲爱的客栈2026", "不舒服文学"],
        },
    )
    brief = build_engine_brief("insight", context)

    assert extract_argus_time_window(brief) == ("2026-05-01", "2026-05-29")


def test_argus_time_window_clamps_generated_date_ranges():
    from utils.argus_engine_context import clamp_date_range_to_argus_window

    assert clamp_date_range_to_argus_window(
        "2026-06-04",
        "2026-06-05",
        "timeWindow: 2026年5月1日至2026年5月29日",
    ) == ("2026-05-01", "2026-05-29", True)
    assert clamp_date_range_to_argus_window(
        "2026-05-10",
        "2026-05-20",
        "timeWindow: 2026-05-01 至 2026-05-29",
    ) == ("2026-05-10", "2026-05-20", False)


def test_query_and_media_agents_use_topic_relevance_guardrails():
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    for relative_path in ["QueryEngine/agent.py", "MediaEngine/agent.py", "InsightEngine/agent.py"]:
        source = (root / relative_path).read_text(encoding="utf-8")
        assert "rewrite_query_if_drifted" in source
        assert "filter_relevant_items" in source
        assert "extract_topic_anchor" in source
        assert "self._argus_context" in source
        assert "_anchor_search_query" in source
        assert "_filter_topic_relevant_results" in source
        assert "topic_query=self._topic_anchor()" in source


def test_date_search_agents_clamp_to_argus_time_window():
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    for relative_path in ["QueryEngine/agent.py", "InsightEngine/agent.py"]:
        source = (root / relative_path).read_text(encoding="utf-8")
        assert "clamp_date_range_to_argus_window" in source
        assert "_clamp_search_date_range" in source
