from __future__ import annotations

import asyncio
import json

from downstream.weibo_data import bundle_importer
from downstream.weibo_data.providers.base import WeiboDataCaps
from utils.weibo_data_prep import (
    build_weibo_collection_bundle,
    compile_weibo_data_task,
    derive_weibo_keywords,
    evaluate_weibo_reportability,
    normalize_weibo_request,
    rank_weibo_posts,
    select_weibo_posts_for_comment_expansion,
)


def test_weibo_keyword_derivation_prefers_event_subject_and_weibo_clue():
    caps = WeiboDataCaps(max_keywords=6)
    request = {
        "eventOrIssue": "交付争议",
        "affectedSubject": "小米SU7",
        "timeWindow": "最近三个月",
        "weiboClue": "微博话题：小米SU7交付",
        "decisionGoal": "判断是否存在舆情风险升级",
        "knownMaterials": ["用户投诉截图", "官方回应"],
    }

    keywords = derive_weibo_keywords(request, caps)

    assert keywords[0] == "小米SU7交付争议"
    assert "小米SU7" in keywords
    assert "微博" not in keywords
    assert len(keywords) <= 6


def test_weibo_keyword_derivation_prioritizes_event_without_subject():
    caps = WeiboDataCaps(max_keywords=6)
    request = {
        "eventOrIssue": "交付争议",
        "affectedSubject": "",
        "timeWindow": "最近三个月",
        "weiboClue": "微博话题：交付争议",
    }

    keywords = derive_weibo_keywords(request, caps)

    assert keywords[0] == "交付争议"
    assert "微博" not in keywords
    assert len(keywords) <= 6


def test_weibo_keyword_derivation_excludes_time_window_and_decision_goal_phrases():
    caps = WeiboDataCaps(max_keywords=6)
    request = {
        "eventOrIssue": "交付争议",
        "affectedSubject": "小米SU7",
        "timeWindow": "最近三个月",
        "decisionGoal": "判断微博舆论风险与冲突叙事",
    }

    keywords = derive_weibo_keywords(request, caps)

    assert "最近三个月" not in keywords
    assert "判断微博舆论风险与冲突叙事" not in keywords
    assert "小米SU7交付争议" in keywords
    assert "交付争议" in keywords


def test_weibo_keyword_derivation_rejects_connector_noise_from_long_event():
    caps = WeiboDataCaps(max_keywords=6)
    request = {
        "eventOrIssue": '王鹤棣在《亲爱的客栈2026》节目中因颁奖环节感到不适（谐音梗"王鹤底"及"有群没你"调侃），随后发微博回应"我当时确实不舒服"，引发"不舒服文学"出圈及广泛讨论。',
        "affectedSubject": "王鹤棣",
        "timeWindow": "2026-05-01 至 2026-05-29",
        "weiboClue": '关键词："不舒服文学"、"王鹤棣"、"我当时确实不舒服"、"亲爱的客栈"',
    }

    keywords = derive_weibo_keywords(request, caps)

    assert "及" not in keywords
    assert all(len(keyword) <= 32 for keyword in keywords)
    assert "王鹤棣 不舒服文学" in keywords
    assert "我当时确实不舒服" in keywords
    assert "亲爱的客栈" in keywords
    assert len(keywords) <= 6


def test_weibo_keyword_derivation_prefers_subject_plus_short_clues():
    caps = WeiboDataCaps(max_keywords=6)
    request = {
        "eventOrIssue": "小米汽车SU7交付延期引发车主维权争议",
        "affectedSubject": "小米汽车",
        "timeWindow": "最近三个月",
        "weiboClue": "小米SU7交付 延期 车主维权",
    }

    keywords = derive_weibo_keywords(request, caps)

    assert keywords[0] == "小米汽车 SU7交付延期"
    assert "小米SU7交付" in keywords
    assert "车主维权" in keywords
    assert "最近三个月" not in keywords
    assert len(keywords) <= 6


def test_weibo_keyword_derivation_combines_product_anchor_with_event_clues():
    caps = WeiboDataCaps(max_keywords=6)
    request = {
        "eventOrIssue": "2025年3月29日小米SU7安徽高速碰撞起火事故及关于车辆安全、事故责任、品牌回应和公众信任的微博争议",
        "affectedSubject": "小米汽车",
        "timeWindow": "2025年3月29日至2025年4月30日",
        "profileId": "enterprise_pr",
        "weiboClue": "小米SU7 安徽高速 碰撞 起火 事故 品牌回应 公众信任",
    }

    keywords = derive_weibo_keywords(request, caps)

    assert "小米SU7 碰撞起火事故" in keywords
    assert "小米SU7 事故回应" in keywords
    assert keywords.index("小米SU7 碰撞起火事故") <= 2
    assert all(len(keyword) <= 32 for keyword in keywords)
    assert len(keywords) <= 6


def test_weibo_keyword_derivation_combines_subject_with_material_clues():
    caps = WeiboDataCaps(max_keywords=6)
    request = {
        "eventOrIssue": "袁娅维2022年成都惊奇无限假期演唱会延期或取消，以及粉丝补偿、票务和沟通争议",
        "affectedSubject": "袁娅维",
        "timeWindow": "2022年12月23日至2023年1月5日",
        "weiboClue": "袁娅维、惊奇无限假期、成都演唱会、演唱会延期、演唱会取消、票务补偿",
        "knownMaterials": [
            "袁娅维",
            "惊奇无限假期",
            "成都演唱会",
            "演唱会延期",
            "演唱会取消",
            "票务补偿",
        ],
    }

    keywords = derive_weibo_keywords(request, caps)

    assert "袁娅维 演唱会取消" in keywords
    assert "袁娅维 惊奇无限假期" in keywords
    assert keywords.index("袁娅维 演唱会取消") <= 2
    assert all(len(keyword) <= 32 for keyword in keywords)
    assert len(keywords) <= 6


def test_compile_weibo_data_task_emits_tikhub_search_and_comment_config():
    caps = WeiboDataCaps()
    task = compile_weibo_data_task(
        {
            "eventOrIssue": "交付争议",
            "affectedSubject": "小米SU7",
            "timeWindow": "最近三个月",
            "weiboClue": "微博话题：小米SU7交付",
        },
        caps,
        provider="tikhub",
    )

    assert task.provider == "tikhub"
    assert task.platform == "weibo"
    assert task.search["endpoint"] == "weibo_app.fetch_search_all"
    assert task.search["pages_per_keyword"] == 3
    assert task.search["search_type"] == "1"
    assert task.comments["enabled"] is True
    assert task.comments["selected_posts"] == 12
    assert task.comments["max_comments_per_post"] == 20
    assert task.comments["max_comments_per_post_hard"] == 30
    assert task.comments["subcomments"] is False
    assert task.keywords[0] == "小米SU7交付争议"
    assert task.caps["allow_subcomments"] is False


def test_weibo_data_prep_preserves_normalized_profile_id():
    caps = WeiboDataCaps()
    request = {
        "eventOrIssue": "高速碰撞起火事故争议",
        "affectedSubject": "小米SU7",
        "timeWindow": "2025-03-29 至 2025-04-30",
        "profileId": "enterprise_pr",
    }

    normalized = normalize_weibo_request(request)
    task = compile_weibo_data_task(request, caps, provider="tikhub")
    bundle = build_weibo_collection_bundle(
        "tikhub",
        request,
        caps,
        posts=[
            {
                "content_id": "p1",
                "content": "小米SU7高速碰撞起火事故争议持续发酵",
                "source_keyword": "小米SU7 高速碰撞起火",
            }
        ],
    )

    assert normalized["profileId"] == "enterprise_pr"
    assert task.metadata["request"]["profileId"] == "enterprise_pr"
    assert bundle.metadata["task"]["metadata"]["request"]["profileId"] == "enterprise_pr"


def test_rank_weibo_posts_prefers_relevance_before_hotness():
    request = {
        "eventOrIssue": "交付争议",
        "affectedSubject": "小米SU7",
        "weiboClue": "微博话题：小米SU7交付",
    }

    posts = [
        {
            "content_id": "1",
            "title": "小米SU7交付争议持续发酵",
            "content": "围绕交付争议的讨论。",
            "author": "A",
            "publish_time": "2026-05-01 10:00:00+08:00",
            "engagement": {"like_count": 3, "comment_count": 1},
        },
        {
            "content_id": "2",
            "title": "小米SU7车主讨论",
            "content": "普通讨论贴。",
            "author": "B",
            "publish_time": "2026-05-10 10:00:00+08:00",
            "engagement": {"like_count": 999, "comment_count": 100},
        },
        {
            "content_id": "3",
            "title": "别的品牌热帖",
            "content": "无关内容。",
            "author": "C",
            "publish_time": "2026-05-11 10:00:00+08:00",
            "engagement": {"like_count": 10000, "comment_count": 500},
        },
    ]

    ranked = rank_weibo_posts(posts, request, caps=WeiboDataCaps(max_keywords=6))

    assert [item["content_id"] for item in ranked] == ["1", "2", "3"]


def test_build_weibo_collection_bundle_applies_caps_and_stop_reason():
    caps = WeiboDataCaps(
        max_keywords=6,
        max_posts_per_keyword=30,
        max_selected_posts=2,
        max_comments_per_post=1,
        max_comments_per_post_hard=2,
        allow_subcomments=False,
    )
    request = {
        "eventOrIssue": "交付争议",
        "affectedSubject": "小米SU7",
        "weiboClue": "微博话题：小米SU7交付",
    }
    posts = [
        {
            "content_id": "1",
            "title": "小米SU7交付争议",
            "content": "post-1",
            "author": "A",
            "publish_time": "2026-05-01 10:00:00+08:00",
            "engagement": {"like_count": 4, "comment_count": 3},
        },
        {
            "content_id": "2",
            "title": "小米SU7讨论",
            "content": "post-2",
            "author": "B",
            "publish_time": "2026-05-02 10:00:00+08:00",
            "engagement": {"like_count": 6, "comment_count": 2},
        },
        {
            "content_id": "3",
            "title": "别的内容",
            "content": "post-3",
            "author": "C",
            "publish_time": "2026-05-03 10:00:00+08:00",
            "engagement": {"like_count": 999, "comment_count": 999},
        },
    ]
    comments = [
        {"comment_id": "11", "note_id": "1", "content": "c1", "comment_like_count": "3"},
        {"comment_id": "12", "note_id": "1", "content": "c2", "comment_like_count": "1"},
        {"comment_id": "13", "note_id": "2", "content": "c3", "comment_like_count": "5"},
    ]

    bundle = build_weibo_collection_bundle(
        "mediacrawler",
        request,
        caps,
        posts=posts,
        comments=comments,
    )

    assert bundle.provider == "mediacrawler"
    assert bundle.keywords[0] == "小米SU7交付争议"
    assert len(bundle.posts) == 3
    assert len(bundle.comments) == 2
    assert bundle.stop_reason == "caps reached"
    assert bundle.metadata["selected_post_count"] == 2
    assert bundle.metadata["post_truncated"] is False
    assert bundle.metadata["comment_truncated"] is True


def test_collection_bundle_retains_analysis_posts_beyond_comment_expansion_cap():
    caps = WeiboDataCaps(max_keywords=2, max_posts_per_keyword=30, max_selected_posts=12)
    posts = [
        {
            "content_id": str(index),
            "content": f"小米SU7交付争议 post {index}",
            "author": f"user-{index}",
            "source_keyword": "小米SU7交付争议",
        }
        for index in range(25)
    ]

    bundle = build_weibo_collection_bundle(
        "tikhub",
        {"eventOrIssue": "交付争议", "affectedSubject": "小米SU7"},
        caps,
        posts=posts,
        comments=[],
    )

    assert len(bundle.posts) == 25
    assert bundle.metadata["selected_post_count"] == 12
    assert bundle.metadata["post_truncated"] is False


def test_collection_bundle_enforces_posts_per_keyword_cap():
    caps = WeiboDataCaps(max_keywords=2, max_posts_per_keyword=2, max_selected_posts=4)
    posts = [
        {
            "content_id": str(index),
            "content": f"小米SU7交付争议 post {index}",
            "author": f"user-{index}",
            "source_keyword": "小米SU7交付争议",
        }
        for index in range(5)
    ]

    bundle = build_weibo_collection_bundle(
        "tikhub",
        {"eventOrIssue": "交付争议", "affectedSubject": "小米SU7"},
        caps,
        posts=posts,
        comments=[],
    )

    assert len(bundle.posts) == 2
    assert bundle.metadata["post_truncated"] is True


def test_reportability_blocks_zero_and_low_data_bundles():
    caps = WeiboDataCaps()
    zero = build_weibo_collection_bundle(
        "tikhub",
        {"eventOrIssue": "交付争议"},
        caps,
    )

    zero_result = evaluate_weibo_reportability(
        zero,
        readiness={"data_ready": False},
    )

    assert zero_result.status == "insufficient_data"
    assert zero_result.stop_reason == "zero_results"
    assert zero_result.can_start_analysis is False

    low_data = build_weibo_collection_bundle(
        "tikhub",
        {"eventOrIssue": "交付争议", "affectedSubject": "小米SU7"},
        caps,
        posts=[
            {
                "content_id": "1",
                "content": "小米SU7交付争议",
                "author": "车主A",
                "source_keyword": "小米SU7交付争议",
            }
        ],
        comments=[
            {"comment_id": "c1", "note_id": "1", "content": "交付争议评论"}
        ],
    )
    low_result = evaluate_weibo_reportability(
        low_data,
        readiness={"data_ready": True},
    )

    assert low_result.status == "insufficient_data"
    assert low_result.stop_reason == "insufficient_posts"
    assert low_result.can_start_analysis is False


def test_reportability_passes_with_relevant_posts_and_comments():
    caps = WeiboDataCaps(max_selected_posts=30, max_comments_per_post=80)
    posts = [
        {
            "content_id": str(index),
            "content": f"小米SU7交付争议 post {index}",
            "author": f"user-{index % 5}",
            "source_keyword": "小米SU7交付争议" if index % 2 else "交付争议",
        }
        for index in range(25)
    ]
    comments = [
        {
            "comment_id": str(index),
            "note_id": str(index % 25),
            "content": "交付争议评论",
        }
        for index in range(90)
    ]
    bundle = build_weibo_collection_bundle(
        "tikhub",
        {"eventOrIssue": "交付争议", "affectedSubject": "小米SU7"},
        caps,
        posts=posts,
        comments=comments,
    )

    result = evaluate_weibo_reportability(
        bundle,
        readiness={"data_ready": True},
    )

    assert result.status == "reportable"
    assert result.stop_reason == "reportable"
    assert result.can_start_analysis is True
    assert result.counts["posts"] == 25
    assert result.counts["comments"] == 90


def test_reportability_accepts_realistic_tikhub_comment_volume():
    caps = WeiboDataCaps(max_selected_posts=60, max_comments_per_post=50)
    posts = [
        {
            "content_id": str(index),
            "content": f"小米SU7交付争议 post {index}",
            "author": f"user-{index % 10}",
            "source_keyword": "小米SU7交付争议" if index % 2 else "交付争议",
        }
        for index in range(68)
    ]
    comments = [
        {
            "comment_id": str(index),
            "note_id": str(index % 68),
            "content": "交付争议评论",
        }
        for index in range(53)
    ]
    bundle = build_weibo_collection_bundle(
        "tikhub",
        {"eventOrIssue": "交付争议", "affectedSubject": "小米SU7"},
        caps,
        posts=posts,
        comments=comments,
    )

    result = evaluate_weibo_reportability(
        bundle,
        readiness={"data_ready": True},
    )

    assert result.status == "reportable"
    assert result.stop_reason == "reportable"
    assert result.can_start_analysis is True


def test_reportability_accepts_broad_post_set_with_twenty_five_comments():
    caps = WeiboDataCaps(max_selected_posts=40, max_comments_per_post=50)
    posts = [
        {
            "content_id": str(index),
            "content": f"LABUBU炒价黄牛争议 post {index}",
            "author": f"user-{index % 12}",
            "source_keyword": "LABUBU炒价黄牛争议" if index % 2 else "LABUBU",
        }
        for index in range(71)
    ]
    comments = [
        {
            "comment_id": str(index),
            "note_id": str(index % 40),
            "content": "LABUBU 黄牛炒价评论",
        }
        for index in range(25)
    ]
    bundle = build_weibo_collection_bundle(
        "tikhub",
        {"eventOrIssue": "炒价黄牛争议", "affectedSubject": "LABUBU"},
        caps,
        posts=posts,
        comments=comments,
    )

    result = evaluate_weibo_reportability(
        bundle,
        readiness={"data_ready": True},
    )

    assert result.status == "reportable"
    assert result.stop_reason == "reportable"
    assert result.can_start_analysis is True


def test_reportability_allows_strong_post_sample_with_limited_comments():
    caps = WeiboDataCaps(max_selected_posts=12, max_comments_per_post=30)
    posts = [
        {
            "content_id": str(index),
            "content": f"王鹤棣 不舒服文学 post {index}",
            "author": f"user-{index % 8}",
            "source_keyword": (
                "王鹤棣 不舒服文学" if index % 3 == 0 else "亲爱的客栈"
            ),
        }
        for index in range(37)
    ]
    comments = [
        {
            "comment_id": str(index),
            "note_id": str(index % 12),
            "content": "不舒服文学 评论",
        }
        for index in range(12)
    ]
    bundle = build_weibo_collection_bundle(
        "tikhub",
        {"eventOrIssue": "不舒服文学出圈争议", "affectedSubject": "王鹤棣"},
        caps,
        posts=posts,
        comments=comments,
    )

    result = evaluate_weibo_reportability(
        bundle,
        readiness={"data_ready": True},
    )

    assert result.status == "reportable"
    assert result.stop_reason == "reportable_limited_comments"
    assert result.can_start_analysis is True
    assert result.metadata["sample_warnings"]["comment_sample_limited"] is True


def test_import_weibo_bundle_inserts_posts_and_comments(monkeypatch, tmp_path):
    class FakeConnection:
        def __init__(self):
            self.posts: list[tuple] = []
            self.comments: list[tuple] = []
            self.closed = False

        async def fetchval(self, query, *params):
            if "FROM weibo_note_comment" in query:
                return len(self.comments)
            if "FROM weibo_note" in query:
                return len(self.posts)
            return None

        async def execute(self, query, *params):
            if "INSERT INTO weibo_note_comment" in query:
                self.comments.append(params)
            elif "INSERT INTO weibo_note" in query:
                self.posts.append(params)

        async def close(self):
            self.closed = True

    fake_connection = FakeConnection()

    async def fake_connect_postgres(_dsn):
        return fake_connection

    monkeypatch.setattr(bundle_importer, "connect_postgres", fake_connect_postgres)

    bundle_path = tmp_path / "bundle.json"
    bundle_path.write_text(
        json.dumps(
            {
                "provider": "mediacrawler",
                "posts": [
                    {
                        "content_id": "1",
                        "content": "小米SU7交付争议",
                        "author": "A",
                    }
                ],
                "comments": [
                    {
                        "comment_id": "10",
                        "note_id": "1",
                        "content": "有人讨论交付争议",
                    }
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    result = asyncio.run(bundle_importer.import_weibo_bundle([bundle_path], "postgresql://example"))

    assert result["provider"] == "mediacrawler"
    assert result["counts"]["weibo_note"] == 1
    assert result["counts"]["weibo_note_comment"] == 1
    assert result["counts"]["post_inserted"] == 1
    assert result["counts"]["comment_inserted"] == 1
    assert fake_connection.closed is True
    assert len(fake_connection.posts) == 1
    assert len(fake_connection.comments) == 1
