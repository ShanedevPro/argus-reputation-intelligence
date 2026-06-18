import json
import threading
import time
from pathlib import Path
from datetime import timedelta


def _write_ready_engine(tmp_path, artifact_name, **evidence_overrides):
    report = tmp_path / f"{artifact_name}.md"
    return _write_ready_report(report, artifact_name, **evidence_overrides)


def _write_ready_report(report, artifact_engine_name, **evidence_overrides):
    report.write_text(f"# {artifact_engine_name}", encoding="utf-8")
    evidence_payload = {
        "engine_name": artifact_engine_name,
        "query": "王鹤棣 不舒服文学",
        "report_file": str(report),
        "evidence_status": "ready",
        "source_count": 1,
        "evidence_items": [{"title": f"{artifact_engine_name} source"}],
        "generated_at": "2026-06-08T00:00:00",
    }
    evidence_payload.update(evidence_overrides)
    report.with_suffix(".evidence.json").write_text(
        json.dumps(evidence_payload),
        encoding="utf-8",
    )
    return str(report)


def _patch_engine_output_dirs(monkeypatch, tmp_path, orchestrator_module):
    engine_dirs = {}
    for engine_name in ("insight", "media", "query"):
        engine_dir = tmp_path / f"{engine_name}_engine_streamlit_reports"
        engine_dir.mkdir(exist_ok=True)
        engine_dirs[engine_name] = engine_dir
        monkeypatch.setitem(
            orchestrator_module.ENGINE_OUTPUT_DIRS,
            engine_name,
            str(engine_dir),
        )
    return engine_dirs


def test_api_search_uses_backend_orchestrator_instead_of_streamlit_fanout(monkeypatch):
    import app

    calls = []
    monkeypatch.setattr(app.settings, "WEIBO_DATA_PROVIDER", "mediacrawler", raising=False)

    class FakeOrchestrator:
        def start_search(self, query, **kwargs):
            calls.append({"query": query, "kwargs": kwargs})
            return {
                "success": True,
                "task_id": "search_1",
                "query": query,
                "status_url": "/api/search/status/search_1",
            }

    def fail_if_streamlit_called(*args, **kwargs):
        raise AssertionError("Streamlit /api/search fanout should not be called")

    monkeypatch.setattr(app, "search_orchestrator", FakeOrchestrator(), raising=False)
    monkeypatch.setattr(app.requests, "post", fail_if_streamlit_called)

    response = app.app.test_client().post(
        "/api/search",
        json={"query": "清华大学苏世民书院"},
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["success"] is True
    assert payload["task_id"] == "search_1"
    assert payload["query"] == "清华大学苏世民书院"
    assert payload["status_url"] == "/api/search/status/search_1"
    assert calls == [
        {
            "query": "清华大学苏世民书院",
            "kwargs": {"engine_artifacts": {}},
        }
    ]


def test_api_search_blocks_tikhub_analysis_without_reportable_data_prep(monkeypatch):
    import app

    calls = []

    class FakeOrchestrator:
        def start_search(self, query):
            calls.append(query)
            return {"success": True, "task_id": "search_1"}

    monkeypatch.setattr(app.settings, "WEIBO_DATA_PROVIDER", "tikhub", raising=False)
    monkeypatch.setattr(app, "search_orchestrator", FakeOrchestrator(), raising=False)

    response = app.app.test_client().post(
        "/api/search",
        json={"query": "分析小米SU7交付争议最近三个月微博舆情风险"},
    )

    assert response.status_code == 409
    payload = response.get_json()
    assert payload["success"] is False
    assert payload["status"] == "needs_weibo_data"
    assert "微博数据准备" in payload["message"]
    assert calls == []


def test_api_search_allows_analysis_with_reportable_data_prep_task(monkeypatch):
    import app

    calls = []
    query = "分析小米SU7交付争议最近三个月微博舆情风险"
    task = app.crawl_tasks.create_task(
        analysis_query=query,
        data_request='{"eventOrIssue":"交付争议","affectedSubject":"小米SU7"}',
        provider="tikhub",
    )
    task.mark_reportable(
        import_result={"counts": {"weibo_note": 25, "weibo_note_comment": 90}},
        readiness={"data_ready": True},
        reportability={"status": "reportable", "can_start_analysis": True},
        bundle_metadata={"raw_post_count": 25},
        evidence_manifest={
            "counts": {"posts": 25, "comments": 90},
            "sample_boundary": {"platform": "weibo"},
        },
    )

    class FakeOrchestrator:
        def start_search(self, query, **kwargs):
            calls.append({"query": query, "kwargs": kwargs})
            return {
                "success": True,
                "task_id": "search_1",
                "query": query,
                "status_url": "/api/search/status/search_1",
            }

    monkeypatch.setattr(app.settings, "WEIBO_DATA_PROVIDER", "tikhub", raising=False)
    monkeypatch.setattr(app, "search_orchestrator", FakeOrchestrator(), raising=False)

    response = app.app.test_client().post(
        "/api/search",
        json={
            "query": query,
            "data_prep_task_id": task.task_id,
            "engine_artifacts": {"insight": {"output_file": "insight.md"}},
        },
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["success"] is True
    assert payload["task_id"] == "search_1"
    assert payload["data_prep_task_id"] == task.task_id
    assert calls == [
        {
            "query": query,
            "kwargs": {
                "research_request": {
                    "eventOrIssue": "交付争议",
                    "affectedSubject": "小米SU7",
                },
                "evidence_manifest": {
                    "counts": {"posts": 25, "comments": 90},
                    "sample_boundary": {"platform": "weibo"},
                },
                "data_prep_task_id": task.task_id,
                "engine_artifacts": {"insight": {"output_file": "insight.md"}},
            },
        }
    ]


def test_api_search_passes_engine_artifacts_without_data_prep(monkeypatch):
    import app

    calls = []

    class FakeOrchestrator:
        def start_search(self, query, **kwargs):
            calls.append({"query": query, "kwargs": kwargs})
            return {"success": True, "task_id": "search_1"}

    monkeypatch.setattr(app.settings, "WEIBO_DATA_PROVIDER", "mediacrawler", raising=False)
    monkeypatch.setattr(app, "search_orchestrator", FakeOrchestrator(), raising=False)

    response = app.app.test_client().post(
        "/api/search",
        json={
            "query": "王鹤棣 不舒服文学",
            "engine_artifacts": {"insight": {"output_file": "insight.md"}},
        },
    )

    assert response.status_code == 200
    assert calls == [
        {
            "query": "王鹤棣 不舒服文学",
            "kwargs": {"engine_artifacts": {"insight": {"output_file": "insight.md"}}},
        }
    ]


def test_api_search_rejects_non_object_engine_artifacts(monkeypatch):
    import app

    calls = []

    class FakeOrchestrator:
        def start_search(self, query, **kwargs):
            calls.append({"query": query, "kwargs": kwargs})
            return {"success": True, "task_id": "search_1"}

    monkeypatch.setattr(app.settings, "WEIBO_DATA_PROVIDER", "mediacrawler", raising=False)
    monkeypatch.setattr(app, "search_orchestrator", FakeOrchestrator(), raising=False)

    response = app.app.test_client().post(
        "/api/search",
        json={"query": "王鹤棣 不舒服文学", "engine_artifacts": ["insight"]},
    )

    assert response.status_code == 400
    payload = response.get_json()
    assert payload["success"] is False
    assert payload["message"] == "engine_artifacts must be an object"
    assert calls == []


def test_api_search_returns_400_when_engine_artifacts_are_invalid(monkeypatch):
    import app

    class FakeOrchestrator:
        def start_search(self, query, **kwargs):
            assert kwargs == {"engine_artifacts": {"forum": {"output_file": "forum.md"}}}
            return {"success": False, "message": "unknown engine artifact: forum"}

    monkeypatch.setattr(app.settings, "WEIBO_DATA_PROVIDER", "mediacrawler", raising=False)
    monkeypatch.setattr(app, "search_orchestrator", FakeOrchestrator(), raising=False)

    response = app.app.test_client().post(
        "/api/search",
        json={
            "query": "王鹤棣 不舒服文学",
            "engine_artifacts": {"forum": {"output_file": "forum.md"}},
        },
    )

    assert response.status_code == 400
    assert response.get_json()["message"] == "unknown engine artifact: forum"


def test_api_search_blocks_non_tikhub_data_prep_task(monkeypatch):
    import app

    calls = []
    query = "分析小米SU7交付争议最近三个月微博舆情风险"
    task = app.crawl_tasks.create_task(
        analysis_query=query,
        data_request="小米SU7交付争议",
        provider="mediacrawler",
    )
    task.mark_reportable(
        import_result={"counts": {"weibo_note": 25, "weibo_note_comment": 90}},
        readiness={"data_ready": True},
        reportability={"status": "reportable", "can_start_analysis": True},
        bundle_metadata={"raw_post_count": 25},
    )

    class FakeOrchestrator:
        def start_search(self, query):
            calls.append(query)
            return {"success": True, "task_id": "search_1"}

    monkeypatch.setattr(app.settings, "WEIBO_DATA_PROVIDER", "tikhub", raising=False)
    monkeypatch.setattr(app, "search_orchestrator", FakeOrchestrator(), raising=False)

    response = app.app.test_client().post(
        "/api/search",
        json={"query": query, "data_prep_task_id": task.task_id},
    )

    assert response.status_code == 409
    payload = response.get_json()
    assert payload["status"] == "needs_weibo_data"
    assert "tikhub" in payload["message"].lower()
    assert calls == []


def test_api_search_blocks_reportable_status_without_reportability_status(monkeypatch):
    import app

    calls = []
    query = "分析小米SU7交付争议最近三个月微博舆情风险"
    task = app.crawl_tasks.create_task(
        analysis_query=query,
        data_request="小米SU7交付争议",
        provider="tikhub",
    )
    task.mark_reportable(
        import_result={"counts": {"weibo_note": 25, "weibo_note_comment": 90}},
        readiness={"data_ready": True},
        reportability={"status": "insufficient_data", "can_start_analysis": True},
        bundle_metadata={"raw_post_count": 25},
    )

    class FakeOrchestrator:
        def start_search(self, query):
            calls.append(query)
            return {"success": True, "task_id": "search_1"}

    monkeypatch.setattr(app.settings, "WEIBO_DATA_PROVIDER", "tikhub", raising=False)
    monkeypatch.setattr(app, "search_orchestrator", FakeOrchestrator(), raising=False)

    response = app.app.test_client().post(
        "/api/search",
        json={"query": query, "data_prep_task_id": task.task_id},
    )

    assert response.status_code == 409
    payload = response.get_json()
    assert payload["status"] == "needs_weibo_data"
    assert calls == []


def test_api_search_blocks_missing_mismatched_and_non_reportable_tasks(monkeypatch):
    import app

    calls = []
    query = "分析小米SU7交付争议最近三个月微博舆情风险"
    task = app.crawl_tasks.create_task(
        analysis_query="另一个查询",
        data_request="小米SU7交付争议",
        provider="tikhub",
    )

    class FakeOrchestrator:
        def start_search(self, query):
            calls.append(query)
            return {"success": True, "task_id": "search_1"}

    monkeypatch.setattr(app.settings, "WEIBO_DATA_PROVIDER", "tikhub", raising=False)
    monkeypatch.setattr(app, "search_orchestrator", FakeOrchestrator(), raising=False)

    client = app.app.test_client()
    missing = client.post(
        "/api/search",
        json={"query": query, "data_prep_task_id": "crawl_missing"},
    )
    mismatch = client.post(
        "/api/search",
        json={"query": query, "data_prep_task_id": task.task_id},
    )

    assert missing.status_code == 409
    assert missing.get_json()["message"] == "未找到对应的微博数据准备任务。"
    assert mismatch.status_code == 409
    assert "不匹配" in mismatch.get_json()["message"]
    assert calls == []


def test_api_search_status_returns_orchestrator_task(monkeypatch):
    import app

    class FakeOrchestrator:
        def get_status(self, task_id):
            assert task_id == "search_1"
            return {
                "success": True,
                "task_id": "search_1",
                "status": "completed",
                "report_task_id": "report_1",
            }

    monkeypatch.setattr(app, "search_orchestrator", FakeOrchestrator(), raising=False)

    response = app.app.test_client().get("/api/search/status/search_1")

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["success"] is True
    assert payload["status"] == "completed"
    assert payload["report_task_id"] == "report_1"


def test_search_status_refreshes_running_engine_timestamps():
    from utils.search_orchestrator import SearchTask, SearchOrchestrator

    task = SearchTask(task_id="search_1", query="王鹤棣 不舒服文学")
    orchestrator = SearchOrchestrator(
        engine_runners={},
        reset_report_baseline=lambda: None,
        start_report_task=lambda query, **kwargs: {"success": True, "task_id": "report_1"},
        run_async=False,
    )
    stale = task.created_at - timedelta(minutes=10)
    task.status = "running"
    task.updated_at = stale
    for status in task.engines.values():
        status.mark_running()
        status.updated_at = stale

    refreshed = orchestrator._status_snapshot(task)

    assert refreshed["updated_at"] != stale.isoformat()
    assert refreshed["engines"]["insight"]["updated_at"] != stale.isoformat()
    assert refreshed["engines"]["media"]["updated_at"] != stale.isoformat()
    assert refreshed["engines"]["query"]["updated_at"] != stale.isoformat()


def test_search_orchestrator_resets_baseline_runs_engines_and_starts_report(monkeypatch):
    from utils.search_orchestrator import SearchOrchestrator
    import utils.search_orchestrator as orchestrator_module

    events = []

    def reset_baseline():
        events.append("reset")

    def make_runner(engine_name):
        def run(query):
            events.append(f"{engine_name}:{query}")
            return f"/tmp/{engine_name}.md"

        return run

    def start_report(query):
        events.append(f"report:{query}")
        return {"success": True, "task_id": "report_1"}

    def load_summary(_path):
        return {
            "evidence_status": "ready",
            "source_count": 1,
            "evidence_items": [{"title": "source A", "url": "https://example.com/a"}],
        }

    monkeypatch.setattr(orchestrator_module, "load_evidence_summary", load_summary)

    orchestrator = SearchOrchestrator(
        engine_runners={
            "insight": make_runner("insight"),
            "media": make_runner("media"),
            "query": make_runner("query"),
        },
        reset_report_baseline=reset_baseline,
        start_report_task=start_report,
        run_async=False,
    )

    started = orchestrator.start_search("清华大学苏世民书院")
    status = orchestrator.get_status(started["task_id"])

    assert events == [
        "reset",
        "insight:清华大学苏世民书院",
        "media:清华大学苏世民书院",
        "query:清华大学苏世民书院",
        "report:清华大学苏世民书院",
    ]
    assert status["status"] == "completed"
    assert status["data_ready"] is True
    assert status["report_task_id"] == "report_1"
    assert not any(key.startswith("fact_") for key in status)
    assert status["engines"]["insight"]["output_file"] == "/tmp/insight.md"
    assert status["engines"]["insight"]["evidence_status"] == "ready"
    assert not any(key.startswith("fact_") for key in status["engines"]["insight"])
    assert status["engines"]["media"]["output_file"] == "/tmp/media.md"
    assert status["engines"]["query"]["output_file"] == "/tmp/query.md"


def test_search_orchestrator_resumes_completed_insight_artifact(monkeypatch, tmp_path):
    from utils.search_orchestrator import SearchOrchestrator
    import utils.search_orchestrator as orchestrator_module

    engine_dirs = _patch_engine_output_dirs(monkeypatch, tmp_path, orchestrator_module)
    report = engine_dirs["insight"] / "insight.md"
    report.write_text("# Insight", encoding="utf-8")
    report.with_suffix(".evidence.json").write_text(
        json.dumps(
                {
                    "engine_name": "insight",
                    "query": "王鹤棣 不舒服文学",
                    "report_file": str(report),
                    "evidence_status": "ready",
                    "source_count": 3,
                "evidence_items": [{"title": "sample"}],
                "generated_at": "2026-06-08T00:00:00",
            }
        ),
        encoding="utf-8",
    )
    report.with_suffix(".sentiment.json").write_text(
        json.dumps(
            {
                "analysis_performed": True,
                "total_analyzed": 2,
                "sentiment_distribution": {"中性": 1, "负面": 1},
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    calls = []
    orchestrator = SearchOrchestrator(
        engine_runners={
            "insight": lambda query: calls.append("insight") or str(report),
            "media": lambda query: calls.append("media")
            or _write_ready_report(engine_dirs["media"] / "media.md", "media"),
            "query": lambda query: calls.append("query")
            or _write_ready_report(engine_dirs["query"] / "query.md", "query"),
        },
        reset_report_baseline=lambda: None,
        start_report_task=lambda query, **kwargs: {"success": True, "task_id": "report_1", **kwargs},
        run_async=False,
        engine_concurrency="sequential",
    )

    started = orchestrator.start_search(
        "王鹤棣 不舒服文学",
        evidence_manifest={"type": "weibo_evidence_manifest"},
        engine_artifacts={"insight": {"output_file": str(report)}},
    )

    status = orchestrator.get_status(started["task_id"])
    assert calls == ["media", "query"]
    assert status["engines"]["insight"]["status"] == "completed"
    assert status["engines"]["insight"]["evidence_status"] == "ready"
    assert status["engines"]["insight"]["output_file"] == str(report)
    assert status["status"] == "completed"


def test_search_orchestrator_rejects_unknown_resume_engine(tmp_path):
    from utils.search_orchestrator import SearchOrchestrator

    orchestrator = SearchOrchestrator(run_async=False)
    started = orchestrator.start_search(
        "王鹤棣 不舒服文学",
        engine_artifacts={"forum": {"output_file": str(tmp_path / "forum.md")}},
    )
    assert started["success"] is False
    assert "unknown engine" in started["message"]


def test_search_orchestrator_rejects_resume_artifact_without_ready_evidence(
    monkeypatch,
    tmp_path,
):
    from utils.search_orchestrator import SearchOrchestrator
    import utils.search_orchestrator as orchestrator_module

    engine_dirs = _patch_engine_output_dirs(monkeypatch, tmp_path, orchestrator_module)
    report = engine_dirs["insight"] / "insight.md"
    report.write_text("# Insight", encoding="utf-8")
    report.with_suffix(".evidence.json").write_text(
        json.dumps(
            {
                "engine_name": "insight",
                "report_file": str(report),
                "evidence_status": "no_data",
                "source_count": 0,
            }
        ),
        encoding="utf-8",
    )
    orchestrator = SearchOrchestrator(run_async=False)
    started = orchestrator.start_search(
        "王鹤棣 不舒服文学",
        engine_artifacts={"insight": {"output_file": str(report)}},
    )
    assert started["success"] is False
    assert "ready evidence" in started["message"]


def test_search_orchestrator_rejects_resume_artifact_for_different_query(monkeypatch, tmp_path):
    from utils.search_orchestrator import SearchOrchestrator
    import utils.search_orchestrator as orchestrator_module

    engine_dirs = _patch_engine_output_dirs(monkeypatch, tmp_path, orchestrator_module)
    report = Path(
        _write_ready_report(
            engine_dirs["insight"] / "insight.md",
            "insight",
            query="小米汽车 碰撞起火",
        )
    )
    orchestrator = SearchOrchestrator(run_async=False)

    started = orchestrator.start_search(
        "王鹤棣 不舒服文学",
        engine_artifacts={"insight": {"output_file": str(report)}},
    )

    assert started["success"] is False
    assert "query does not match" in started["message"]


def test_search_orchestrator_accepts_resume_artifact_with_compact_event_query(
    monkeypatch,
    tmp_path,
):
    from utils.search_orchestrator import SearchOrchestrator
    import utils.search_orchestrator as orchestrator_module

    engine_dirs = _patch_engine_output_dirs(monkeypatch, tmp_path, orchestrator_module)
    report = Path(
        _write_ready_report(
            engine_dirs["insight"] / "insight.md",
            "insight",
            query="王鹤棣 亲爱的客栈2026 不舒服文学 我当时确实不舒服",
        )
    )
    calls = []
    orchestrator = SearchOrchestrator(
        engine_runners={
            "insight": lambda _query: calls.append("insight") or str(report),
            "media": lambda _query: calls.append("media")
            or _write_ready_report(engine_dirs["media"] / "media.md", "media"),
            "query": lambda _query: calls.append("query")
            or _write_ready_report(engine_dirs["query"] / "query.md", "query"),
        },
        reset_report_baseline=lambda: None,
        start_report_task=lambda query, **kwargs: {"success": True, "task_id": "report_1", **kwargs},
        run_async=False,
    )

    started = orchestrator.start_search(
        "王鹤棣在《亲爱的客栈2026》中因颁奖感到不适并发微博回应（我当时确实不舒服）引发不舒服文学出圈",
        engine_artifacts={"insight": {"output_file": str(report)}},
    )

    status = orchestrator.get_status(started["task_id"])
    assert calls == ["media", "query"]
    assert status["engines"]["insight"]["status"] == "completed"
    assert status["status"] == "completed"


def test_search_orchestrator_concurrent_resume_skips_completed_artifact(monkeypatch, tmp_path):
    from utils.search_orchestrator import SearchOrchestrator
    import utils.search_orchestrator as orchestrator_module

    engine_dirs = _patch_engine_output_dirs(monkeypatch, tmp_path, orchestrator_module)
    calls = []
    orchestrator = SearchOrchestrator(
        engine_runners={
            "insight": lambda query: calls.append("insight")
            or _write_ready_report(engine_dirs["insight"] / "insight-run.md", "insight"),
            "media": lambda query: calls.append("media")
            or _write_ready_report(engine_dirs["media"] / "media.md", "media"),
            "query": lambda query: calls.append("query")
            or _write_ready_report(engine_dirs["query"] / "query.md", "query"),
        },
        reset_report_baseline=lambda: None,
        start_report_task=lambda query, **kwargs: {"success": True, "task_id": "report_1"},
        run_async=False,
        engine_concurrency="concurrent",
    )
    insight_report = Path(
        _write_ready_report(engine_dirs["insight"] / "insight.md", "insight")
    )

    started = orchestrator.start_search(
        "王鹤棣 不舒服文学",
        engine_artifacts={"insight": {"output_file": str(insight_report)}},
    )

    status = orchestrator.get_status(started["task_id"])
    assert sorted(calls) == ["media", "query"]
    assert status["engines"]["insight"]["status"] == "completed"
    assert status["engines"]["insight"]["output_file"] == str(insight_report)
    assert status["status"] == "completed"


def test_search_orchestrator_resets_baseline_before_using_resumed_artifact(monkeypatch, tmp_path):
    from utils.search_orchestrator import SearchOrchestrator
    import utils.search_orchestrator as orchestrator_module

    events = []
    engine_dirs = _patch_engine_output_dirs(monkeypatch, tmp_path, orchestrator_module)
    insight_report = Path(
        _write_ready_report(engine_dirs["insight"] / "insight.md", "insight")
    )

    def reset_baseline():
        events.append("reset")

    def make_runner(engine_name):
        def run(_query):
            events.append(f"run:{engine_name}")
            return _write_ready_report(
                engine_dirs[engine_name] / f"{engine_name}.md",
                engine_name,
            )

        return run

    def start_report(_query, **_kwargs):
        events.append("report")
        return {"success": True, "task_id": "report_1"}

    orchestrator = SearchOrchestrator(
        engine_runners={
            "insight": lambda _query: events.append("run:insight") or str(insight_report),
            "media": make_runner("media"),
            "query": make_runner("query"),
        },
        reset_report_baseline=reset_baseline,
        start_report_task=start_report,
        run_async=False,
        engine_concurrency="sequential",
    )

    started = orchestrator.start_search(
        "王鹤棣 不舒服文学",
        engine_artifacts={"insight": {"output_file": str(insight_report)}},
    )

    status = orchestrator.get_status(started["task_id"])
    assert events == ["reset", "run:media", "run:query", "report"]
    assert status["engines"]["insight"]["status"] == "completed"
    assert status["engines"]["insight"]["output_file"] == str(insight_report)
    assert status["status"] == "completed"


def test_reset_report_baseline_excludes_resumed_artifact(monkeypatch, tmp_path):
    from types import SimpleNamespace

    import ReportEngine.flask_interface as report_interface
    import utils.search_orchestrator as orchestrator_module

    monkeypatch.chdir(tmp_path)
    insight_dir = tmp_path / "insight_engine_streamlit_reports"
    insight_dir.mkdir()
    insight_report = insight_dir / "insight.md"
    insight_report.write_text("# Insight", encoding="utf-8")

    baseline_data = {}

    class FakeFileBaseline:
        def __init__(self):
            self.baseline_data = baseline_data

        def initialize_baseline(self, directories):
            self.baseline_data.update(
                {
                    engine: len(list(Path(directory).glob("*.md")))
                    if Path(directory).exists()
                    else 0
                    for engine, directory in directories.items()
                }
            )
            return dict(self.baseline_data)

        def _save_baseline(self):
            baseline_data.update(self.baseline_data)

    fake_agent = SimpleNamespace(file_baseline=FakeFileBaseline())

    monkeypatch.setattr(report_interface, "report_agent", fake_agent)

    orchestrator_module._reset_report_baseline(
        exclude_files={"insight": [str(insight_report)]}
    )

    assert baseline_data["insight"] == 0


def test_reset_report_baseline_does_not_exclude_outside_engine_directory(monkeypatch, tmp_path):
    from types import SimpleNamespace

    import ReportEngine.flask_interface as report_interface
    import utils.search_orchestrator as orchestrator_module

    monkeypatch.chdir(tmp_path)
    insight_dir = tmp_path / "insight_engine_streamlit_reports"
    insight_dir.mkdir()
    in_dir_report = insight_dir / "insight.md"
    in_dir_report.write_text("# Insight", encoding="utf-8")
    outside_report = tmp_path / "outside.md"
    outside_report.write_text("# Outside", encoding="utf-8")

    baseline_data = {}

    class FakeFileBaseline:
        def __init__(self):
            self.baseline_data = baseline_data

        def initialize_baseline(self, directories):
            self.baseline_data.update(
                {
                    engine: len(list(Path(directory).glob("*.md")))
                    if Path(directory).exists()
                    else 0
                    for engine, directory in directories.items()
                }
            )
            return dict(self.baseline_data)

        def _save_baseline(self):
            baseline_data.update(self.baseline_data)

    monkeypatch.setattr(
        report_interface,
        "report_agent",
        SimpleNamespace(file_baseline=FakeFileBaseline()),
    )

    orchestrator_module._reset_report_baseline(
        exclude_files={"insight": [str(outside_report)]}
    )

    assert baseline_data["insight"] == 1


def test_search_orchestrator_ignores_preflight_for_resumed_engine(monkeypatch, tmp_path):
    from utils.search_orchestrator import SearchOrchestrator
    import utils.search_orchestrator as orchestrator_module

    calls = []
    engine_dirs = _patch_engine_output_dirs(monkeypatch, tmp_path, orchestrator_module)
    insight_report = Path(_write_ready_report(engine_dirs["insight"] / "insight.md", "insight"))
    orchestrator = SearchOrchestrator(
        engine_runners={
            "insight": lambda _query: calls.append("insight") or str(insight_report),
            "media": lambda _query: calls.append("media")
            or _write_ready_report(engine_dirs["media"] / "media.md", "media"),
            "query": lambda _query: calls.append("query")
            or _write_ready_report(engine_dirs["query"] / "query.md", "query"),
        },
        reset_report_baseline=lambda: None,
        start_report_task=lambda query, **kwargs: {"success": True, "task_id": "report_1"},
        engine_preflight=lambda: {"insight": "Missing Python package SQLAlchemy."},
        run_async=False,
    )

    started = orchestrator.start_search(
        "王鹤棣 不舒服文学",
        engine_artifacts={"insight": {"output_file": str(insight_report)}},
    )

    status = orchestrator.get_status(started["task_id"])
    assert started["success"] is True
    assert calls == ["media", "query"]
    assert status["status"] == "completed"
    assert status["engines"]["insight"]["status"] == "completed"
    assert status["engines"]["insight"]["error_message"] == ""


def test_search_orchestrator_rejects_resume_artifact_with_wrong_engine_name(
    monkeypatch,
    tmp_path,
):
    from utils.search_orchestrator import SearchOrchestrator
    import utils.search_orchestrator as orchestrator_module

    engine_dirs = _patch_engine_output_dirs(monkeypatch, tmp_path, orchestrator_module)
    report = Path(
        _write_ready_report(
            engine_dirs["insight"] / "insight.md",
            "insight",
            engine_name="media",
        )
    )
    orchestrator = SearchOrchestrator(run_async=False)

    started = orchestrator.start_search(
        "王鹤棣 不舒服文学",
        engine_artifacts={"insight": {"output_file": str(report)}},
    )

    assert started["success"] is False
    assert "engine_name" in started["message"]


def test_search_orchestrator_rejects_resume_artifact_with_mismatched_report_file(
    monkeypatch,
    tmp_path,
):
    from utils.search_orchestrator import SearchOrchestrator
    import utils.search_orchestrator as orchestrator_module

    engine_dirs = _patch_engine_output_dirs(monkeypatch, tmp_path, orchestrator_module)
    report = Path(
        _write_ready_report(
            engine_dirs["insight"] / "insight.md",
            "insight",
            report_file=str(engine_dirs["insight"] / "other.md"),
        )
    )
    orchestrator = SearchOrchestrator(run_async=False)

    started = orchestrator.start_search(
        "王鹤棣 不舒服文学",
        engine_artifacts={"insight": {"output_file": str(report)}},
    )

    assert started["success"] is False
    assert "report_file" in started["message"]


def test_search_orchestrator_rejects_resume_artifact_outside_engine_directory(monkeypatch, tmp_path):
    from utils.search_orchestrator import SearchOrchestrator
    import utils.search_orchestrator as orchestrator_module

    engine_dir = tmp_path / "insight_engine_streamlit_reports"
    engine_dir.mkdir()
    monkeypatch.setitem(
        orchestrator_module.ENGINE_OUTPUT_DIRS,
        "insight",
        str(engine_dir),
    )
    outside_report = Path(_write_ready_report(tmp_path / "insight.md", "insight"))
    orchestrator = SearchOrchestrator(run_async=False)

    started = orchestrator.start_search(
        "王鹤棣 不舒服文学",
        engine_artifacts={"insight": {"output_file": str(outside_report)}},
    )

    assert started["success"] is False
    assert "output directory" in started["message"]


def test_search_orchestrator_accepts_relative_report_file_for_same_resolved_artifact(
    monkeypatch,
    tmp_path,
):
    from utils.search_orchestrator import SearchOrchestrator
    import utils.search_orchestrator as orchestrator_module

    monkeypatch.chdir(tmp_path)
    engine_dir = tmp_path / "insight_engine_streamlit_reports"
    engine_dir.mkdir()
    monkeypatch.setitem(
        orchestrator_module.ENGINE_OUTPUT_DIRS,
        "insight",
        "insight_engine_streamlit_reports",
    )
    report = engine_dir / "insight.md"
    _write_ready_report(
        report,
        "insight",
        report_file="insight_engine_streamlit_reports/insight.md",
    )
    orchestrator = SearchOrchestrator(
        engine_runners={
            "insight": lambda _query: str(report),
            "media": lambda _query: _write_ready_engine(tmp_path, "media"),
            "query": lambda _query: _write_ready_engine(tmp_path, "query"),
        },
        reset_report_baseline=lambda: None,
        start_report_task=lambda query, **kwargs: {"success": True, "task_id": "report_1"},
        run_async=False,
    )

    started = orchestrator.start_search(
        "王鹤棣 不舒服文学",
        engine_artifacts={
            "insight": {"output_file": "insight_engine_streamlit_reports/insight.md"}
        },
    )

    status = orchestrator.get_status(started["task_id"])
    assert started["success"] is True
    assert status["status"] == "completed"
    assert status["engines"]["insight"]["output_file"] == (
        "insight_engine_streamlit_reports/insight.md"
    )


def test_search_orchestrator_rejects_non_object_engine_artifacts():
    from utils.search_orchestrator import SearchOrchestrator

    orchestrator = SearchOrchestrator(run_async=False)

    for engine_artifacts in (["insight"], []):
        started = orchestrator.start_search(
            "王鹤棣 不舒服文学",
            engine_artifacts=engine_artifacts,
        )

        assert started["success"] is False
        assert "engine_artifacts" in started["message"]


def test_search_orchestrator_defaults_to_sequential_engine_runs(monkeypatch):
    monkeypatch.setenv("ARGUS_SEARCH_ENGINE_CONCURRENCY", "sequential")

    from utils.search_orchestrator import SearchOrchestrator
    import utils.search_orchestrator as orchestrator_module

    events = []

    def make_runner(engine_name):
        def run(_query):
            events.append(engine_name)
            return f"/tmp/{engine_name}.md"

        return run

    monkeypatch.setattr(
        orchestrator_module,
        "load_evidence_summary",
        lambda _path: {
            "evidence_status": "ready",
            "source_count": 1,
            "evidence_items": [{"snippet": "ok"}],
        },
    )

    orchestrator = SearchOrchestrator(
        engine_runners={
            name: make_runner(name)
            for name in ("insight", "media", "query")
        },
        reset_report_baseline=lambda: None,
        start_report_task=lambda query, **kwargs: {"success": True, "task_id": "report_1"},
    )

    started = orchestrator.start_search("王鹤棣 不舒服文学")
    status = orchestrator.get_status(started["task_id"])
    deadline = time.time() + 3
    while time.time() < deadline and status["status"] != "completed":
        time.sleep(0.05)
        status = orchestrator.get_status(started["task_id"])

    assert status["status"] == "completed"
    assert events == ["insight", "media", "query"]


def test_search_orchestrator_default_search_returns_background_task_but_runs_engines_sequentially(monkeypatch):
    monkeypatch.setenv("ARGUS_SEARCH_ENGINE_CONCURRENCY", "sequential")

    from utils.search_orchestrator import SearchOrchestrator
    import utils.search_orchestrator as orchestrator_module

    release_first_engine = threading.Event()
    events = []

    def make_runner(engine_name):
        def run(_query):
            events.append(engine_name)
            if engine_name == "insight":
                release_first_engine.wait(timeout=5)
            return f"/tmp/{engine_name}.md"

        return run

    monkeypatch.setattr(
        orchestrator_module,
        "load_evidence_summary",
        lambda _path: {
            "evidence_status": "ready",
            "source_count": 1,
            "evidence_items": [{"snippet": "ok"}],
        },
    )

    orchestrator = SearchOrchestrator(
        engine_runners={
            name: make_runner(name)
            for name in ("insight", "media", "query")
        },
        reset_report_baseline=lambda: None,
        start_report_task=lambda query, **kwargs: {"success": True, "task_id": "report_1"},
    )

    started = orchestrator.start_search("王鹤棣 不舒服文学")
    try:
        assert started["status"] == "running"

        deadline = time.time() + 2
        while time.time() < deadline and events != ["insight"]:
            time.sleep(0.05)
        assert events == ["insight"]

        release_first_engine.set()
        deadline = time.time() + 3
        status = orchestrator.get_status(started["task_id"])
        while time.time() < deadline and status["status"] != "completed":
            time.sleep(0.05)
            status = orchestrator.get_status(started["task_id"])

        assert status["status"] == "completed"
        assert events == ["insight", "media", "query"]
    finally:
        release_first_engine.set()


def test_search_orchestrator_keeps_engine_query_clean_when_manifest_is_present(monkeypatch):
    from utils.search_orchestrator import SearchOrchestrator
    import utils.search_orchestrator as orchestrator_module

    received = {}

    def make_runner(engine_name):
        def run(query):
            received[engine_name] = query
            return f"/tmp/{engine_name}.md"

        return run

    monkeypatch.setattr(
        orchestrator_module,
        "load_evidence_summary",
        lambda _path: {
            "evidence_status": "ready",
            "source_count": 1,
            "evidence_items": [{"snippet": "ok"}],
        },
    )

    orchestrator = SearchOrchestrator(
        engine_runners={
            name: make_runner(name)
            for name in ("insight", "media", "query")
        },
        reset_report_baseline=lambda: None,
        start_report_task=lambda query, **kwargs: {"success": True, "task_id": "report_1"},
        run_async=False,
    )

    started = orchestrator.start_search(
        "王鹤棣 不舒服文学",
        research_request={"affectedSubject": "王鹤棣"},
        evidence_manifest={
            "counts": {"posts": 29, "comments": 115},
            "sample_boundary": {"platform": "weibo"},
        },
        data_prep_task_id="crawl_1",
    )
    status = orchestrator.get_status(started["task_id"])

    assert status["status"] == "completed"
    assert received == {
        "query": "王鹤棣 不舒服文学",
        "media": "王鹤棣 不舒服文学",
        "insight": "王鹤棣 不舒服文学",
    }
    assert status["research_brief"]["enabled"] is True
    assert "query" in status["research_brief"]["engine_briefs"]
    assert status["data_prep_task_id"] == "crawl_1"


def test_report_structure_context_does_not_pollute_engine_state_query(monkeypatch):
    monkeypatch.setenv("QUERY_ENGINE_API_KEY", "test-key")
    monkeypatch.setenv("QUERY_ENGINE_MODEL_NAME", "test-model")
    monkeypatch.setenv("TAVILY_API_KEY", "test-tavily")

    from QueryEngine.nodes.report_structure_node import ReportStructureNode
    from QueryEngine.state.state import State

    messages = []

    class FakeLLM:
        def stream_invoke_to_string(self, _system_prompt, message):
            messages.append(message)
            return '[{"title":"事实核验","content":"核验事件边界"}]'

    node = ReportStructureNode(
        FakeLLM(),
        "王鹤棣 不舒服文学",
        structure_input="王鹤棣 不舒服文学\n\n<ARGUS_ENGINE_CONTEXT>Profile lens: 艺人明星舆情</ARGUS_ENGINE_CONTEXT>",
    )

    state = node.mutate_state(state=State())

    assert "ARGUS_ENGINE_CONTEXT" in messages[0]
    assert state.query == "王鹤棣 不舒服文学"
    assert state.report_title == "关于'王鹤棣 不舒服文学'的深度研究报告"
    assert "ARGUS_ENGINE_CONTEXT" not in state.report_title


def test_search_orchestrator_passes_weibo_manifest_to_report_engine(monkeypatch):
    from utils.search_orchestrator import SearchOrchestrator
    import utils.search_orchestrator as orchestrator_module

    received = {}

    monkeypatch.setattr(
        orchestrator_module,
        "load_evidence_summary",
        lambda _path: {
            "evidence_status": "ready",
            "source_count": 1,
            "evidence_items": [{"snippet": "ok"}],
        },
    )

    def start_report(query, **kwargs):
        received["query"] = query
        received["kwargs"] = kwargs
        return {"success": True, "task_id": "report_1"}

    orchestrator = SearchOrchestrator(
        engine_runners={
            name: (lambda _query, engine_name=name: f"/tmp/{engine_name}.md")
            for name in ("insight", "media", "query")
        },
        reset_report_baseline=lambda: None,
        start_report_task=start_report,
        run_async=False,
    )

    orchestrator.start_search(
        "王鹤棣 不舒服文学",
        evidence_manifest={
            "provider": "tikhub",
            "counts": {"posts": 29, "comments": 115},
            "sample_boundary": {"platform": "weibo"},
        },
    )

    assert received["query"] == "王鹤棣 不舒服文学"
    assert received["kwargs"]["data_bundles"][0]["type"] == "weibo_evidence_manifest"
    assert received["kwargs"]["data_bundles"][0]["counts"]["posts"] == 29


def test_search_orchestrator_merges_insight_sentiment_into_report_manifest(monkeypatch, tmp_path):
    from utils.search_orchestrator import SearchOrchestrator
    import utils.search_orchestrator as orchestrator_module
    import json

    received = {}

    def make_runner(engine_name):
        def run(_query):
            output_file = tmp_path / f"{engine_name}.md"
            output_file.write_text("report", encoding="utf-8")
            if engine_name == "insight":
                output_file.with_suffix(".sentiment.json").write_text(
                    json.dumps(
                        {
                            "total_analyzed": 843,
                            "sentiment_distribution": {
                                "非常负面": 228,
                                "中性": 281,
                            },
                        },
                        ensure_ascii=False,
                    ),
                    encoding="utf-8",
                )
            return str(output_file)

        return run

    monkeypatch.setattr(
        orchestrator_module,
        "load_evidence_summary",
        lambda _path: {
            "evidence_status": "ready",
            "source_count": 1,
            "evidence_items": [{"snippet": "ok"}],
        },
    )

    def start_report(query, **kwargs):
        received["query"] = query
        received["kwargs"] = kwargs
        return {"success": True, "task_id": "report_1"}

    orchestrator = SearchOrchestrator(
        engine_runners={
            name: make_runner(name)
            for name in ("insight", "media", "query")
        },
        reset_report_baseline=lambda: None,
        start_report_task=start_report,
        run_async=False,
    )

    orchestrator.start_search(
        "王鹤棣 不舒服文学",
        evidence_manifest={
            "provider": "tikhub",
            "counts": {"posts": 29, "comments": 115},
            "sample_boundary": {"platform": "weibo"},
        },
    )

    manifest = received["kwargs"]["data_bundles"][0]
    assert manifest["sentiment_analysis"]["total_analyzed"] == 843
    assert manifest["sentiment_analysis"]["sentiment_distribution"]["非常负面"] == 228


def test_search_orchestrator_passes_exact_engine_files_to_report_engine(monkeypatch, tmp_path):
    from utils.search_orchestrator import SearchOrchestrator
    import utils.search_orchestrator as orchestrator_module

    received = {}

    monkeypatch.setattr(
        orchestrator_module,
        "load_evidence_summary",
        lambda _path: {
            "evidence_status": "ready",
            "source_count": 1,
            "evidence_items": [{"snippet": "ok"}],
        },
    )

    def make_runner(engine_name):
        def run(_query):
            output_file = tmp_path / f"{engine_name}.md"
            output_file.write_text(f"# {engine_name}", encoding="utf-8")
            return str(output_file)

        return run

    def start_report(query, **kwargs):
        received["query"] = query
        received["kwargs"] = kwargs
        return {"success": True, "task_id": "report_1"}

    orchestrator = SearchOrchestrator(
        engine_runners={
            name: make_runner(name)
            for name in ("insight", "media", "query")
        },
        reset_report_baseline=lambda: None,
        start_report_task=start_report,
        run_async=False,
    )

    orchestrator.start_search("王鹤棣 不舒服文学")

    assert received["kwargs"]["engine_files"] == {
        "insight": str(tmp_path / "insight.md"),
        "media": str(tmp_path / "media.md"),
        "query": str(tmp_path / "query.md"),
    }


def test_report_engine_uses_explicit_engine_files_instead_of_latest(monkeypatch, tmp_path):
    from types import SimpleNamespace
    from ReportEngine import flask_interface

    selected = {
        "insight": tmp_path / "insight-selected.md",
        "media": tmp_path / "media-selected.md",
        "query": tmp_path / "query-selected.md",
    }
    latest = {
        "insight": tmp_path / "insight-latest.md",
        "media": tmp_path / "media-latest.md",
        "query": tmp_path / "query-latest.md",
    }
    for engine_paths in (selected, latest):
        for path in engine_paths.values():
            path.write_text(path.name, encoding="utf-8")

    loaded_paths = {}

    class FakeReportAgent:
        def check_input_files(self, *_args):
            return {
                "ready": True,
                "latest_files": {
                    **{engine: str(path) for engine, path in latest.items()},
                    "forum": "logs/forum.log",
                },
                "missing_files": [],
            }

        def load_input_files(self, file_paths):
            loaded_paths.update(file_paths)
            return {"reports": ["query", "media", "insight"], "forum_logs": ""}

        def generate_report(self, **_kwargs):
            return {"html_content": "<html></html>"}

    monkeypatch.setattr(flask_interface, "report_agent", FakeReportAgent())
    monkeypatch.setattr(flask_interface, "current_task", None)
    monkeypatch.setattr(flask_interface, "tasks_registry", {})
    monkeypatch.setattr(flask_interface, "auto_export_report_artifacts", lambda _task: None)

    result = flask_interface.start_report_task(
        query="王鹤棣 不舒服文学",
        auto_export=False,
        engine_files={engine: str(path) for engine, path in selected.items()},
    )

    assert result["success"] is True
    task_id = result["task_id"]
    deadline = time.time() + 3
    while time.time() < deadline:
        task = flask_interface.tasks_registry[task_id]
        if task.status in {"completed", "error"}:
            break
        time.sleep(0.05)

    assert flask_interface.tasks_registry[task_id].status == "completed"
    assert loaded_paths == {
        "insight": str(selected["insight"]),
        "media": str(selected["media"]),
        "query": str(selected["query"]),
        "forum": "logs/forum.log",
    }


def test_search_orchestrator_passes_profile_id_to_report_engine(monkeypatch):
    from utils.search_orchestrator import SearchOrchestrator
    import utils.search_orchestrator as orchestrator_module

    received = {}

    monkeypatch.setattr(
        orchestrator_module,
        "load_evidence_summary",
        lambda _path: {
            "evidence_status": "ready",
            "source_count": 1,
            "evidence_items": [{"snippet": "ok"}],
        },
    )

    def start_report(query, **kwargs):
        received["query"] = query
        received["kwargs"] = kwargs
        return {"success": True, "task_id": "report_1"}

    orchestrator = SearchOrchestrator(
        engine_runners={
            name: (lambda _query, engine_name=name: f"/tmp/{engine_name}.md")
            for name in ("insight", "media", "query")
        },
        reset_report_baseline=lambda: None,
        start_report_task=start_report,
        run_async=False,
    )

    orchestrator.start_search(
        "小米SU7 高速碰撞起火事故",
        research_request={
            "eventOrIssue": "高速碰撞起火事故争议",
            "affectedSubject": "小米SU7",
            "profileId": "enterprise_pr",
        },
        evidence_manifest={
            "provider": "tikhub",
            "research_request": {
                "eventOrIssue": "高速碰撞起火事故争议",
                "affectedSubject": "小米SU7",
                "profileId": "enterprise_pr",
            },
            "counts": {"posts": 68, "comments": 53},
            "sample_boundary": {"platform": "weibo"},
        },
    )

    manifest = received["kwargs"]["data_bundles"][0]
    assert manifest["type"] == "weibo_evidence_manifest"
    assert manifest["research_request"]["profileId"] == "enterprise_pr"


def test_search_orchestrator_runs_forum_synthesis_before_report(monkeypatch):
    from utils.search_orchestrator import SearchOrchestrator
    import utils.search_orchestrator as orchestrator_module

    events = []

    monkeypatch.setattr(
        orchestrator_module,
        "load_evidence_summary",
        lambda _path: {
            "evidence_status": "ready",
            "source_count": 1,
            "evidence_items": [{"snippet": "ok"}],
        },
    )

    def runner(engine_name):
        def run(_query):
            events.append(f"engine:{engine_name}")
            return f"/tmp/{engine_name}.md"

        return run

    def forum_synthesis(task):
        events.append("forum")
        return {"success": True, "forum_log_path": "logs/forum.log"}

    def report(query, **kwargs):
        events.append("report")
        return {"success": True, "task_id": "report_1"}

    orchestrator = SearchOrchestrator(
        engine_runners={
            name: runner(name)
            for name in ("insight", "media", "query")
        },
        reset_report_baseline=lambda: None,
        start_report_task=report,
        forum_synthesis_runner=forum_synthesis,
        run_async=False,
    )

    started = orchestrator.start_search("王鹤棣 不舒服文学")
    status = orchestrator.get_status(started["task_id"])

    assert status["status"] == "completed"
    assert events[-2:] == ["forum", "report"]
    assert status["forum_synthesis"]["forum_log_path"] == "logs/forum.log"


def test_reset_report_baseline_initializes_report_engine_on_demand(monkeypatch):
    from types import SimpleNamespace

    import ReportEngine.flask_interface as report_interface
    import utils.search_orchestrator as orchestrator_module

    events = []
    fake_agent = SimpleNamespace(
        file_baseline=SimpleNamespace(
            initialize_baseline=lambda directories: events.append(dict(directories))
        )
    )

    def initialize_report_engine():
        events.append("initialize")
        report_interface.report_agent = fake_agent
        return True

    monkeypatch.setattr(report_interface, "report_agent", None)
    monkeypatch.setattr(
        report_interface,
        "initialize_report_engine",
        initialize_report_engine,
    )

    orchestrator_module._reset_report_baseline()

    assert events == ["initialize", orchestrator_module.ENGINE_OUTPUT_DIRS]


def test_search_orchestrator_blocks_report_when_an_engine_fails():
    from utils.search_orchestrator import SearchOrchestrator

    report_calls = []

    def ok_runner(query):
        return "/tmp/ok.md"

    def failing_runner(query):
        raise RuntimeError("media failed")

    orchestrator = SearchOrchestrator(
        engine_runners={
            "insight": ok_runner,
            "media": failing_runner,
            "query": ok_runner,
        },
        reset_report_baseline=lambda: None,
        start_report_task=lambda query: report_calls.append(query),
        run_async=False,
    )

    started = orchestrator.start_search("清华大学苏世民书院")
    status = orchestrator.get_status(started["task_id"])

    assert status["status"] == "error"
    assert status["report_task_id"] is None
    assert status["engines"]["media"]["status"] == "error"
    assert "media failed" in status["engines"]["media"]["error_message"]
    assert report_calls == []


def test_search_orchestrator_fails_fast_when_engine_dependencies_are_missing():
    from utils.search_orchestrator import SearchOrchestrator

    calls = []
    report_calls = []

    def runner(query):
        calls.append(query)
        return "/tmp/should-not-run.md"

    orchestrator = SearchOrchestrator(
        engine_runners={"insight": runner, "media": runner, "query": runner},
        reset_report_baseline=lambda: calls.append("reset"),
        start_report_task=lambda query: report_calls.append(query),
        engine_preflight=lambda: {
            "query": "Missing Python package tavily-python.",
            "insight": "Missing Python package SQLAlchemy.",
        },
        run_async=False,
    )

    started = orchestrator.start_search("王鹤棣 不舒服文学")
    status = orchestrator.get_status(started["task_id"])

    assert status["status"] == "error"
    assert "query" in status["error_message"]
    assert "insight" in status["error_message"]
    assert status["report_task_id"] is None
    assert status["engines"]["query"]["status"] == "error"
    assert "tavily-python" in status["engines"]["query"]["error_message"]
    assert status["engines"]["insight"]["status"] == "error"
    assert "SQLAlchemy" in status["engines"]["insight"]["error_message"]
    assert calls == ["reset"]
    assert report_calls == []


def test_search_orchestrator_surfaces_async_engine_failure_while_other_engine_runs():
    from utils.search_orchestrator import SearchOrchestrator

    slow_started = threading.Event()
    release_slow = threading.Event()
    report_calls = []

    def ok_runner(query):
        return "/tmp/ok.md"

    def failing_runner(query):
        raise RuntimeError("query failed")

    def slow_runner(query):
        slow_started.set()
        release_slow.wait(timeout=10)
        return "/tmp/media.md"

    orchestrator = SearchOrchestrator(
        engine_runners={
            "insight": ok_runner,
            "media": slow_runner,
            "query": failing_runner,
        },
        reset_report_baseline=lambda: None,
        start_report_task=lambda query: report_calls.append(query),
        engine_preflight=lambda: {},
        run_async=True,
        engine_concurrency="concurrent",
    )

    started = orchestrator.start_search("王鹤棣 不舒服文学")
    assert slow_started.wait(timeout=2)

    try:
        deadline = time.time() + 2
        status = orchestrator.get_status(started["task_id"])
        while time.time() < deadline and status["status"] != "error":
            time.sleep(0.05)
            status = orchestrator.get_status(started["task_id"])

        assert status["status"] == "error"
        assert "query" in status["error_message"]
        assert status["engines"]["query"]["status"] == "error"
        assert "query failed" in status["engines"]["query"]["error_message"]
        assert status["engines"]["media"]["status"] == "running"
        assert status["report_task_id"] is None
        assert report_calls == []
    finally:
        release_slow.set()


def test_search_orchestrator_marks_hung_async_engine_error_after_timeout():
    from utils.search_orchestrator import SearchOrchestrator

    slow_started = threading.Event()
    release_slow = threading.Event()
    report_calls = []

    def ok_runner(query):
        return "/tmp/ok.md"

    def slow_runner(query):
        slow_started.set()
        release_slow.wait(timeout=10)
        return "/tmp/query.md"

    orchestrator = SearchOrchestrator(
        engine_runners={
            "insight": ok_runner,
            "media": ok_runner,
            "query": slow_runner,
        },
        reset_report_baseline=lambda: None,
        start_report_task=lambda query: report_calls.append(query),
        engine_preflight=lambda: {},
        run_async=True,
        engine_concurrency="concurrent",
        engine_timeout_seconds=0.2,
    )

    started = orchestrator.start_search("王鹤棣 不舒服文学")
    assert slow_started.wait(timeout=2)

    try:
        deadline = time.time() + 3
        status = orchestrator.get_status(started["task_id"])
        while time.time() < deadline and status["status"] != "error":
            time.sleep(0.05)
            status = orchestrator.get_status(started["task_id"])

        time.sleep(0.1)
        status = orchestrator.get_status(started["task_id"])
        assert status["status"] == "error"
        assert "query" in status["error_message"]
        assert "超时" in status["error_message"]
        assert status["engines"]["query"]["status"] == "error"
        assert "timed out" in status["engines"]["query"]["error_message"]
        assert status["report_task_id"] is None
        assert report_calls == []

        release_slow.set()
        deadline = time.time() + 2
        while time.time() < deadline:
            status = orchestrator.get_status(started["task_id"])
            if status["engines"]["query"]["status"] == "completed":
                break
            time.sleep(0.05)

        status = orchestrator.get_status(started["task_id"])
        assert status["status"] == "error"
        assert status["engines"]["query"]["status"] == "error"
        assert status["report_task_id"] is None
        assert report_calls == []
    finally:
        release_slow.set()


def test_search_orchestrator_marks_hung_sequential_engine_error_after_timeout():
    from utils.search_orchestrator import SearchOrchestrator

    slow_started = threading.Event()
    release_slow = threading.Event()
    calls = []
    report_calls = []

    def slow_runner(query):
        calls.append("insight")
        slow_started.set()
        release_slow.wait(timeout=10)
        return "/tmp/insight.md"

    def should_not_run(query):
        calls.append("media")
        return "/tmp/media.md"

    orchestrator = SearchOrchestrator(
        engine_runners={
            "insight": slow_runner,
            "media": should_not_run,
            "query": should_not_run,
        },
        reset_report_baseline=lambda: None,
        start_report_task=lambda query: report_calls.append(query),
        engine_preflight=lambda: {},
        run_async=True,
        engine_concurrency="sequential",
        engine_timeout_seconds=0.2,
    )

    started = orchestrator.start_search("王鹤棣 不舒服文学")
    assert slow_started.wait(timeout=2)

    try:
        deadline = time.time() + 3
        status = orchestrator.get_status(started["task_id"])
        while time.time() < deadline and status["status"] != "error":
            time.sleep(0.05)
            status = orchestrator.get_status(started["task_id"])

        assert status["status"] == "error"
        assert "insight" in status["error_message"]
        assert "超时" in status["error_message"]
        assert status["engines"]["insight"]["status"] == "error"
        assert "timed out" in status["engines"]["insight"]["error_message"]
        assert status["engines"]["media"]["status"] == "pending"
        assert status["engines"]["query"]["status"] == "pending"
        assert report_calls == []
        assert calls == ["insight"]
    finally:
        release_slow.set()


def test_default_engine_runners_apply_local_workload_settings(monkeypatch):
    import types

    import utils.search_orchestrator as orchestrator_module

    created_configs = {}
    research_calls = []

    class FakeSettings:
        def __init__(self, **kwargs):
            created_configs[kwargs["OUTPUT_DIR"]] = kwargs

    class FakeAgent:
        def __init__(self, config):
            self.config = config

        def research(self, query, save_report=True, argus_context=""):
            research_calls.append(
                {
                    "query": query,
                    "save_report": save_report,
                    "argus_context": argus_context,
                    "config": self.config,
                }
            )

    fake_root_settings = types.SimpleNamespace(
        INSIGHT_ENGINE_API_KEY="insight-key",
        INSIGHT_ENGINE_BASE_URL="https://example.test/insight",
        INSIGHT_ENGINE_MODEL_NAME="insight-model",
        MEDIA_ENGINE_API_KEY="media-key",
        MEDIA_ENGINE_BASE_URL="https://example.test/media",
        MEDIA_ENGINE_MODEL_NAME="media-model",
        QUERY_ENGINE_API_KEY="query-key",
        QUERY_ENGINE_BASE_URL="https://example.test/query",
        QUERY_ENGINE_MODEL_NAME="query-model",
        DB_HOST="localhost",
        DB_USER="user",
        DB_PASSWORD="pw",
        DB_NAME="db",
        DB_PORT=5432,
        DB_CHARSET="utf8",
        DB_DIALECT="postgresql",
        SEARCH_TOOL_TYPE="BochaAPI",
        BOCHA_WEB_SEARCH_API_KEY="bocha-key",
        ANSPIRE_API_KEY="anspire-key",
        TAVILY_API_KEY="tavily-key",
        ARGUS_SEARCH_ENGINE_MAX_REFLECTIONS=1,
        ARGUS_SEARCH_ENGINE_MAX_PARAGRAPHS=4,
        ARGUS_INSIGHT_MAX_AUTO_SENTIMENT_SEARCHES=1,
        KEYWORD_OPTIMIZER_MAX_KEYWORDS=6,
    )
    monkeypatch.setattr(
        orchestrator_module,
        "_latest_markdown_file",
        lambda directory: f"/tmp/{directory}.md",
    )

    monkeypatch.setitem(
        __import__("sys").modules,
        "config",
        types.SimpleNamespace(settings=fake_root_settings),
    )
    monkeypatch.setitem(
        __import__("sys").modules,
        "InsightEngine",
        types.SimpleNamespace(DeepSearchAgent=FakeAgent, Settings=FakeSettings),
    )
    monkeypatch.setitem(
        __import__("sys").modules,
        "MediaEngine",
        types.SimpleNamespace(
            DeepSearchAgent=FakeAgent,
            AnspireSearchAgent=FakeAgent,
            TavilySearchAgent=FakeAgent,
            Settings=FakeSettings,
        ),
    )
    monkeypatch.setitem(
        __import__("sys").modules,
        "QueryEngine",
        types.SimpleNamespace(DeepSearchAgent=FakeAgent, Settings=FakeSettings),
    )

    orchestrator_module._run_insight_engine("王鹤棣 不舒服文学", argus_context="ctx")
    orchestrator_module._run_media_engine("王鹤棣 不舒服文学", argus_context="ctx")
    orchestrator_module._run_query_engine("王鹤棣 不舒服文学", argus_context="ctx")

    insight_config = created_configs["insight_engine_streamlit_reports"]
    media_config = created_configs["media_engine_streamlit_reports"]
    query_config = created_configs["query_engine_streamlit_reports"]
    assert insight_config["MAX_REFLECTIONS"] == 1
    assert insight_config["MAX_PARAGRAPHS"] == 4
    assert insight_config["MAX_AUTO_SENTIMENT_SEARCHES"] == 1
    assert insight_config["KEYWORD_OPTIMIZER_MAX_KEYWORDS"] == 6
    assert media_config["MAX_REFLECTIONS"] == 1
    assert media_config["MAX_PARAGRAPHS"] == 4
    assert query_config["MAX_REFLECTIONS"] == 1
    assert query_config["MAX_PARAGRAPHS"] == 4
    assert all(call["argus_context"] == "ctx" for call in research_calls)


def test_search_orchestrator_blocks_report_when_any_engine_is_no_data(monkeypatch):
    from utils.search_orchestrator import SearchOrchestrator
    import utils.search_orchestrator as orchestrator_module

    report_calls = []

    def runner(query):
        return "/tmp/report.md"

    def load_summary(_path):
        return {
            "engine_name": "insight",
            "evidence_status": "no_data",
            "source_count": 0,
            "evidence_items": [],
        }

    monkeypatch.setattr(orchestrator_module, "load_evidence_summary", load_summary)

    orchestrator = SearchOrchestrator(
        engine_runners={"insight": runner, "media": runner, "query": runner},
        reset_report_baseline=lambda: None,
        start_report_task=lambda query: report_calls.append(query),
        run_async=False,
    )

    started = orchestrator.start_search("清华大学苏世民书院")
    status = orchestrator.get_status(started["task_id"])

    assert status["status"] == "blocked"
    assert status["data_ready"] is False
    assert "证据不足" in status["blocked_reason"]
    assert report_calls == []


def test_search_orchestrator_blocks_report_when_insight_has_no_relevant_evidence(monkeypatch):
    from utils.search_orchestrator import SearchOrchestrator
    import utils.search_orchestrator as orchestrator_module

    report_calls = []

    def make_runner(engine_name):
        return lambda _query: f"/tmp/{engine_name}.md"

    def load_summary(path):
        engine_name = Path(path).name.split(".", 1)[0]
        if engine_name == "insight":
            return {
                "engine_name": "insight",
                "evidence_status": "no_data",
                "source_count": 0,
                "evidence_items": [],
            }
        return {
            "engine_name": engine_name,
            "evidence_status": "ready",
            "source_count": 1,
            "evidence_items": [{"evidence_id": "E1", "snippet": "source"}],
        }

    monkeypatch.setattr(orchestrator_module, "load_evidence_summary", load_summary)

    orchestrator = SearchOrchestrator(
        engine_runners={
            "insight": make_runner("insight"),
            "media": make_runner("media"),
            "query": make_runner("query"),
        },
        reset_report_baseline=lambda: None,
        start_report_task=lambda query: report_calls.append(query),
        run_async=False,
    )

    started = orchestrator.start_search("清华大学苏世民书院")
    status = orchestrator.get_status(started["task_id"])

    assert status["status"] == "blocked"
    assert status["data_ready"] is False
    assert status["engines"]["insight"]["evidence_status"] == "no_data"
    assert "insight" in status["blocked_reason"]
    assert report_calls == []


def test_frontend_start_calls_search_api_and_uses_passive_iframe_preview():
    html = Path("templates/index.html").read_text(encoding="utf-8")

    assert "fetch('/api/search'" in html
    assert "preview_only=true" in html
    assert "auto_search=true" not in html


def test_frontend_handles_blocked_search_state():
    html = Path("templates/index.html").read_text(encoding="utf-8")

    assert "data.status === 'blocked'" in html
    assert "证据不足，未启动正式分析" in html
