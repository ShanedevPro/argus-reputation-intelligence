import json

from downstream.weibo_data.providers.base import WeiboCollectionBundle


def test_crawl_task_store_creates_task_with_created_status():
    from utils.crawl_tasks import CrawlTaskStore

    task = CrawlTaskStore().create_task(
        analysis_query="分析小米SU7交付争议",
        data_request="小米SU7交付争议",
        provider="tikhub",
    )

    assert task.status == "created"
    assert "evidence_manifest" in task.to_dict()


def _set_weibo_caps(monkeypatch, app, *, selected_posts=30, comments_per_post=90):
    monkeypatch.setattr(app.settings, "CRAWLER_CLOUD_ENDPOINT", None, raising=False)
    monkeypatch.setattr(app.settings, "WEIBO_DATA_PROVIDER", "tikhub", raising=False)
    monkeypatch.setattr(app.settings, "WEIBO_DATA_MAX_KEYWORDS", 6, raising=False)
    monkeypatch.setattr(app.settings, "WEIBO_DATA_MAX_POSTS_PER_KEYWORD", 30, raising=False)
    monkeypatch.setattr(app.settings, "WEIBO_DATA_MAX_SELECTED_POSTS", selected_posts, raising=False)
    monkeypatch.setattr(app.settings, "WEIBO_DATA_MAX_COMMENTS_PER_POST", comments_per_post, raising=False)
    monkeypatch.setattr(app.settings, "WEIBO_DATA_MAX_COMMENTS_PER_POST_HARD", comments_per_post, raising=False)
    monkeypatch.setattr(app.settings, "WEIBO_DATA_ALLOW_SUBCOMMENTS", False, raising=False)


def test_create_crawl_task_executes_tikhub_provider_and_marks_reportable(monkeypatch):
    import app

    _set_weibo_caps(monkeypatch, app)
    imported = []

    class FakeProvider:
        name = "tikhub"

        def collect(self, request, caps):
            assert request["eventOrIssue"] == "交付争议"
            return WeiboCollectionBundle(
                provider="tikhub",
                keywords=["小米SU7交付争议", "交付争议"],
                posts=[
                    {
                        "content_id": str(index),
                        "content": f"小米SU7交付争议 post {index}",
                        "author": f"user-{index % 5}",
                        "source_keyword": "小米SU7交付争议" if index % 2 else "交付争议",
                    }
                    for index in range(25)
                ],
                comments=[
                    {
                        "comment_id": str(index),
                        "note_id": str(index % 25),
                        "content": "交付争议评论",
                    }
                    for index in range(90)
                ],
                metadata={"raw_post_count": 25, "raw_comment_count": 90},
            )

    async def fake_import_records(paths, dsn, relevant_only=True):
        imported.append(
            {
                "paths": [str(path) for path in paths],
                "dsn": dsn,
                "relevant_only": relevant_only,
            }
        )
        return {
            "provider": "tikhub",
            "counts": {
                "seen_posts": 25,
                "seen_comments": 90,
                "weibo_note": 25,
                "weibo_note_comment": 90,
            },
        }

    async def fake_check_data_readiness(query, minimum_total=1, minimum_tables=1, platforms=None):
        assert platforms == ["weibo"]
        return {
            "success": True,
            "query": query,
            "status": "ready",
            "data_ready": True,
            "total_matches": 25,
            "matched_tables": 2,
            "checks": [],
            "errors": [],
        }

    monkeypatch.setattr(app, "select_weibo_provider", lambda _settings: FakeProvider())
    monkeypatch.setattr(app, "import_weibo_bundle", fake_import_records)
    monkeypatch.setattr(app, "check_data_readiness", fake_check_data_readiness)

    response = app.app.test_client().post(
        "/api/crawl/tasks",
        json={
            "analysis_query": "分析小米SU7交付争议最近三个月微博舆情风险",
            "data_request": {
                "eventOrIssue": "交付争议",
                "affectedSubject": "小米SU7",
                "timeWindow": "最近三个月",
                "weiboClue": "微博话题：小米SU7交付",
            },
        },
    )

    assert response.status_code in {200, 202}
    payload = response.get_json()
    assert payload["success"] is True
    assert payload["task"]["provider"] == "tikhub"
    assert payload["task"]["status"] == "reportable"
    assert payload["task"]["reportability"]["can_start_analysis"] is True
    assert payload["task"]["reportability"]["status"] == "reportable"
    assert payload["task"]["evidence_manifest"]["sample_boundary"]["platform"] == "weibo"
    assert payload["task"]["evidence_manifest"]["counts"]["posts"] == 25
    assert payload["task"]["evidence_manifest"]["counts"]["comments"] == 90
    assert payload["task"]["bundle_metadata"]["raw_post_count"] == 25
    assert payload["task"]["import_result"]["counts"]["weibo_note"] == 25
    assert payload["task"]["readiness"]["data_ready"] is True
    assert imported and imported[0]["relevant_only"] is True


def test_create_crawl_task_accepts_event_and_keywords_aliases(monkeypatch):
    import app

    _set_weibo_caps(monkeypatch, app)
    seen_requests = []
    readiness_queries = []

    class FakeProvider:
        name = "tikhub"

        def collect(self, request, caps):
            seen_requests.append(dict(request))
            assert request["eventOrIssue"] == "不舒服文学出圈争议"
            assert request["affectedSubject"] == "王鹤棣"
            assert request["profileId"] == "artist_management"
            assert "我当时确实不舒服" in request["knownMaterials"]
            assert "亲爱的客栈" in request["knownMaterials"]
            return WeiboCollectionBundle(
                provider="tikhub",
                keywords=["王鹤棣 不舒服文学", "我当时确实不舒服", "亲爱的客栈"],
                posts=[
                    {
                        "content_id": str(index),
                        "content": f"王鹤棣 不舒服文学 post {index}",
                        "author": f"user-{index % 5}",
                        "source_keyword": "王鹤棣 不舒服文学",
                    }
                    for index in range(25)
                ],
                comments=[
                    {
                        "comment_id": str(index),
                        "note_id": str(index % 25),
                        "content": "我当时确实不舒服 评论",
                    }
                    for index in range(90)
                ],
                metadata={"raw_post_count": 25, "raw_comment_count": 90},
            )

    async def fake_import_records(paths, dsn, relevant_only=True):
        return {
            "provider": "tikhub",
            "counts": {
                "seen_posts": 25,
                "seen_comments": 90,
                "weibo_note": 25,
                "weibo_note_comment": 90,
            },
        }

    async def fake_check_data_readiness(query, minimum_total=1, minimum_tables=1, platforms=None):
        readiness_queries.append(query)
        return {
            "success": True,
            "query": query,
            "status": "ready",
            "data_ready": True,
            "total_matches": 25,
            "matched_tables": 2,
            "checks": [],
            "errors": [],
        }

    monkeypatch.setattr(app, "select_weibo_provider", lambda _settings: FakeProvider())
    monkeypatch.setattr(app, "import_weibo_bundle", fake_import_records)
    monkeypatch.setattr(app, "check_data_readiness", fake_check_data_readiness)

    response = app.app.test_client().post(
        "/api/crawl/tasks",
        json={
            "analysis_query": "王鹤棣 不舒服文学",
            "data_request": {
                "event": "不舒服文学出圈争议",
                "affectedSubject": "王鹤棣",
                "timeWindow": "2026年5月1日至2026年5月29日",
                "profileId": "artist_management",
                "keywords": ["我当时确实不舒服", "亲爱的客栈"],
            },
        },
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["success"] is True
    assert payload["task"]["status"] == "reportable"
    assert seen_requests
    assert readiness_queries
    assert "我当时确实不舒服" in readiness_queries[-1]
    assert "亲爱的客栈" in readiness_queries[-1]


def test_create_crawl_task_normalizes_snake_case_profile_request(monkeypatch):
    import app

    _set_weibo_caps(monkeypatch, app)
    seen_requests = []

    class FakeProvider:
        name = "tikhub"

        def collect(self, request, caps):
            seen_requests.append(dict(request))
            assert request["eventOrIssue"] == "袁娅维2022年成都演唱会取消争议"
            assert request["affectedSubject"] == "袁娅维"
            assert request["timeWindow"] == "2022年12月23日至2023年1月5日"
            assert request["profileId"] == "artist_management"
            assert "惊奇无限假期" in request["knownMaterials"]
            return WeiboCollectionBundle(
                provider="tikhub",
                keywords=["袁娅维", "惊奇无限假期"],
                posts=[
                    {
                        "content_id": str(index),
                        "content": f"袁娅维 惊奇无限假期 成都演唱会取消 post {index}",
                        "author": f"user-{index % 5}",
                        "source_keyword": "袁娅维",
                    }
                    for index in range(25)
                ],
                comments=[
                    {
                        "comment_id": str(index),
                        "note_id": str(index % 25),
                        "content": "取消演唱会补偿沟通评论",
                    }
                    for index in range(90)
                ],
                metadata={"raw_post_count": 25, "raw_comment_count": 90},
            )

    async def fake_import_records(paths, dsn, relevant_only=True):
        return {
            "provider": "tikhub",
            "counts": {"weibo_note": 25, "weibo_note_comment": 90},
        }

    async def fake_check_data_readiness(query, minimum_total=1, minimum_tables=1, platforms=None):
        return {
            "success": True,
            "query": query,
            "status": "ready",
            "data_ready": True,
            "total_matches": 25,
            "matched_tables": 2,
            "checks": [],
            "errors": [],
        }

    monkeypatch.setattr(app, "select_weibo_provider", lambda _settings: FakeProvider())
    monkeypatch.setattr(app, "import_weibo_bundle", fake_import_records)
    monkeypatch.setattr(app, "check_data_readiness", fake_check_data_readiness)

    response = app.app.test_client().post(
        "/api/crawl/tasks",
        json={
            "analysis_query": "袁娅维2022年成都演唱会取消争议",
            "data_request": {
                "event": "袁娅维2022年成都演唱会取消争议",
                "affected_subject": "袁娅维",
                "time_window": "2022年12月23日至2023年1月5日",
                "profile_id": "artist_management",
                "keywords": ["惊奇无限假期", "成都演唱会", "演唱会取消"],
            },
        },
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["success"] is True
    saved_request = json.loads(payload["task"]["data_request"])
    assert saved_request["affectedSubject"] == "袁娅维"
    assert saved_request["timeWindow"] == "2022年12月23日至2023年1月5日"
    assert saved_request["profileId"] == "artist_management"
    assert "惊奇无限假期" in saved_request["knownMaterials"]
    assert payload["task"]["bundle_metadata"]["task"]["metadata"]["original_time_window"] == (
        "2022年12月23日至2023年1月5日"
    )
    assert seen_requests


def test_create_crawl_task_preserves_profile_id_through_manifest(monkeypatch):
    import app

    _set_weibo_caps(monkeypatch, app)
    seen_requests = []

    class FakeProvider:
        name = "tikhub"

        def collect(self, request, caps):
            seen_requests.append(dict(request))
            return WeiboCollectionBundle(
                provider="tikhub",
                keywords=["小米SU7 高速碰撞起火"],
                posts=[
                    {
                        "content_id": str(index),
                        "content": f"小米SU7高速碰撞起火事故争议 post {index}",
                        "author": f"user-{index % 5}",
                        "source_keyword": "小米SU7 高速碰撞起火",
                    }
                    for index in range(25)
                ],
                comments=[
                    {
                        "comment_id": str(index),
                        "note_id": str(index % 25),
                        "content": "企业回应和安全责任仍需解释",
                    }
                    for index in range(90)
                ],
                metadata={"raw_post_count": 25, "raw_comment_count": 90},
            )

    async def fake_import_records(paths, dsn, relevant_only=True):
        return {
            "provider": "tikhub",
            "counts": {"weibo_note": 25, "weibo_note_comment": 90},
        }

    async def fake_check_data_readiness(query, minimum_total=1, minimum_tables=1, platforms=None):
        return {"success": True, "data_ready": True, "checks": [], "errors": []}

    monkeypatch.setattr(app, "select_weibo_provider", lambda _settings: FakeProvider())
    monkeypatch.setattr(app, "import_weibo_bundle", fake_import_records)
    monkeypatch.setattr(app, "check_data_readiness", fake_check_data_readiness)

    response = app.app.test_client().post(
        "/api/crawl/tasks",
        json={
            "analysis_query": "小米SU7 高速碰撞起火事故 2025",
            "data_request": {
                "eventOrIssue": "高速碰撞起火事故争议",
                "affectedSubject": "小米SU7",
                "timeWindow": "2025-03-29 至 2025-04-30",
                "profileId": "enterprise_pr",
            },
        },
    )

    payload = response.get_json()

    assert payload["task"]["status"] == "reportable"
    assert seen_requests[0]["profileId"] == "enterprise_pr"
    assert '"profileId": "enterprise_pr"' in payload["task"]["data_request"]
    assert payload["task"]["bundle_metadata"]["task"]["metadata"]["request"]["profileId"] == "enterprise_pr"
    assert payload["task"]["evidence_manifest"]["research_request"]["profileId"] == "enterprise_pr"


def test_create_crawl_task_blocks_analysis_when_tikhub_has_insufficient_data(monkeypatch):
    import app

    _set_weibo_caps(monkeypatch, app)
    imported = []
    analysis_started = []

    class FakeProvider:
        name = "tikhub"

        def collect(self, request, caps):
            return WeiboCollectionBundle(
                provider="tikhub",
                keywords=["小米SU7交付争议"],
                posts=[],
                comments=[],
                stop_reason="zero_results",
                metadata={"raw_post_count": 0, "raw_comment_count": 0},
            )

    async def fake_import_records(paths, dsn, relevant_only=True):
        imported.append(paths)
        return {"counts": {"weibo_note": 0, "weibo_note_comment": 0}}

    class FakeSearchOrchestrator:
        def start_search(self, query):
            analysis_started.append(query)
            return {"success": True}

    monkeypatch.setattr(app, "select_weibo_provider", lambda _settings: FakeProvider())
    monkeypatch.setattr(app, "import_weibo_bundle", fake_import_records)
    monkeypatch.setattr(app, "search_orchestrator", FakeSearchOrchestrator())

    response = app.app.test_client().post(
        "/api/crawl/tasks",
        json={
            "analysis_query": "分析小米SU7交付争议最近三个月微博舆情风险",
            "data_request": {
                "eventOrIssue": "交付争议",
                "affectedSubject": "小米SU7",
            },
        },
    )

    assert response.status_code in {200, 202}
    payload = response.get_json()
    assert payload["task"]["status"] == "insufficient_data"
    assert payload["task"]["reportability"]["stop_reason"] == "zero_results"
    assert payload["task"]["reportability"]["can_start_analysis"] is False
    assert payload["task"]["evidence_manifest"]["sample_boundary"]["comment_depth"] == "first_level_only"
    assert payload["task"]["evidence_manifest"]["counts"]["posts"] == 0
    assert "微博样本不足" in payload["task"]["next_action"]
    assert imported == []
    assert analysis_started == []


def test_create_crawl_task_runs_bounded_fallback_until_reportable(monkeypatch):
    import app

    _set_weibo_caps(monkeypatch, app)
    calls = []
    import_calls = []

    class FakeProvider:
        name = "tikhub"

        def collect(self, request, caps):
            calls.append({"request": dict(request), "caps": caps.to_dict()})
            if len(calls) == 1:
                return WeiboCollectionBundle(
                    provider="tikhub",
                    keywords=["小米SU7交付争议"],
                    posts=[
                        {
                            "content_id": "1",
                            "content": "小米SU7交付争议",
                            "author": "user-1",
                            "source_keyword": "小米SU7交付争议",
                        }
                    ],
                    comments=[],
                )
            return WeiboCollectionBundle(
                provider="tikhub",
                keywords=["小米SU7交付争议", "交付争议"],
                posts=[
                    {
                        "content_id": str(index),
                        "content": f"小米SU7交付争议 post {index}",
                        "author": f"user-{index % 5}",
                        "source_keyword": "小米SU7交付争议" if index % 2 else "交付争议",
                    }
                    for index in range(25)
                ],
                comments=[
                    {
                        "comment_id": str(index),
                        "note_id": str(index % 25),
                        "content": "交付争议评论",
                    }
                    for index in range(90)
                ],
            )

    async def fake_import_records(paths, dsn, relevant_only=True):
        import_calls.append([str(path) for path in paths])
        if len(import_calls) == 1:
            return {
                "provider": "tikhub",
                "counts": {
                    "seen_posts": 1,
                    "seen_comments": 0,
                    "post_inserted": 1,
                    "comment_inserted": 0,
                    "weibo_note": 1,
                    "weibo_note_comment": 0,
                },
            }
        return {
            "provider": "tikhub",
            "counts": {
                "seen_posts": 25,
                "seen_comments": 90,
                "post_inserted": 24,
                "comment_inserted": 90,
                "weibo_note": 25,
                "weibo_note_comment": 90,
            },
        }

    async def fake_check_data_readiness(query, minimum_total=1, minimum_tables=1, platforms=None):
        return {
            "success": True,
            "query": query,
            "status": "ready",
            "data_ready": True,
            "total_matches": 25,
            "matched_tables": 2,
            "checks": [],
            "errors": [],
        }

    monkeypatch.setattr(app, "select_weibo_provider", lambda _settings: FakeProvider())
    monkeypatch.setattr(app, "import_weibo_bundle", fake_import_records)
    monkeypatch.setattr(app, "check_data_readiness", fake_check_data_readiness)

    response = app.app.test_client().post(
        "/api/crawl/tasks",
        json={
            "analysis_query": "分析小米SU7交付争议最近三个月微博舆情风险",
            "data_request": {
                "eventOrIssue": "交付争议",
                "affectedSubject": "小米SU7",
            },
        },
    )

    payload = response.get_json()
    assert payload["task"]["status"] == "reportable"
    assert len(calls) == 2
    assert payload["task"]["bundle_metadata"]["collection_rounds"][0]["strategy"] == "default"
    assert payload["task"]["bundle_metadata"]["collection_rounds"][1]["strategy"] == "broaden_keywords"
    assert payload["task"]["import_result"]["counts"]["seen_posts"] == 26
    assert payload["task"]["import_result"]["counts"]["comment_inserted"] == 90
    assert payload["task"]["import_result"]["counts"]["weibo_note_comment"] == 90


def test_create_crawl_task_records_insufficient_after_bounded_fallback(monkeypatch):
    import app

    _set_weibo_caps(monkeypatch, app)
    calls = []

    class FakeProvider:
        name = "tikhub"

        def collect(self, request, caps):
            calls.append({"request": dict(request), "caps": caps.to_dict()})
            return WeiboCollectionBundle(
                provider="tikhub",
                keywords=["小米SU7交付争议"],
                posts=[
                    {
                        "content_id": "1",
                        "content": "小米SU7交付争议",
                        "author": "user-1",
                        "source_keyword": "小米SU7交付争议",
                    }
                ],
                comments=[],
            )

    async def fake_import_records(paths, dsn, relevant_only=True):
        return {
            "provider": "tikhub",
            "counts": {
                "seen_posts": 1,
                "seen_comments": 0,
                "weibo_note": 1,
                "weibo_note_comment": 0,
            },
        }

    async def fake_check_data_readiness(query, minimum_total=1, minimum_tables=1, platforms=None):
        return {
            "success": True,
            "query": query,
            "status": "ready",
            "data_ready": True,
            "total_matches": 1,
            "matched_tables": 1,
            "checks": [],
            "errors": [],
        }

    monkeypatch.setattr(app, "select_weibo_provider", lambda _settings: FakeProvider())
    monkeypatch.setattr(app, "import_weibo_bundle", fake_import_records)
    monkeypatch.setattr(app, "check_data_readiness", fake_check_data_readiness)

    response = app.app.test_client().post(
        "/api/crawl/tasks",
        json={
            "analysis_query": "分析小米SU7交付争议最近三个月微博舆情风险",
            "data_request": {
                "eventOrIssue": "交付争议",
                "affectedSubject": "小米SU7",
            },
        },
    )

    payload = response.get_json()
    assert payload["task"]["status"] == "insufficient_data"
    assert len(calls) == 3
    assert payload["task"]["bundle_metadata"]["fallback_stop_reason"] == "insufficient_after_fallback"
    assert len(payload["task"]["bundle_metadata"]["collection_rounds"]) == 3


def test_create_crawl_task_preserves_posts_per_keyword_cap_across_fallback(monkeypatch):
    import app

    _set_weibo_caps(monkeypatch, app)
    monkeypatch.setattr(app.settings, "WEIBO_DATA_MAX_KEYWORDS", 2, raising=False)
    monkeypatch.setattr(app.settings, "WEIBO_DATA_MAX_POSTS_PER_KEYWORD", 2, raising=False)
    calls = []

    class FakeProvider:
        name = "tikhub"

        def collect(self, request, caps):
            call_index = len(calls)
            calls.append({"request": dict(request), "caps": caps.to_dict()})
            return WeiboCollectionBundle(
                provider="tikhub",
                keywords=["小米SU7交付争议"],
                posts=[
                    {
                        "content_id": str(call_index * 10 + index),
                        "content": f"小米SU7交付争议 post {call_index}-{index}",
                        "author": f"user-{call_index}-{index}",
                        "source_keyword": "小米SU7交付争议",
                    }
                    for index in range(2)
                ],
                comments=[],
            )

    async def fake_import_records(paths, dsn, relevant_only=True):
        return {
            "provider": "tikhub",
            "counts": {
                "seen_posts": 2,
                "seen_comments": 0,
                "weibo_note": 2,
                "weibo_note_comment": 0,
            },
        }

    async def fake_check_data_readiness(query, minimum_total=1, minimum_tables=1, platforms=None):
        return {
            "success": True,
            "query": query,
            "status": "ready",
            "data_ready": True,
            "total_matches": 2,
            "matched_tables": 1,
            "checks": [],
            "errors": [],
        }

    monkeypatch.setattr(app, "select_weibo_provider", lambda _settings: FakeProvider())
    monkeypatch.setattr(app, "import_weibo_bundle", fake_import_records)
    monkeypatch.setattr(app, "check_data_readiness", fake_check_data_readiness)

    response = app.app.test_client().post(
        "/api/crawl/tasks",
        json={
            "analysis_query": "分析小米SU7交付争议最近三个月微博舆情风险",
            "data_request": {
                "eventOrIssue": "交付争议",
                "affectedSubject": "小米SU7",
            },
        },
    )

    payload = response.get_json()
    assert len(calls) == 3
    assert payload["task"]["bundle_metadata"]["post_count"] == 2


def test_create_crawl_task_expand_comments_round_uses_hard_cap(monkeypatch):
    import app

    _set_weibo_caps(monkeypatch, app, selected_posts=12, comments_per_post=2)
    monkeypatch.setattr(app.settings, "WEIBO_DATA_MAX_COMMENTS_PER_POST", 1, raising=False)
    monkeypatch.setattr(app.settings, "WEIBO_DATA_MAX_COMMENTS_PER_POST_HARD", 2, raising=False)
    calls = []

    class FakeProvider:
        name = "tikhub"

        def collect(self, request, caps):
            calls.append(caps.to_dict())
            return WeiboCollectionBundle(
                provider="tikhub",
                keywords=["小米SU7交付争议"],
                posts=[
                    {
                        "content_id": "1",
                        "content": "小米SU7交付争议",
                        "author": "user-1",
                        "source_keyword": "小米SU7交付争议",
                    }
                ],
                comments=[],
            )

    async def fake_import_records(paths, dsn, relevant_only=True):
        return {"provider": "tikhub", "counts": {"seen_posts": 1, "seen_comments": 0}}

    async def fake_check_data_readiness(query, minimum_total=1, minimum_tables=1, platforms=None):
        return {
            "success": True,
            "query": query,
            "status": "ready",
            "data_ready": True,
            "total_matches": 1,
            "matched_tables": 1,
            "checks": [],
            "errors": [],
        }

    monkeypatch.setattr(app, "select_weibo_provider", lambda _settings: FakeProvider())
    monkeypatch.setattr(app, "import_weibo_bundle", fake_import_records)
    monkeypatch.setattr(app, "check_data_readiness", fake_check_data_readiness)

    app.app.test_client().post(
        "/api/crawl/tasks",
        json={
            "analysis_query": "分析小米SU7交付争议最近三个月微博舆情风险",
            "data_request": {
                "eventOrIssue": "交付争议",
                "affectedSubject": "小米SU7",
            },
        },
    )

    assert [call["max_comments_per_post"] for call in calls] == [1, 1, 2]
    assert all(call["max_comments_per_post_hard"] == 2 for call in calls)


def test_create_crawl_task_marks_failed_when_tikhub_provider_errors(monkeypatch):
    import app

    _set_weibo_caps(monkeypatch, app)
    analysis_started = []

    class FakeProvider:
        name = "tikhub"

        def collect(self, request, caps):
            raise RuntimeError("TikHub quota exceeded")

    class FakeSearchOrchestrator:
        def start_search(self, query):
            analysis_started.append(query)
            return {"success": True}

    monkeypatch.setattr(app, "select_weibo_provider", lambda _settings: FakeProvider())
    monkeypatch.setattr(app, "search_orchestrator", FakeSearchOrchestrator())

    response = app.app.test_client().post(
        "/api/crawl/tasks",
        json={
            "analysis_query": "分析小米SU7交付争议最近三个月微博舆情风险",
            "data_request": {
                "eventOrIssue": "交付争议",
                "affectedSubject": "小米SU7",
            },
        },
    )

    assert response.status_code == 500
    payload = response.get_json()
    assert payload["success"] is False
    assert payload["task"]["status"] == "failed"
    assert "quota exceeded" in payload["task"]["error_message"]
    assert analysis_started == []


def test_create_crawl_task_records_manual_cloud_handoff(monkeypatch):
    import app

    monkeypatch.setattr(app.settings, "WEIBO_DATA_PROVIDER", "mediacrawler", raising=False)
    monkeypatch.setattr(app.settings, "WEIBO_DATA_MAX_KEYWORDS", 6, raising=False)
    monkeypatch.setattr(app.settings, "WEIBO_DATA_MAX_POSTS_PER_KEYWORD", 30, raising=False)
    monkeypatch.setattr(app.settings, "WEIBO_DATA_MAX_SELECTED_POSTS", 12, raising=False)
    monkeypatch.setattr(app.settings, "WEIBO_DATA_MAX_COMMENTS_PER_POST", 20, raising=False)
    monkeypatch.setattr(app.settings, "WEIBO_DATA_MAX_COMMENTS_PER_POST_HARD", 30, raising=False)
    monkeypatch.setattr(app.settings, "WEIBO_DATA_ALLOW_SUBCOMMENTS", False, raising=False)

    response = app.app.test_client().post(
        "/api/crawl/tasks",
        json={
            "analysis_query": "分析小米SU7交付争议最近三个月微博舆情风险",
            "data_request": "小米SU7交付争议",
        },
    )

    assert response.status_code == 202
    payload = response.get_json()
    assert payload["success"] is True
    assert payload["task"]["status"] == "manual_action_required"
    assert payload["task"]["analysis_query"] == "分析小米SU7交付争议最近三个月微博舆情风险"
    assert payload["task"]["data_request"] == "小米SU7交付争议"
    assert payload["task"]["platforms"] == ["wb"]
    assert payload["task"]["provider"] == "mediacrawler"
    assert payload["task"]["caps"]["max_keywords"] == 6
    assert "微博采集任务" in payload["task"]["next_action"]
    assert payload["task"]["status_url"].startswith("/api/crawl/tasks/")


def test_create_crawl_task_submits_to_configured_cloud_endpoint(monkeypatch):
    import app

    requests = []

    def fake_post(url, json=None, timeout=None, headers=None):
        requests.append(
            {
                "url": url,
                "json": json,
                "timeout": timeout,
                "headers": headers,
            }
        )

        class Response:
            def raise_for_status(self):
                return None

            def json(self):
                return {"job_id": "cloud_job_123", "status_url": "https://crawler/jobs/123"}

        return Response()

    monkeypatch.setattr(app.settings, "CRAWLER_CLOUD_ENDPOINT", "https://crawler/jobs")
    monkeypatch.setattr(app.settings, "CRAWLER_CLOUD_API_KEY", "secret-key")
    monkeypatch.setattr(app.settings, "WEIBO_DATA_PROVIDER", "mediacrawler", raising=False)
    monkeypatch.setattr(app.settings, "WEIBO_DATA_MAX_KEYWORDS", 6, raising=False)
    monkeypatch.setattr(app.settings, "WEIBO_DATA_MAX_POSTS_PER_KEYWORD", 30, raising=False)
    monkeypatch.setattr(app.settings, "WEIBO_DATA_MAX_SELECTED_POSTS", 12, raising=False)
    monkeypatch.setattr(app.settings, "WEIBO_DATA_MAX_COMMENTS_PER_POST", 20, raising=False)
    monkeypatch.setattr(app.settings, "WEIBO_DATA_MAX_COMMENTS_PER_POST_HARD", 30, raising=False)
    monkeypatch.setattr(app.settings, "WEIBO_DATA_ALLOW_SUBCOMMENTS", False, raising=False)
    monkeypatch.setattr(app.requests, "post", fake_post)

    response = app.app.test_client().post(
        "/api/crawl/tasks",
        json={
            "analysis_query": "分析小米SU7交付争议最近三个月微博舆情风险",
            "data_request": "小米SU7交付争议",
        },
    )

    assert response.status_code == 202
    payload = response.get_json()
    assert payload["task"]["status"] == "queued"
    assert payload["task"]["cloud_job_id"] == "cloud_job_123"
    assert payload["task"]["cloud_status_url"] == "https://crawler/jobs/123"
    assert payload["task"]["provider"] == "mediacrawler"
    assert payload["task"]["caps"]["max_selected_posts"] == 12
    assert requests == [
        {
            "url": "https://crawler/jobs",
            "json": {
                "task_id": payload["task"]["task_id"],
                "analysis_query": "分析小米SU7交付争议最近三个月微博舆情风险",
                "data_request": "小米SU7交付争议",
                "platforms": ["wb"],
                "provider": "mediacrawler",
                "caps": {
                    "max_keywords": 6,
                    "max_posts_per_keyword": 30,
                    "max_selected_posts": 12,
                    "max_comments_per_post": 20,
                    "max_comments_per_post_hard": 30,
                    "allow_subcomments": False,
                },
            },
            "timeout": 10,
            "headers": {"authorization": "Bearer secret-key"},
        }
    ]


def test_get_crawl_task_returns_saved_contract(monkeypatch):
    import app

    monkeypatch.setattr(app.settings, "WEIBO_DATA_PROVIDER", "mediacrawler", raising=False)

    client = app.app.test_client()
    created = client.post(
        "/api/crawl/tasks",
        json={"analysis_query": "Acme | sentiment", "data_request": "Acme social posts"},
    ).get_json()

    response = client.get(created["task"]["status_url"])

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["success"] is True
    assert payload["task"]["task_id"] == created["task"]["task_id"]
    assert payload["task"]["status"] == "manual_action_required"
    assert payload["task"]["platforms"] == ["wb"]
    assert payload["task"]["provider"] == "mediacrawler"


def test_get_crawl_task_polls_cloud_status_and_imports_completed_output(
    monkeypatch,
    tmp_path,
):
    import app

    output = tmp_path / "remote-posts.json"
    output.write_text(
        '{"provider":"mediacrawler","posts":[{"content_id":"1","content":"post"}],"comments":[{"comment_id":"10","note_id":"1","content":"comment"}]}',
        encoding="utf-8",
    )

    def fake_post(_url, json=None, timeout=None, headers=None):
        class Response:
            def raise_for_status(self):
                return None

            def json(self):
                return {"job_id": "remote_job", "status_url": "https://crawler/jobs/remote_job"}

        return Response()

    def fake_get(url, timeout=None, headers=None):
        assert url == "https://crawler/jobs/remote_job"
        assert timeout == 10
        assert headers == {"authorization": "Bearer secret-key"}

        class Response:
            def raise_for_status(self):
                return None

            def json(self):
                return {"status": "completed", "output_files": [str(output)]}

        return Response()

    async def fake_import_records(paths, dsn, relevant_only=True):
        return {
            "inputs": [str(path) for path in paths],
            "counts": {"seen_posts": 1, "seen_comments": 1, "weibo_note": 1, "weibo_note_comment": 1},
        }

    async def fake_check_data_readiness(query, minimum_total=1, minimum_tables=1, platforms=None):
        return {
            "success": True,
            "query": query,
            "status": "ready",
            "data_ready": True,
            "total_matches": 1,
            "matched_tables": 1,
            "minimum_total": minimum_total,
            "minimum_tables": minimum_tables,
            "message": "Imported MediaCrawler data is ready.",
            "terms": ["navos"],
            "checks": [],
            "errors": [],
        }

    monkeypatch.setattr(app.settings, "CRAWLER_CLOUD_ENDPOINT", "https://crawler/jobs")
    monkeypatch.setattr(app.settings, "CRAWLER_CLOUD_API_KEY", "secret-key")
    monkeypatch.setattr(app.requests, "post", fake_post)
    monkeypatch.setattr(app.requests, "get", fake_get)
    monkeypatch.setattr(app, "import_weibo_bundle", fake_import_records)
    monkeypatch.setattr(app, "check_data_readiness", fake_check_data_readiness)

    client = app.app.test_client()
    created = client.post(
        "/api/crawl/tasks",
        json={"analysis_query": "Navos | reputation", "data_request": "Navos posts"},
    ).get_json()

    response = client.get(created["task"]["status_url"])

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["task"]["status"] == "insufficient_data"
    assert payload["task"]["import_result"]["counts"]["weibo_note"] == 1
    assert payload["task"]["readiness"]["data_ready"] is True
    assert payload["task"]["reportability"]["can_start_analysis"] is False


def test_crawl_task_callback_imports_output_and_marks_task_imported(monkeypatch, tmp_path):
    import app

    imported = []

    async def fake_import_records(paths, dsn, relevant_only=True):
        imported.append(
            {
                "paths": [str(path) for path in paths],
                "dsn": dsn,
                "relevant_only": relevant_only,
            }
        )
        return {"counts": {"seen_posts": 1, "seen_comments": 1, "weibo_note": 1, "weibo_note_comment": 1}}

    async def fake_check_data_readiness(query, minimum_total=1, minimum_tables=1, platforms=None):
        return {
            "success": True,
            "query": query,
            "status": "ready",
            "data_ready": True,
            "total_matches": 1,
            "matched_tables": 1,
            "minimum_total": minimum_total,
            "minimum_tables": minimum_tables,
            "message": "Imported MediaCrawler data is ready.",
            "terms": ["navos"],
            "checks": [],
            "errors": [],
        }

    output = tmp_path / "posts.json"
    output.write_text(
        '{"provider":"mediacrawler","posts":[{"content_id":"1","content":"post"}],"comments":[{"comment_id":"10","note_id":"1","content":"comment"}]}',
        encoding="utf-8",
    )
    monkeypatch.setattr(app.settings, "WEIBO_DATA_PROVIDER", "mediacrawler", raising=False)
    monkeypatch.setattr(app.settings, "WEIBO_DATA_MAX_SELECTED_POSTS", 30, raising=False)
    monkeypatch.setattr(app.settings, "WEIBO_DATA_MAX_COMMENTS_PER_POST", 90, raising=False)
    monkeypatch.setattr(app.settings, "WEIBO_DATA_MAX_COMMENTS_PER_POST_HARD", 90, raising=False)
    monkeypatch.setattr(app, "import_weibo_bundle", fake_import_records)
    monkeypatch.setattr(app, "check_data_readiness", fake_check_data_readiness)

    client = app.app.test_client()
    created = client.post(
        "/api/crawl/tasks",
        json={"analysis_query": "Navos | reputation", "data_request": "Navos posts"},
    ).get_json()

    response = client.post(
        f"/api/crawl/tasks/{created['task']['task_id']}/complete",
        json={"output_files": [str(output)]},
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["success"] is True
    assert payload["task"]["status"] == "insufficient_data"
    assert payload["task"]["import_result"]["counts"]["weibo_note"] == 1
    assert payload["task"]["readiness"]["status"] == "ready"
    assert payload["task"]["readiness"]["data_ready"] is True
    assert payload["task"]["reportability"]["can_start_analysis"] is False
    assert imported == [
        {
            "paths": [str(output)],
            "dsn": app.build_mediacrawler_dsn(),
            "relevant_only": True,
        }
    ]


def test_crawl_task_callback_can_mark_reportable_after_import(monkeypatch, tmp_path):
    import json
    import app

    async def fake_import_records(paths, dsn, relevant_only=True):
        return {
            "counts": {
                "seen_posts": 25,
                "seen_comments": 90,
                "weibo_note": 25,
                "weibo_note_comment": 90,
            }
        }

    async def fake_check_data_readiness(query, minimum_total=1, minimum_tables=1, platforms=None):
        return {
            "success": True,
            "query": query,
            "status": "ready",
            "data_ready": True,
            "total_matches": 25,
            "matched_tables": 2,
            "minimum_total": minimum_total,
            "minimum_tables": minimum_tables,
            "message": "Imported data is ready.",
            "terms": ["小米SU7"],
            "checks": [],
            "errors": [],
        }

    output = tmp_path / "reportable-posts.json"
    output.write_text(
        json.dumps(
            {
                "provider": "mediacrawler",
                "posts": [
                    {
                        "content_id": str(index),
                        "content": f"小米SU7交付争议 post {index}",
                        "author": f"user-{index % 5}",
                        "source_keyword": "小米SU7交付争议" if index % 2 else "交付争议",
                    }
                    for index in range(25)
                ],
                "comments": [
                    {
                        "comment_id": str(index),
                        "note_id": str(index % 25),
                        "content": "交付争议评论",
                    }
                    for index in range(90)
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(app.settings, "WEIBO_DATA_PROVIDER", "mediacrawler", raising=False)
    monkeypatch.setattr(app.settings, "WEIBO_DATA_MAX_SELECTED_POSTS", 30, raising=False)
    monkeypatch.setattr(app.settings, "WEIBO_DATA_MAX_COMMENTS_PER_POST", 90, raising=False)
    monkeypatch.setattr(app.settings, "WEIBO_DATA_MAX_COMMENTS_PER_POST_HARD", 90, raising=False)
    monkeypatch.setattr(app, "import_weibo_bundle", fake_import_records)
    monkeypatch.setattr(app, "check_data_readiness", fake_check_data_readiness)

    client = app.app.test_client()
    created = client.post(
        "/api/crawl/tasks",
        json={"analysis_query": "小米SU7交付争议", "data_request": "小米SU7交付争议"},
    ).get_json()

    response = client.post(
        f"/api/crawl/tasks/{created['task']['task_id']}/complete",
        json={"output_files": [str(output)]},
    )

    payload = response.get_json()
    assert payload["task"]["status"] == "reportable"
    assert payload["task"]["reportability"]["can_start_analysis"] is True
    assert payload["task"]["evidence_manifest"]["counts"]["posts"] == 25
    assert payload["task"]["evidence_manifest"]["counts"]["comments"] == 90


def test_create_crawl_task_requires_analysis_query():
    import app

    response = app.app.test_client().post(
        "/api/crawl/tasks",
        json={"data_request": "Need more posts"},
    )

    assert response.status_code == 400
    payload = response.get_json()
    assert payload["success"] is False
    assert "analysis query" in payload["message"].lower()
