from downstream.weibo_data.providers.base import WeiboCollectionBundle
from utils.weibo_evidence_manifest import build_weibo_evidence_manifest


def test_manifest_records_sample_boundary_counts_and_key_evidence():
    bundle = WeiboCollectionBundle(
        provider="tikhub",
        keywords=["王鹤棣 不舒服文学", "我当时确实不舒服"],
        posts=[
            {
                "content_id": "p1",
                "url": "https://weibo.com/p1",
                "content": "王鹤棣回应我当时确实不舒服",
                "author": "娱乐观察",
                "author_id": "u1",
                "publish_time": "2026-05-23 10:00:00",
                "source_keyword": "王鹤棣 不舒服文学",
                "engagement": {
                    "like_count": 1200,
                    "comment_count": 90,
                    "share_count": 30,
                },
            }
        ],
        comments=[
            {
                "comment_id": "c1",
                "note_id": "p1",
                "content": "节目组这个玩笑不合适",
                "nickname": "用户A",
                "user_id": "cu1",
                "create_date_time": "2026-05-23 11:00:00",
                "comment_like_count": 15,
            }
        ],
        stop_reason="reportable",
        metadata={
            "task": {
                "metadata": {
                    "request": {
                        "eventOrIssue": "亲爱的客栈2026 不舒服文学",
                        "affectedSubject": "王鹤棣",
                        "timeWindow": "2026-05-01 至 2026-05-29",
                    }
                }
            },
            "collection_rounds": [{"strategy": "default", "post_count": 1}],
            "errors": [{"stage": "comments", "message": "one comment page failed"}],
        },
    )

    manifest = build_weibo_evidence_manifest(
        bundle=bundle,
        readiness={"data_ready": True, "total_matches": 2},
        reportability={"status": "reportable", "can_start_analysis": True},
        import_result={"counts": {"weibo_note": 1, "weibo_note_comment": 1}},
    )

    assert manifest["manifest_version"] == 1
    assert manifest["provider"] == "tikhub"
    assert manifest["sample_boundary"]["platform"] == "weibo"
    assert manifest["sample_boundary"]["comment_depth"] == "first_level_only"
    assert manifest["sample_boundary"]["represents"] == "collected_weibo_sample_only"
    assert manifest["counts"]["posts"] == 1
    assert manifest["counts"]["comments"] == 1
    assert manifest["counts"]["authors"] == 2
    assert manifest["counts"]["keywords"] == 2
    assert manifest["research_request"]["affectedSubject"] == "王鹤棣"
    assert manifest["key_posts"][0]["source_id"] == "p1"
    assert manifest["key_comments"][0]["source_id"] == "c1"
    assert manifest["provider_errors"][0]["stage"] == "comments"


def test_manifest_preserves_profile_id_from_data_prep_task():
    bundle = WeiboCollectionBundle(
        provider="tikhub",
        keywords=["小米SU7 高速碰撞起火"],
        posts=[
            {
                "content_id": "p1",
                "content": "小米SU7高速碰撞起火事故引发企业回应与安全质疑。",
                "source_keyword": "小米SU7 高速碰撞起火",
            }
        ],
        metadata={
            "task": {
                "metadata": {
                    "request": {
                        "eventOrIssue": "高速碰撞起火事故争议",
                        "affectedSubject": "小米SU7",
                        "profileId": "enterprise_pr",
                    }
                }
            }
        },
    )

    manifest = build_weibo_evidence_manifest(bundle=bundle)

    assert manifest["research_request"]["profileId"] == "enterprise_pr"


def test_manifest_filters_off_topic_high_engagement_before_ranking():
    bundle = WeiboCollectionBundle(
        provider="tikhub",
        keywords=["王鹤棣", "不舒服文学", "我当时确实不舒服"],
        posts=[
            {
                "content_id": "promo",
                "url": "sinaweibo://detail/?mblogid=promo",
                "content": "王鹤棣五月酷云影响力之星，剧集综艺双赛道成绩优异。",
                "author": "酷云数娱",
                "publish_time": "2026-06-02 03:02:11",
                "source_keyword": "王鹤棣",
                "engagement": {"like_count": 9000, "comment_count": 800, "share_count": 700},
            },
            {
                "content_id": "event",
                "url": "sinaweibo://detail/?mblogid=event",
                "content": "王鹤棣回应我当时确实不舒服，不舒服文学继续发酵。",
                "author": "娱乐观察",
                "publish_time": "2026-05-23 10:00:00",
                "source_keyword": "不舒服文学",
                "engagement": {"like_count": 30, "comment_count": 8, "share_count": 2},
            },
        ],
        metadata={
            "task": {
                "metadata": {
                    "request": {
                        "eventOrIssue": "王鹤棣在亲爱的客栈2026因颁奖环节感到不适并回应我当时确实不舒服，引发不舒服文学出圈。",
                        "affectedSubject": "王鹤棣",
                        "timeWindow": "2026-05-01 至 2026-05-29",
                    }
                }
            }
        },
    )

    manifest = build_weibo_evidence_manifest(bundle=bundle)

    assert [post["source_id"] for post in manifest["key_posts"]] == ["event"]
    assert "酷云影响力之星" not in str(manifest["key_posts"])


def test_manifest_filters_key_evidence_outside_confirmed_time_window():
    bundle = WeiboCollectionBundle(
        provider="tikhub",
        keywords=["王鹤棣", "亲爱的客栈2026", "不舒服文学"],
        posts=[
            {
                "content_id": "outside",
                "content": "王鹤棣亲爱的客栈2026相关争议继续发酵，吴泽林捂耳朵片段被讨论。",
                "publish_time": "2026-06-04 05:06:35",
                "source_keyword": "王鹤棣 亲爱的客栈2026",
                "engagement": {"like_count": 999, "comment_count": 99},
            },
            {
                "content_id": "inside",
                "content": "王鹤棣回应我当时确实不舒服，不舒服文学继续发酵。",
                "publish_time": "2026-05-23 10:00:00",
                "source_keyword": "不舒服文学",
                "engagement": {"like_count": 8, "comment_count": 1},
            },
        ],
        comments=[
            {
                "comment_id": "outside-comment",
                "note_id": "outside",
                "content": "这个玩笑边界还是要讨论。",
                "create_date_time": "2026-06-04 06:00:00",
                "comment_like_count": 100,
            },
            {
                "comment_id": "inside-comment",
                "note_id": "inside",
                "content": "这个玩笑确实不合适。",
                "create_date_time": "2026-05-23 11:00:00",
                "comment_like_count": 1,
            },
        ],
        metadata={
            "task": {
                "metadata": {
                    "request": {
                        "eventOrIssue": "王鹤棣在亲爱的客栈2026因颁奖环节感到不适并回应我当时确实不舒服，引发不舒服文学出圈。",
                        "affectedSubject": "王鹤棣",
                        "timeWindow": "2026年5月1日至2026年5月29日",
                    }
                }
            }
        },
    )

    manifest = build_weibo_evidence_manifest(bundle=bundle)

    assert [post["source_id"] for post in manifest["key_posts"]] == ["inside"]
    assert [comment["source_id"] for comment in manifest["key_comments"]] == [
        "inside-comment"
    ]
    assert "outside" not in str(manifest["key_posts"])
    assert "outside-comment" not in str(manifest["key_comments"])


def test_manifest_requires_subject_or_specific_event_phrase_not_broad_program_only():
    bundle = WeiboCollectionBundle(
        provider="tikhub",
        keywords=["亲爱的客栈2026", "王鹤棣", "不舒服文学"],
        posts=[
            {
                "content_id": "broad-program",
                "content": "沈月海外热度上升至TOP6，《亲爱的客栈2026》收官后粉丝考古持续升温。",
                "author": "V-Pulse",
                "publish_time": "2026-06-02 14:03:29",
                "source_keyword": "亲爱的客栈2026",
                "engagement": {"like_count": 710, "comment_count": 67, "share_count": 35},
            },
            {
                "content_id": "event",
                "content": "王鹤棣回应我当时确实不舒服，不舒服文学继续发酵。",
                "author": "娱乐观察",
                "publish_time": "2026-05-23 10:00:00",
                "source_keyword": "不舒服文学",
                "engagement": {"like_count": 8, "comment_count": 1},
            },
        ],
        metadata={
            "task": {
                "metadata": {
                    "request": {
                        "eventOrIssue": "王鹤棣在亲爱的客栈2026因颁奖环节感到不适并回应我当时确实不舒服，引发不舒服文学出圈。",
                        "affectedSubject": "王鹤棣",
                        "timeWindow": "2026-05-01 至 2026-05-29",
                    }
                }
            }
        },
    )

    manifest = build_weibo_evidence_manifest(bundle=bundle)

    assert [post["source_id"] for post in manifest["key_posts"]] == ["event"]
    assert "沈月海外热度" not in str(manifest["key_posts"])


def test_manifest_excludes_meme_derivatives_without_subject_or_core_event_anchor():
    bundle = WeiboCollectionBundle(
        provider="tikhub",
        keywords=["王鹤棣", "我当时确实不舒服", "不舒服文学"],
        posts=[
            {
                "content_id": "derivative-concert",
                "content": "这个不舒服文学不要太好用，我没去成韩庚的演唱会，在家分析了一天，现在想想，我当时确实不舒服。",
                "publish_time": "2026-06-03 09:56:34",
                "source_keyword": "我当时确实不舒服",
                "engagement": {"like_count": 120, "comment_count": 40},
            },
            {
                "content_id": "derivative-other-artist",
                "content": "#王安宇# 我想说我当时确实不舒服，安宇就这样被水泼向眼睛。",
                "publish_time": "2026-06-03 07:54:35",
                "source_keyword": "我当时确实不舒服",
                "engagement": {"like_count": 90, "comment_count": 20},
            },
            {
                "content_id": "event",
                "content": "王鹤棣在亲爱的客栈颁奖环节回应我当时确实不舒服，不舒服文学继续发酵。",
                "publish_time": "2026-06-03 12:00:00",
                "source_keyword": "不舒服文学",
                "engagement": {"like_count": 3, "comment_count": 1},
            },
        ],
        metadata={
            "task": {
                "metadata": {
                    "request": {
                        "eventOrIssue": "王鹤棣在亲爱的客栈2026因颁奖环节感到不适并回应我当时确实不舒服，引发不舒服文学出圈。",
                        "affectedSubject": "王鹤棣",
                    }
                }
            }
        },
    )

    manifest = build_weibo_evidence_manifest(bundle=bundle)

    assert [post["source_id"] for post in manifest["key_posts"]] == ["event"]
    assert "韩庚的演唱会" not in str(manifest["key_posts"])
    assert "王安宇" not in str(manifest["key_posts"])


def test_manifest_uses_general_relevance_instead_of_event_blacklists():
    bundle = WeiboCollectionBundle(
        provider="tikhub",
        keywords=["小米SU7 高速碰撞起火", "事故争议"],
        posts=[
            {
                "content_id": "broad-brand",
                "content": "小米SU7本周门店活动热度很高，现场体验人数继续增加。",
                "author": "科技观察",
                "publish_time": "2025-04-02 10:00:00",
                "source_keyword": "小米SU7",
                "engagement": {"like_count": 12000, "comment_count": 1500},
            },
            {
                "content_id": "event",
                "content": "小米SU7高速碰撞起火事故引发安全质疑，企业回应仍被追问。",
                "author": "新闻观察",
                "publish_time": "2025-04-01 10:00:00",
                "source_keyword": "小米SU7 高速碰撞起火",
                "engagement": {"like_count": 30, "comment_count": 8},
            },
        ],
        metadata={
            "task": {
                "metadata": {
                    "request": {
                        "eventOrIssue": "高速碰撞起火事故争议",
                        "affectedSubject": "小米SU7",
                        "profileId": "enterprise_pr",
                    }
                }
            }
        },
    )

    manifest = build_weibo_evidence_manifest(bundle=bundle)

    assert [post["source_id"] for post in manifest["key_posts"]] == ["event"]
    assert "门店活动" not in str(manifest["key_posts"])


def test_manifest_uses_request_and_keyword_signals_without_fixed_event_allowlists():
    bundle = WeiboCollectionBundle(
        provider="tikhub",
        keywords=["蓝鲸云服务 数据泄露 隐私担忧", "会员资料外流"],
        posts=[
            {
                "content_id": "promo",
                "content": "蓝鲸云服务本周上线会员权益活动，转发抽取年度套餐。",
                "publish_time": "2026-05-02 09:00:00",
                "source_keyword": "蓝鲸云服务",
                "engagement": {"like_count": 9000, "comment_count": 500},
            },
            {
                "content_id": "event",
                "content": "蓝鲸云服务会员数据泄露后，用户集中担忧隐私保护和资料外流。",
                "publish_time": "2026-05-02 10:00:00",
                "source_keyword": "蓝鲸云服务 数据泄露 隐私担忧",
                "engagement": {"like_count": 12, "comment_count": 4},
            },
        ],
        comments=[
            {
                "comment_id": "event-comment",
                "note_id": "event",
                "content": "隐私担忧不是小事，企业要解释资料外流范围。",
                "create_date_time": "2026-05-02 11:00:00",
                "comment_like_count": 8,
            }
        ],
        metadata={
            "task": {
                "metadata": {
                    "request": {
                        "eventOrIssue": "蓝鲸云服务会员数据泄露引发隐私担忧",
                        "affectedSubject": "蓝鲸云服务",
                        "profileId": "enterprise_pr",
                    }
                }
            }
        },
    )

    manifest = build_weibo_evidence_manifest(bundle=bundle)

    assert [post["source_id"] for post in manifest["key_posts"]] == ["event"]
    assert [comment["source_id"] for comment in manifest["key_comments"]] == [
        "event-comment"
    ]
    assert "会员权益活动" not in str(manifest["key_posts"])


def test_manifest_comments_inherit_parent_relevance():
    bundle = WeiboCollectionBundle(
        provider="tikhub",
        keywords=["不舒服文学"],
        posts=[
            {
                "content_id": "event",
                "content": "王鹤棣回应我当时确实不舒服，不舒服文学引发讨论。",
                "publish_time": "2026-05-23 10:00:00",
                "source_keyword": "不舒服文学",
                "engagement": {"like_count": 20},
            }
        ],
        comments=[
            {
                "comment_id": "event-comment",
                "note_id": "event",
                "content": "这个玩笑确实不合适",
                "nickname": "用户A",
                "create_date_time": "2026-05-23 11:00:00",
                "comment_like_count": 5,
            },
            {
                "comment_id": "orphan-comment",
                "note_id": "other",
                "content": "晚上好这里蹲",
                "nickname": "用户B",
                "create_date_time": "2026-06-02 14:10:45",
                "comment_like_count": 500,
            },
        ],
        metadata={
            "task": {
                "metadata": {
                    "request": {
                        "eventOrIssue": "亲爱的客栈2026 不舒服文学",
                        "affectedSubject": "王鹤棣",
                    }
                }
            }
        },
    )

    manifest = build_weibo_evidence_manifest(bundle=bundle)

    assert [comment["source_id"] for comment in manifest["key_comments"]] == [
        "event-comment"
    ]


def test_manifest_requires_post_body_relevance_not_only_source_keyword():
    broad_keyword = "王鹤棣（中国演员、艺人）王鹤棣在《亲爱的客栈2026》中"
    bundle = WeiboCollectionBundle(
        provider="tikhub",
        keywords=[broad_keyword, "不舒服文学", "我当时确实不舒服"],
        posts=[
            {
                "content_id": "movie",
                "content": "影院相约去看《星河入梦》吧，附主演王鹤棣介绍。",
                "publish_time": "2026-02-27 00:05:13",
                "source_keyword": broad_keyword,
                "engagement": {"like_count": 500},
            },
            {
                "content_id": "event",
                "content": "王鹤棣称我当时确实不舒服，不舒服文学继续发酵。",
                "publish_time": "2026-05-27 16:30:56",
                "source_keyword": broad_keyword,
                "engagement": {"like_count": 5},
            },
        ],
        metadata={
            "task": {
                "metadata": {
                    "request": {
                        "eventOrIssue": "王鹤棣在亲爱的客栈2026颁奖环节感到不适并回应我当时确实不舒服，引发不舒服文学。",
                        "affectedSubject": "王鹤棣",
                    }
                }
            }
        },
    )

    manifest = build_weibo_evidence_manifest(bundle=bundle)

    assert [post["source_id"] for post in manifest["key_posts"]] == ["event"]
    assert "星河入梦" not in str(manifest["key_posts"])


def test_manifest_filters_generic_comments_even_when_parent_is_relevant():
    bundle = WeiboCollectionBundle(
        provider="tikhub",
        keywords=["王鹤棣 不舒服文学"],
        posts=[
            {
                "content_id": "event",
                "content": "王鹤棣回应我当时确实不舒服，不舒服文学引发讨论。",
                "source_keyword": "不舒服文学",
                "engagement": {"like_count": 20},
            }
        ],
        comments=[
            {
                "comment_id": "generic",
                "note_id": "event",
                "content": "不管你现在多迷茫，过得多累，走得多艰辛，请相信生命中总有一段路要自己走完。",
                "nickname": "用户A",
                "create_date_time": "2026-05-23 11:00:00",
                "comment_like_count": 50,
            },
            {
                "comment_id": "contextual",
                "note_id": "event",
                "content": "这个玩笑确实不合适，节目组应该道歉。",
                "nickname": "用户B",
                "create_date_time": "2026-05-23 11:05:00",
                "comment_like_count": 3,
            },
        ],
        metadata={
            "task": {
                "metadata": {
                    "request": {
                        "eventOrIssue": "亲爱的客栈2026 不舒服文学",
                        "affectedSubject": "王鹤棣",
                    }
                }
            }
        },
    )

    manifest = build_weibo_evidence_manifest(bundle=bundle)

    assert [comment["source_id"] for comment in manifest["key_comments"]] == [
        "contextual"
    ]
    assert "不管你现在多迷茫" not in str(manifest["key_comments"])


def test_manifest_handles_weak_empty_samples_without_key_evidence():
    bundle = WeiboCollectionBundle(
        provider="tikhub",
        keywords=["王鹤棣"],
        posts=[
            {
                "content_id": "weak",
                "content": "王鹤棣新剧花絮释出。",
                "source_keyword": "王鹤棣",
                "engagement": {"like_count": 100},
            }
        ],
        comments=[],
        metadata={
            "task": {
                "metadata": {
                    "request": {
                        "eventOrIssue": "亲爱的客栈2026 不舒服文学",
                        "affectedSubject": "王鹤棣",
                    }
                }
            }
        },
    )

    manifest = build_weibo_evidence_manifest(bundle=bundle)

    assert manifest["counts"]["posts"] == 1
    assert manifest["key_posts"] == []
    assert manifest["key_comments"] == []


def test_manifest_matches_common_variants_of_quoted_event_phrase():
    bundle = WeiboCollectionBundle(
        provider="tikhub",
        keywords=["王鹤棣", "我当时确实不舒服", "不舒服文学"],
        posts=[
            {
                "content_id": "variant",
                "content": "我依旧坚定@王鹤棣_Dylan #王鹤棣说自己确实不舒服##王鹤棣[超话]#",
                "publish_time": "2026-05-24 10:00:00",
                "source_keyword": "王鹤棣",
                "engagement": {"like_count": 12},
            }
        ],
        metadata={
            "task": {
                "metadata": {
                    "request": {
                        "eventOrIssue": "王鹤棣在亲爱的客栈2026颁奖环节感到不适并回应我当时确实不舒服，引发不舒服文学。",
                        "affectedSubject": "王鹤棣",
                    }
                }
            }
        },
    )

    manifest = build_weibo_evidence_manifest(bundle=bundle)

    assert [post["source_id"] for post in manifest["key_posts"]] == ["variant"]


def test_manifest_keeps_multiple_event_behavior_evidence_not_only_phrase_matches():
    bundle = WeiboCollectionBundle(
        provider="tikhub",
        keywords=["王鹤棣", "亲爱的客栈2026", "不舒服文学"],
        posts=[
            {
                "content_id": "direct",
                "content": "王鹤棣回应我当时确实不舒服，不舒服文学继续发酵。",
                "publish_time": "2026-05-23 10:00:00",
                "source_keyword": "不舒服文学",
                "engagement": {"like_count": 20, "comment_count": 2},
            },
            {
                "content_id": "wuzelin",
                "content": "网友发现节目里别人夸王鹤棣时，吴泽林捂耳朵不听，相关画面后续被剪掉。",
                "publish_time": "2026-06-04 16:46:23",
                "source_keyword": "王鹤棣 在《亲爱的客栈2026》中",
                "engagement": {"like_count": 14, "comment_count": 3},
            },
            {
                "content_id": "group-joke",
                "content": "王鹤棣在亲爱的客栈收官颁奖环节被调侃小群没你，玩笑边界引发讨论。",
                "publish_time": "2026-05-24 11:00:00",
                "source_keyword": "亲爱的客栈2026",
                "engagement": {"like_count": 10, "comment_count": 1},
            },
            {
                "content_id": "daily",
                "content": "王鹤棣新剧路透造型很帅，粉丝期待咸鱼飞升播出。",
                "publish_time": "2026-06-04 16:45:29",
                "source_keyword": "王鹤棣",
                "engagement": {"like_count": 9000, "comment_count": 800},
            },
        ],
        metadata={
            "task": {
                "metadata": {
                    "request": {
                        "eventOrIssue": "王鹤棣在亲爱的客栈2026因颁奖环节感到不适并回应我当时确实不舒服，引发不舒服文学出圈。",
                        "affectedSubject": "王鹤棣",
                    }
                }
            }
        },
    )

    manifest = build_weibo_evidence_manifest(bundle=bundle)

    assert {post["source_id"] for post in manifest["key_posts"]} == {
        "direct",
        "wuzelin",
        "group-joke",
    }
    assert "新剧路透" not in str(manifest["key_posts"])


def test_manifest_keeps_real_tikhub_style_event_posts_and_comments():
    bundle = WeiboCollectionBundle(
        provider="tikhub",
        keywords=[
            "亲爱的客栈2026",
            "王鹤棣",
            "不舒服文学",
            "我当时确实不舒服",
            "亲爱的客栈",
            "不舒服",
        ],
        posts=[
            {
                "content_id": "5303361425637377",
                "note_id": "5303361425637377",
                "url": "sinaweibo://detail/?mblogid=5303361425637377&id=5303361425637377",
                "content": "#王鹤棣不舒服只是迟到的自我保护#为什么当时不说呢 迟来的觉悟可不好 我也不舒服了",
                "author": "娱乐用户",
                "publish_time": "2026-05-24 10:00:00",
                "source_keyword": "王鹤棣",
                "liked_count": "321",
                "comments_count": "12",
                "shared_count": "4",
            },
            {
                "content_id": "5302148965338652",
                "note_id": "5302148965338652",
                "url": "sinaweibo://detail/?mblogid=5302148965338652&id=5302148965338652",
                "content": "#不舒服文学下沉出圈# 从王鹤棣一句“当时以为是我敏感了，但确实不舒服”火起来。",
                "author": "梗观察",
                "publish_time": "2026-05-23 12:00:00",
                "source_keyword": "不舒服文学",
                "liked_count": "58",
                "comments_count": "8",
                "shared_count": "2",
            },
            {
                "content_id": "daily",
                "note_id": "daily",
                "content": "王鹤棣新剧路透造型很好看，粉丝期待播出。",
                "author": "剧粉",
                "publish_time": "2026-05-24 10:00:00",
                "source_keyword": "王鹤棣",
                "liked_count": "9999",
                "comments_count": "999",
                "shared_count": "99",
            },
        ],
        comments=[
            {
                "comment_id": "comment-1",
                "note_id": "5303361425637377",
                "content": "这个颁奖玩笑确实不合适，边界感太差了。",
                "nickname": "用户A",
                "create_date_time": "2026-05-24 11:00:00",
                "comment_like_count": "22",
            }
        ],
        metadata={
            "task": {
                "metadata": {
                    "request": {
                        "eventOrIssue": "王鹤棣在《亲爱的客栈2026》中因颁奖感到不适并发微博回应（我当时确实不舒服）引发不舒服文学出圈",
                        "affectedSubject": "王鹤棣",
                        "timeWindow": "2026年5月1日至2026年5月29日",
                    }
                }
            }
        },
    )

    manifest = build_weibo_evidence_manifest(bundle=bundle)

    assert {post["source_id"] for post in manifest["key_posts"]} == {
        "5303361425637377",
        "5302148965338652",
    }
    assert "新剧路透" not in str(manifest["key_posts"])
    assert [comment["source_id"] for comment in manifest["key_comments"]] == [
        "comment-1"
    ]
    assert manifest["key_posts"][0]["engagement"]["like_count"] > 0
