from ReportEngine.agent import ReportAgent
from ReportEngine.core import DocumentComposer


def _agent_for_context_tests():
    agent = object.__new__(ReportAgent)
    agent.config = type("Config", (), {"MAX_CONTENT_LENGTH": 500000})()
    agent._stringify = lambda value: value if isinstance(value, str) else str(value)
    agent._default_theme_tokens = lambda: {"accent": "#155e8a"}
    return agent


def test_build_generation_context_preserves_data_bundles():
    agent = _agent_for_context_tests()

    context = agent._build_generation_context(
        "王鹤棣 不舒服文学",
        {"query_engine": "facts", "media_engine": "media", "insight_engine": "insight"},
        "forum",
        {"template_name": "template"},
        {"title": "title"},
        {},
        {},
        {},
        data_bundles=[{"type": "weibo_evidence_manifest", "counts": {"posts": 29}}],
    )

    assert context["data_bundles"][0]["type"] == "weibo_evidence_manifest"
    assert context["data_bundles"][0]["counts"]["posts"] == 29


def test_required_weibo_evidence_chapters_enter_document_ir():
    agent = object.__new__(ReportAgent)
    existing_chapters = [
        {
            "chapterId": "S1",
            "title": "核心发现",
            "order": 10,
            "blocks": [
                {"type": "heading", "level": 2, "text": "核心发现", "anchor": "core"}
            ],
        }
    ]
    manifest = {
        "type": "weibo_evidence_manifest",
        "provider": "tikhub",
        "sample_boundary": {
            "platform": "weibo",
            "comment_depth": "first_level_only",
            "represents": "collected_weibo_sample_only",
            "warning": "This sample does not represent all public opinion.",
        },
        "counts": {"posts": 29, "comments": 115, "authors": 20, "keywords": 4},
        "keywords": ["王鹤棣 不舒服文学", "我当时确实不舒服"],
        "key_posts": [
            {
                "source_id": "p1",
                "source_url": "https://weibo.com/p1",
                "content": "王鹤棣回应我当时确实不舒服",
                "author_name": "娱乐观察",
                "created_at": "2026-05-23 10:00:00",
                "engagement": {"like_count": 1200, "comment_count": 90},
                "evidence_kind": "weibo_post",
            }
        ],
        "key_comments": [
            {
                "source_id": "c1",
                "parent_source_id": "p1",
                "content": "节目组这个玩笑不合适",
                "author_name": "用户A",
                "created_at": "2026-05-23 11:00:00",
                "engagement": {"like_count": 15},
                "evidence_kind": "weibo_comment",
            }
        ],
    }

    chapters = agent._ensure_required_evidence_chapters(
        existing_chapters,
        data_bundles=[manifest],
    )
    document_ir = DocumentComposer().build_document(
        "report-1",
        {"title": "王鹤棣 不舒服文学"},
        chapters,
    )

    titles = [chapter["title"] for chapter in document_ir["chapters"]]
    assert "数据来源与样本说明" in titles
    assert "关键证据表" in titles
    evidence_chapter = next(
        chapter for chapter in document_ir["chapters"] if chapter["title"] == "关键证据表"
    )
    assert any(block.get("type") == "table" for block in evidence_chapter["blocks"])
    assert "王鹤棣回应我当时确实不舒服" in str(evidence_chapter)


def test_required_weibo_evidence_chapters_are_customer_facing_and_include_sentiment():
    agent = object.__new__(ReportAgent)
    manifest = {
        "type": "weibo_evidence_manifest",
        "provider": "tikhub",
        "research_request": {
            "eventOrIssue": "亲爱的客栈2026 不舒服文学",
            "affectedSubject": "王鹤棣",
            "timeWindow": "2026-05-01 至 2026-05-29",
        },
        "sample_boundary": {
            "platform": "weibo",
            "comment_depth": "first_level_only",
            "represents": "collected_weibo_sample_only",
            "warning": "This sample does not represent all public opinion.",
        },
        "counts": {"posts": 50, "comments": 95, "authors": 132, "keywords": 6},
        "keywords": ["王鹤棣 不舒服文学", "我当时确实不舒服"],
        "key_posts": [
            {
                "source_id": "5304763157578196",
                "source_url": "sinaweibo://detail/?mblogid=5304763157578196&id=5304763157578196",
                "content": "王鹤棣发文称在颁奖环节感到不适，沈月随后道歉解释。",
                "author_name": "烟竹阮桐粥",
                "created_at": "2026-05-31 14:25:56",
                "engagement": {"like_count": 51, "comment_count": 13},
            }
        ],
        "sentiment_analysis": {
            "total_analyzed": 853,
            "sentiment_distribution": {
                "非常负面": 255,
                "负面": 137,
                "中性": 199,
                "正面": 80,
                "非常正面": 182,
            },
        },
    }

    chapters = agent._ensure_required_evidence_chapters([], data_bundles=[manifest])
    rendered = str(chapters)
    titles = [chapter["title"] for chapter in chapters]

    assert "数据来源与样本说明" in titles
    assert "关键证据表" in titles
    assert "情绪分布与样本说明" in titles
    assert "2026-05-01 至 2026-05-29" in rendered
    assert "仅代表本次采集到的微博样本，不代表全网或全部公众意见" in rendered
    assert "总计分析 853 条文本" in rendered
    assert "非常负面：255" in rendered
    assert "微博ID: 5304763157578196" in rendered
    assert "sinaweibo://" not in rendered
    assert "platform=weibo" not in rendered
    assert "comment_depth" not in rendered
    assert "dataBundles" not in rendered
    assert "This sample does not represent" not in rendered


def test_required_evidence_chapters_include_profile_framing():
    agent = object.__new__(ReportAgent)
    manifest = {
        "type": "weibo_evidence_manifest",
        "provider": "tikhub",
        "research_request": {
            "eventOrIssue": "高速碰撞起火事故争议",
            "affectedSubject": "小米SU7",
            "timeWindow": "2025-03-29 至 2025-04-30",
            "profileId": "enterprise_pr",
        },
        "counts": {"posts": 68, "comments": 53, "authors": 42, "keywords": 5},
        "keywords": ["小米SU7 高速碰撞起火"],
        "key_posts": [],
        "key_comments": [],
    }

    chapters = agent._ensure_required_evidence_chapters([], data_bundles=[manifest])
    rendered = str(chapters)

    assert "分析画像：企业公关舆情" in rendered
    assert "企业公关、品牌、客服、法务和管理层" in rendered
    assert "车主" not in rendered
