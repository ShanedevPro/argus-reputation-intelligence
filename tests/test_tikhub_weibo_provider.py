from __future__ import annotations

import builtins

import pytest

from downstream.weibo_data.providers.base import WeiboDataCaps
from downstream.weibo_data.providers.tikhub import (
    TikHubProviderSetupError,
    TikHubWeiboProvider,
)


class FakeWeiboWeb:
    def __init__(
        self,
        *,
        search_cards=None,
        comment_items=None,
        search_error: Exception | None = None,
        comment_error: Exception | None = None,
    ):
        self.search_cards = list(search_cards or [])
        self.comment_items = list(comment_items or [])
        self.search_error = search_error
        self.comment_error = comment_error
        self.search_calls: list[dict] = []
        self.comment_calls: list[dict] = []

    def fetch_search(self, *, keyword, page, search_type=None, time_scope=None):
        self.search_calls.append(
            {
                "keyword": keyword,
                "page": page,
                "search_type": search_type,
                "time_scope": time_scope,
            }
        )
        if self.search_error:
            raise self.search_error
        return {"data": {"data": {"cards": self.search_cards}}}

    def fetch_post_comments(self, *, post_id, mid, max_id=None, max_id_type=None):
        self.comment_calls.append(
            {
                "post_id": post_id,
                "mid": mid,
                "max_id": max_id,
                "max_id_type": max_id_type,
            }
        )
        if self.comment_error:
            raise self.comment_error
        return {"data": {"data": {"data": self.comment_items}}}


class FakeWeiboApp:
    def __init__(
        self,
        *,
        search_cards=None,
        search_items=None,
        search_error: Exception | None = None,
    ):
        self.search_cards = list(search_cards or [])
        self.search_items = list(search_items or [])
        self.search_error = search_error
        self.search_calls: list[dict] = []

    def fetch_search_all(self, *, query, page, search_type=None):
        self.search_calls.append(
            {
                "query": query,
                "page": page,
                "search_type": search_type,
            }
        )
        if self.search_error:
            raise self.search_error
        payload = {}
        if self.search_cards:
            payload["cards"] = self.search_cards
        if self.search_items:
            payload["items"] = self.search_items
        return {"data": payload}


class FakeTikHubClient:
    def __init__(self, weibo_web: FakeWeiboWeb, weibo_app: FakeWeiboApp | None = None):
        self.weibo_web = weibo_web
        if weibo_app is not None:
            self.weibo_app = weibo_app


def _mblog(
    post_id: str,
    text: str,
    *,
    comments_count: int = 3,
    created_at: str = "Fri May 01 10:00:00 +0800 2026",
) -> dict:
    return {
        "mblog": {
            "id": post_id,
            "mid": post_id,
            "mblogid": f"bid-{post_id}",
            "text": text,
            "created_at": created_at,
            "comments_count": comments_count,
            "attitudes_count": 2,
            "reposts_count": 1,
            "user": {
                "id": "u1",
                "screen_name": "车主A",
                "profile_image_url": "https://example.com/avatar.jpg",
            },
        },
        "scheme": f"https://m.weibo.cn/status/{post_id}",
    }


def test_tikhub_provider_collects_search_posts_and_first_level_comments():
    weibo_web = FakeWeiboWeb(
        search_cards=[
            _mblog("100", "小米SU7交付争议"),
            _mblog("100", "小米SU7交付争议"),
        ],
        comment_items=[
            {
                "id": "c1",
                "text": "评论交付争议",
                "created_at": "Fri May 01 11:00:00 +0800 2026",
                "like_count": 5,
                "user": {"id": "cu1", "screen_name": "评论者"},
            }
        ],
    )
    provider = TikHubWeiboProvider(
        api_key="sk-test",
        client_factory=lambda **_kwargs: FakeTikHubClient(weibo_web),
    )

    bundle = provider.collect(
        {
            "eventOrIssue": "交付争议",
            "affectedSubject": "小米SU7",
            "timeWindow": "最近三个月",
            "weiboClue": "微博话题：小米SU7交付",
        },
        WeiboDataCaps(max_keywords=1, max_selected_posts=2, max_comments_per_post=2),
    )

    assert bundle.provider == "tikhub"
    assert len(bundle.posts) == 1
    assert bundle.posts[0]["content_id"] == "100"
    assert bundle.posts[0]["note_id"] == "100"
    assert bundle.posts[0]["content"] == "小米SU7交付争议"
    assert bundle.posts[0]["author"] == "车主A"
    assert bundle.posts[0]["author_id"] == "u1"
    assert bundle.posts[0]["engagement"]["comment_count"] == 3
    assert len(bundle.comments) == 1
    assert bundle.comments[0]["comment_id"] == "c1"
    assert bundle.comments[0]["note_id"] == "100"
    assert bundle.comments[0]["content"] == "评论交付争议"
    assert bundle.comments[0]["comment_like_count"] == 5
    assert weibo_web.search_calls[0]["search_type"] == "1"
    assert weibo_web.search_calls[0]["time_scope"] == "month"
    assert weibo_web.comment_calls == [
        {"post_id": "100", "mid": "100", "max_id": None, "max_id_type": 0}
    ]
    assert len(weibo_web.search_calls) == 3
    assert bundle.metadata["raw_post_count"] == 6
    assert bundle.metadata["deduped_post_count"] == 1
    assert bundle.metadata["raw_comment_count"] == 1
    assert bundle.metadata["endpoints"]["search"] == "weibo_web.fetch_search"
    assert bundle.metadata["endpoints"]["comments"] == "weibo_web.fetch_post_comments"


def test_tikhub_provider_prefers_weibo_app_search_and_nested_cards():
    weibo_web = FakeWeiboWeb(
        comment_items=[
            {
                "id": "c1",
                "text": "评论LABUBU炒价",
                "created_at": "Fri May 01 11:00:00 +0800 2026",
                "like_count": 5,
                "user": {"id": "cu1", "screen_name": "评论者"},
            }
        ],
    )
    weibo_app = FakeWeiboApp(
        search_cards=[
            {
                "card_type": 11,
                "card_group": [
                    _mblog("100", "LABUBU 价格崩盘，黄牛破防"),
                ],
            },
        ],
    )
    provider = TikHubWeiboProvider(
        api_key="sk-test",
        search_type="1",
        pages_per_keyword=1,
        client_factory=lambda **_kwargs: FakeTikHubClient(weibo_web, weibo_app),
    )

    bundle = provider.collect(
        {
            "eventOrIssue": "炒价黄牛争议",
            "affectedSubject": "LABUBU",
            "timeWindow": "最近三个月",
        },
        WeiboDataCaps(max_keywords=1, max_selected_posts=1),
    )

    assert weibo_app.search_calls == [
        {"query": "LABUBU炒价黄牛争议", "page": 1, "search_type": 1}
    ]
    assert weibo_web.search_calls == []
    assert bundle.posts[0]["content"] == "LABUBU 价格崩盘，黄牛破防"
    assert bundle.metadata["endpoints"]["search"] == "weibo_app.fetch_search_all"
    assert bundle.metadata["irrelevant_post_count"] == 0


def test_tikhub_provider_filters_off_topic_search_cards_before_import():
    weibo_web = FakeWeiboWeb(comment_items=[])
    weibo_app = FakeWeiboApp(
        search_cards=[
            _mblog("100", "领到京东618红包，天天领红包"),
            _mblog("101", "LABUBU 价格崩盘，黄牛破防"),
        ],
    )
    provider = TikHubWeiboProvider(
        api_key="sk-test",
        search_type="1",
        pages_per_keyword=1,
        client_factory=lambda **_kwargs: FakeTikHubClient(weibo_web, weibo_app),
    )

    bundle = provider.collect(
        {"eventOrIssue": "炒价黄牛争议", "affectedSubject": "LABUBU"},
        WeiboDataCaps(max_keywords=1, max_selected_posts=2),
    )

    assert [post["content_id"] for post in bundle.posts] == ["101"]
    assert bundle.metadata["raw_post_count"] == 2
    assert bundle.metadata["irrelevant_post_count"] == 1


def test_tikhub_provider_filters_posts_outside_requested_recent_window_before_comments():
    weibo_web = FakeWeiboWeb(
        comment_items=[
            {
                "id": "c1",
                "text": "评论LABUBU炒价",
                "created_at": "Fri May 01 11:00:00 +0800 2026",
                "like_count": 5,
                "user": {"id": "cu1", "screen_name": "评论者"},
            }
        ],
    )
    weibo_app = FakeWeiboApp(
        search_cards=[
            _mblog(
                "old",
                "LABUBU 价格崩盘，黄牛破防",
                created_at="Sun Jun 01 10:00:00 +0800 2025",
            ),
            _mblog("new", "LABUBU 价格崩盘，黄牛破防"),
        ],
    )
    provider = TikHubWeiboProvider(
        api_key="sk-test",
        search_type="1",
        pages_per_keyword=1,
        client_factory=lambda **_kwargs: FakeTikHubClient(weibo_web, weibo_app),
    )

    bundle = provider.collect(
        {
            "eventOrIssue": "炒价黄牛争议",
            "affectedSubject": "LABUBU",
            "timeWindow": "最近三个月",
        },
        WeiboDataCaps(max_keywords=1, max_selected_posts=2),
    )

    assert [post["content_id"] for post in bundle.posts] == ["new"]
    assert weibo_web.comment_calls == [
        {"post_id": "new", "mid": "new", "max_id": None, "max_id_type": 0}
    ]
    assert bundle.metadata["out_of_window_post_count"] == 1


def test_tikhub_provider_filters_posts_outside_explicit_chinese_date_window_before_comments():
    weibo_web = FakeWeiboWeb(
        search_cards=[
            _mblog(
                "outside",
                "王鹤棣 不舒服文学 亲爱的客栈",
                created_at="Thu Jun 04 10:00:00 +0800 2026",
            ),
            _mblog(
                "inside",
                "王鹤棣回应我当时确实不舒服，不舒服文学继续发酵",
                created_at="Sun May 24 10:00:00 +0800 2026",
            ),
        ],
        comment_items=[],
    )
    weibo_app = FakeWeiboApp(search_cards=[])
    provider = TikHubWeiboProvider(
        api_key="sk-test",
        search_type="1",
        pages_per_keyword=1,
        client_factory=lambda **_kwargs: FakeTikHubClient(weibo_web, weibo_app),
    )

    bundle = provider.collect(
        {
            "eventOrIssue": "王鹤棣在亲爱的客栈2026颁奖环节感到不适并回应我当时确实不舒服，引发不舒服文学。",
            "affectedSubject": "王鹤棣",
            "timeWindow": "2026年5月1日至2026年5月29日",
        },
        WeiboDataCaps(max_keywords=1, max_selected_posts=2),
    )

    assert [post["content_id"] for post in bundle.posts] == ["inside"]
    assert weibo_web.comment_calls == [
        {"post_id": "inside", "mid": "inside", "max_id": None, "max_id_type": 0}
    ]
    assert bundle.metadata["out_of_window_post_count"] == 1
    assert bundle.metadata["time_window_filter"] == {
        "start": "2026-05-01",
        "end_exclusive": "2026-05-30",
    }


def test_tikhub_provider_uses_weibo_web_search_for_explicit_historical_window():
    weibo_web = FakeWeiboWeb(
        search_cards=[
            _mblog(
                "inside",
                "袁娅维道歉，成都演唱会突然取消引发争议",
                created_at="Sat Dec 24 21:56:39 +0800 2022",
            )
        ],
        comment_items=[],
    )
    weibo_app = FakeWeiboApp(
        search_cards=[
            _mblog(
                "recent",
                "袁娅维 成都演唱会近期无关讨论",
                created_at="Fri May 01 10:00:00 +0800 2026",
            )
        ],
    )
    provider = TikHubWeiboProvider(
        api_key="sk-test",
        search_type="61",
        pages_per_keyword=1,
        client_factory=lambda **_kwargs: FakeTikHubClient(weibo_web, weibo_app),
    )

    bundle = provider.collect(
        {
            "eventOrIssue": "袁娅维成都演唱会取消道歉争议",
            "affectedSubject": "袁娅维",
            "timeWindow": "2022年12月23日至2023年1月5日",
            "weiboClue": "袁娅维道歉、演唱会取消、惊奇无限假期",
        },
        WeiboDataCaps(max_keywords=1, max_selected_posts=1),
    )

    assert weibo_app.search_calls == []
    assert weibo_web.search_calls == [
        {
            "keyword": "袁娅维 成都演唱会取消道歉争议",
            "page": 1,
            "search_type": "1",
            "time_scope": None,
        }
    ]
    assert [post["content_id"] for post in bundle.posts] == ["inside"]
    assert bundle.metadata["endpoints"]["search"] == "weibo_web.fetch_search"
    assert bundle.metadata["out_of_window_post_count"] == 0


def test_tikhub_provider_extracts_weibo_app_items_data_posts():
    weibo_web = FakeWeiboWeb(comment_items=[])
    weibo_app = FakeWeiboApp(
        search_items=[
            {"data": _mblog("101", "LABUBU 冰箱炒价讨论")["mblog"]},
        ],
    )
    provider = TikHubWeiboProvider(
        api_key="sk-test",
        search_type="1",
        pages_per_keyword=1,
        client_factory=lambda **_kwargs: FakeTikHubClient(weibo_web, weibo_app),
    )

    bundle = provider.collect(
        {"eventOrIssue": "炒价黄牛争议", "affectedSubject": "LABUBU"},
        WeiboDataCaps(max_keywords=1, max_selected_posts=1),
    )

    assert [post["content_id"] for post in bundle.posts] == ["101"]
    assert bundle.metadata["raw_post_count"] == 1


def test_tikhub_provider_returns_zero_results_stop_reason():
    weibo_web = FakeWeiboWeb(search_cards=[], comment_items=[])
    provider = TikHubWeiboProvider(
        api_key="sk-test",
        client_factory=lambda **_kwargs: FakeTikHubClient(weibo_web),
    )

    bundle = provider.collect(
        {"eventOrIssue": "交付争议", "affectedSubject": "小米SU7"},
        WeiboDataCaps(max_keywords=1),
    )

    assert bundle.posts == []
    assert bundle.comments == []
    assert bundle.stop_reason == "zero_results"
    assert weibo_web.comment_calls == []


def test_tikhub_provider_keeps_posts_when_comment_collection_fails():
    weibo_web = FakeWeiboWeb(
        search_cards=[_mblog("100", "小米SU7交付争议")],
        comment_error=RuntimeError("quota exceeded"),
    )
    provider = TikHubWeiboProvider(
        api_key="sk-test",
        client_factory=lambda **_kwargs: FakeTikHubClient(weibo_web),
    )

    bundle = provider.collect(
        {"eventOrIssue": "交付争议", "affectedSubject": "小米SU7"},
        WeiboDataCaps(max_keywords=1, max_selected_posts=1),
    )

    assert len(bundle.posts) == 1
    assert bundle.comments == []
    assert bundle.stop_reason == "comment_collection_failed"
    assert bundle.metadata["errors"][0]["stage"] == "comments"
    assert "quota exceeded" in bundle.metadata["errors"][0]["message"]


def test_tikhub_provider_paginates_first_level_comments_until_cap():
    class PaginatedComments(FakeWeiboWeb):
        def fetch_post_comments(self, *, post_id, mid, max_id=None, max_id_type=None):
            self.comment_calls.append(
                {
                    "post_id": post_id,
                    "mid": mid,
                    "max_id": max_id,
                    "max_id_type": max_id_type,
                }
            )
            if max_id is None:
                return {
                    "data": {
                        "data": {
                            "data": [
                                {
                                    "id": "c1",
                                    "text": "第一页评论",
                                    "user": {"id": "u1", "screen_name": "A"},
                                }
                            ],
                            "max_id": "cursor-2",
                            "max_id_type": 0,
                        }
                    }
                }
            return {
                "data": {
                    "data": {
                        "data": [
                            {
                                "id": "c2",
                                "text": "第二页评论",
                                "user": {"id": "u2", "screen_name": "B"},
                            }
                        ],
                        "max_id": 0,
                        "max_id_type": 0,
                    }
                }
            }

    weibo_web = PaginatedComments(
        search_cards=[_mblog("100", "小米SU7交付争议")],
    )
    provider = TikHubWeiboProvider(
        api_key="sk-test",
        pages_per_keyword=1,
        client_factory=lambda **_kwargs: FakeTikHubClient(weibo_web),
    )

    bundle = provider.collect(
        {"eventOrIssue": "交付争议", "affectedSubject": "小米SU7"},
        WeiboDataCaps(max_keywords=1, max_selected_posts=1, max_comments_per_post=2),
    )

    assert [comment["comment_id"] for comment in bundle.comments] == ["c1", "c2"]
    assert weibo_web.comment_calls == [
        {"post_id": "100", "mid": "100", "max_id": None, "max_id_type": 0},
        {"post_id": "100", "mid": "100", "max_id": "cursor-2", "max_id_type": 0},
    ]
    assert bundle.metadata["raw_comment_count"] == 2


def test_tikhub_provider_enforces_max_posts_per_keyword_before_dedupe():
    weibo_web = FakeWeiboWeb(
        search_cards=[
            _mblog(str(index), f"小米SU7交付争议 {index}")
            for index in range(5)
        ],
        comment_items=[],
    )
    provider = TikHubWeiboProvider(
        api_key="sk-test",
        pages_per_keyword=1,
        client_factory=lambda **_kwargs: FakeTikHubClient(weibo_web),
    )

    bundle = provider.collect(
        {"eventOrIssue": "交付争议", "affectedSubject": "小米SU7"},
        WeiboDataCaps(max_keywords=1, max_posts_per_keyword=2, max_selected_posts=2),
    )

    assert len(bundle.posts) == 2
    assert bundle.metadata["keyword_post_counts"]["小米SU7交付争议"] == 2
    assert bundle.metadata["post_cap_truncated"] is True


def test_tikhub_provider_raises_setup_error_for_search_auth_or_quota_failure():
    weibo_web = FakeWeiboWeb(search_error=RuntimeError("401 quota exceeded"))
    provider = TikHubWeiboProvider(
        api_key="sk-test",
        pages_per_keyword=1,
        client_factory=lambda **_kwargs: FakeTikHubClient(weibo_web),
    )

    with pytest.raises(TikHubProviderSetupError, match="401 quota exceeded"):
        provider.collect(
            {"eventOrIssue": "交付争议", "affectedSubject": "小米SU7"},
            WeiboDataCaps(max_keywords=1),
        )


def test_tikhub_provider_skips_recoverable_search_400_and_continues():
    class OneBadSearchCall(FakeWeiboWeb):
        def fetch_search(self, *, keyword, page, search_type=None, time_scope=None):
            self.search_calls.append(
                {
                    "keyword": keyword,
                    "page": page,
                    "search_type": search_type,
                    "time_scope": time_scope,
                }
            )
            if len(self.search_calls) == 1:
                raise RuntimeError("400 GET fetch_search: HTTP 400")
            return {"data": {"data": {"cards": self.search_cards}}}

    weibo_web = OneBadSearchCall(
        search_cards=[_mblog("100", "小米SU7交付争议")],
        comment_items=[],
    )
    provider = TikHubWeiboProvider(
        api_key="sk-test",
        pages_per_keyword=1,
        client_factory=lambda **_kwargs: FakeTikHubClient(weibo_web),
    )

    bundle = provider.collect(
        {"eventOrIssue": "交付争议", "affectedSubject": "小米SU7"},
        WeiboDataCaps(max_keywords=2, max_selected_posts=1),
    )

    assert len(bundle.posts) == 1
    assert bundle.metadata["errors"][0]["stage"] == "search"
    assert "HTTP 400" in bundle.metadata["errors"][0]["message"]


def test_tikhub_provider_requires_api_key_without_injected_client():
    provider = TikHubWeiboProvider(api_key="")

    with pytest.raises(TikHubProviderSetupError):
        provider.collect(
            {"eventOrIssue": "交付争议", "affectedSubject": "小米SU7"},
            WeiboDataCaps(max_keywords=1),
        )


def test_tikhub_provider_raises_setup_error_when_sdk_missing(monkeypatch):
    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "tikhub":
            raise ModuleNotFoundError("No module named 'tikhub'", name="tikhub")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    provider = TikHubWeiboProvider(api_key="sk-test")

    with pytest.raises(TikHubProviderSetupError, match="SDK is not installed"):
        provider.collect(
            {"eventOrIssue": "交付争议", "affectedSubject": "小米SU7"},
            WeiboDataCaps(max_keywords=1),
        )


def test_tikhub_provider_repr_redacts_api_key():
    provider = TikHubWeiboProvider(api_key="sk-secret-token")

    assert "sk-secret-token" not in repr(provider)
