from utils.research_brief_builder import (
    build_common_research_context,
    build_engine_brief,
)


def test_common_context_preserves_manifest_and_request():
    manifest = {
        "research_request": {
            "eventOrIssue": "亲爱的客栈2026 不舒服文学",
            "affectedSubject": "王鹤棣",
            "timeWindow": "2026-05-01 至 2026-05-29",
        },
        "sample_boundary": {"platform": "weibo", "comment_depth": "first_level_only"},
        "counts": {"posts": 29, "comments": 115, "authors": 29, "keywords": 4},
        "keywords": ["王鹤棣 不舒服文学"],
        "key_posts": [{"content": "王鹤棣回应不舒服"}],
        "key_comments": [{"content": "玩笑不合适"}],
    }

    context = build_common_research_context(
        query="王鹤棣 不舒服文学 2026-05",
        research_request=manifest["research_request"],
        evidence_manifest=manifest,
        data_prep_task_id="crawl_1",
    )

    assert context["query"] == "王鹤棣 不舒服文学 2026-05"
    assert context["data_prep_task_id"] == "crawl_1"
    assert context["research_request"]["affectedSubject"] == "王鹤棣"
    assert context["evidence_manifest"]["counts"]["comments"] == 115


def test_engine_briefs_are_role_specific_and_sample_bound():
    context = build_common_research_context(
        query="王鹤棣 不舒服文学 2026-05",
        research_request={
            "eventOrIssue": "亲爱的客栈2026 不舒服文学",
            "affectedSubject": "王鹤棣",
            "timeWindow": "2026-05-01 至 2026-05-29",
        },
        evidence_manifest={
            "sample_boundary": {
                "platform": "weibo",
                "comment_depth": "first_level_only",
            },
            "counts": {"posts": 29, "comments": 115},
            "keywords": ["王鹤棣 不舒服文学"],
        },
    )

    query_brief = build_engine_brief("query", context)
    media_brief = build_engine_brief("media", context)
    insight_brief = build_engine_brief("insight", context)

    assert "事实核验员" in query_brief
    assert "传播观察员" in media_brief
    assert "舆情洞察员" in insight_brief
    assert "Fact & Timeline Desk" not in query_brief
    assert "Media & Narrative Desk" not in media_brief
    assert "Weibo Reaction & Risk Signals Desk" not in insight_brief
    assert "微博一级评论" in insight_brief
    assert "帖子 29 条、微博一级评论 115 条" in insight_brief
    assert "仅代表本次采集到的微博样本，不代表全网或全部公众意见" in insight_brief
    assert "first_level_only" not in insight_brief
    assert "This sample does not represent" not in insight_brief
    assert "weibo_evidence_manifest" not in insight_brief
    assert "Do not claim to represent all public opinion" in insight_brief


def test_engine_brief_adds_artist_management_profile_lens():
    context = build_common_research_context(
        query="袁娅维 成都演唱会延期 2022",
        research_request={
            "eventOrIssue": "惊奇无限假期成都站延期与补偿争议",
            "affectedSubject": "袁娅维",
            "timeWindow": "2022-10 至 2022-12",
            "profileId": "artist_management",
        },
        evidence_manifest={"counts": {"posts": 21, "comments": 91}},
    )

    brief = build_engine_brief("media", context)

    assert '"profileId": "artist_management"' in brief
    assert "艺人经纪、工作室和公关团队" in brief
    assert "粉丝关系" in brief


def test_engine_brief_adds_industry_neutral_enterprise_profile_lens():
    context = build_common_research_context(
        query="小米SU7 高速碰撞起火事故",
        research_request={
            "eventOrIssue": "高速碰撞起火事故争议",
            "affectedSubject": "小米SU7",
            "timeWindow": "2025-03-29 至 2025-04-30",
            "profileId": "enterprise_pr",
        },
        evidence_manifest={"counts": {"posts": 68, "comments": 53}},
    )

    brief = build_engine_brief("insight", context)

    assert '"profileId": "enterprise_pr"' in brief
    assert "企业公关、品牌、客服、法务和管理层" in brief
    assert "车主" not in brief


def test_report_structure_context_wraps_argus_context_without_replacing_clean_query():
    from utils.argus_engine_context import build_report_structure_input

    message = build_report_structure_input(
        "王鹤棣 不舒服文学",
        "Profile lens: 艺人明星舆情。\n<ARGUS_CONTEXT_JSON>{}</ARGUS_CONTEXT_JSON>",
    )

    assert message.startswith("王鹤棣 不舒服文学\n\n")
    assert "<ARGUS_ENGINE_CONTEXT>" in message
    assert "Profile lens: 艺人明星舆情" in message
