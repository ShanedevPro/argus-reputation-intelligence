import importlib.util
import json
from pathlib import Path
from argparse import Namespace


ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = ROOT / "scripts" / "argus_backend_profile_smoke.py"


def load_smoke_module():
    spec = importlib.util.spec_from_file_location("argus_backend_profile_smoke", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_smoke_recorder_writes_start_heartbeat_and_exit(tmp_path):
    smoke = load_smoke_module()
    recorder = smoke.SmokeRecorder(tmp_path)

    recorder.write_start({"event": "王鹤棣", "mode": "cached"})
    recorder.set_stage("searching", {"task_id": "search_1"})
    recorder.write_heartbeat()
    recorder.write_exit(exit_code=0, result={"status": "report-ready"})

    started = json.loads((tmp_path / "smoke-started.json").read_text(encoding="utf-8"))
    heartbeat = json.loads((tmp_path / "heartbeat.json").read_text(encoding="utf-8"))
    exited = json.loads((tmp_path / "smoke-exit.json").read_text(encoding="utf-8"))

    assert started["event"] == "王鹤棣"
    assert heartbeat["stage"] == "searching"
    assert heartbeat["details"]["task_id"] == "search_1"
    assert exited["exit_code"] == 0
    assert exited["result"]["status"] == "report-ready"


def test_restore_reportable_crawl_task_preserves_cached_manifest():
    smoke = load_smoke_module()
    from utils.crawl_tasks import CrawlTaskStore

    store = CrawlTaskStore()
    cached_payload = {
        "success": True,
        "task": {
            "analysis_query": "王鹤棣 不舒服文学",
            "data_request": '{"eventOrIssue":"不舒服文学","profileId":"artist_management"}',
            "platforms": ["wb"],
            "provider": "tikhub",
            "caps": {"max_keywords": 6},
            "status": "reportable",
            "import_result": {"counts": {"weibo_note": 42}},
            "readiness": {"data_ready": True},
            "reportability": {"status": "reportable", "can_start_analysis": True},
            "bundle_metadata": {"post_count": 42, "comment_count": 34},
            "evidence_manifest": {
                "counts": {"posts": 42, "comments": 34},
                "research_request": {"profileId": "artist_management"},
            },
        },
    }

    task = smoke.restore_crawl_task_from_payload(cached_payload, store)

    assert task.status == "reportable"
    assert task.provider == "tikhub"
    assert task.analysis_query == "王鹤棣 不舒服文学"
    assert task.reportability["can_start_analysis"] is True
    assert task.evidence_manifest["research_request"]["profileId"] == "artist_management"


def test_build_engine_artifacts_from_direct_args():
    smoke = load_smoke_module()

    artifacts = smoke.build_engine_artifacts_from_args(
        Namespace(
            engine_artifact=["insight=/tmp/insight.md", "media=/tmp/media.md"],
            resume_search_status="",
            resume_engine=[],
        )
    )

    assert artifacts == {
        "insight": {"output_file": "/tmp/insight.md"},
        "media": {"output_file": "/tmp/media.md"},
    }


def test_build_engine_artifacts_rejects_malformed_direct_arg():
    smoke = load_smoke_module()

    try:
        smoke.build_engine_artifacts_from_args(
            Namespace(
                engine_artifact=["insight"],
                resume_search_status="",
                resume_engine=[],
            )
        )
    except ValueError as exc:
        assert "--engine-artifact must use engine=/path/to/report.md" in str(exc)
    else:
        raise AssertionError("expected ValueError")


def test_build_engine_artifacts_from_resume_status(tmp_path):
    smoke = load_smoke_module()
    status_file = tmp_path / "search-status.json"
    status_file.write_text(
        json.dumps(
            {
                "engines": {
                    "insight": {
                        "status": "completed",
                        "evidence_status": "ready",
                        "output_file": "/tmp/insight.md",
                    }
                }
            }
        ),
        encoding="utf-8",
    )

    artifacts = smoke.build_engine_artifacts_from_args(
        Namespace(
            engine_artifact=[],
            resume_search_status=str(status_file),
            resume_engine=["insight"],
        )
    )

    assert artifacts == {"insight": {"output_file": "/tmp/insight.md"}}


def test_build_engine_artifacts_requires_resume_engine_in_status(tmp_path):
    smoke = load_smoke_module()
    status_file = tmp_path / "search-status.json"
    status_file.write_text(json.dumps({"engines": {}}), encoding="utf-8")

    try:
        smoke.build_engine_artifacts_from_args(
            Namespace(
                engine_artifact=[],
                resume_search_status=str(status_file),
                resume_engine=["insight"],
            )
        )
    except ValueError as exc:
        assert "insight is missing from resume status" in str(exc)
    else:
        raise AssertionError("expected ValueError")


def test_build_engine_artifacts_requires_status_when_resume_engine_is_set():
    smoke = load_smoke_module()

    try:
        smoke.build_engine_artifacts_from_args(
            Namespace(
                engine_artifact=[],
                resume_search_status="",
                resume_engine=["insight"],
            )
        )
    except ValueError as exc:
        assert "--resume-search-status is required with --resume-engine" in str(exc)
    else:
        raise AssertionError("expected ValueError")


def test_build_engine_artifacts_requires_ready_resume_status(tmp_path):
    smoke = load_smoke_module()
    status_file = tmp_path / "search-status.json"
    status_file.write_text(
        json.dumps(
            {
                "engines": {
                    "insight": {
                        "status": "completed",
                        "evidence_status": "no_data",
                        "output_file": "/tmp/insight.md",
                    }
                }
            }
        ),
        encoding="utf-8",
    )

    try:
        smoke.build_engine_artifacts_from_args(
            Namespace(
                engine_artifact=[],
                resume_search_status=str(status_file),
                resume_engine=["insight"],
            )
        )
    except ValueError as exc:
        assert "insight is not completed with ready evidence in resume status" in str(exc)
    else:
        raise AssertionError("expected ValueError")


def test_build_engine_artifacts_requires_resume_output_file(tmp_path):
    smoke = load_smoke_module()
    status_file = tmp_path / "search-status.json"
    status_file.write_text(
        json.dumps(
            {
                "engines": {
                    "insight": {
                        "status": "completed",
                        "evidence_status": "ready",
                    }
                }
            }
        ),
        encoding="utf-8",
    )

    try:
        smoke.build_engine_artifacts_from_args(
            Namespace(
                engine_artifact=[],
                resume_search_status=str(status_file),
                resume_engine=["insight"],
            )
        )
    except ValueError as exc:
        assert "insight resume status is missing output_file" in str(exc)
    else:
        raise AssertionError("expected ValueError")


def test_run_smoke_can_create_fresh_crawl_from_request(monkeypatch, tmp_path):
    smoke = load_smoke_module()
    recorder = smoke.SmokeRecorder(tmp_path)
    args = type(
        "Args",
        (),
        {
            "output_dir": tmp_path,
            "event_label": "fresh",
            "crawl_response": "",
            "request_file": str(tmp_path / "request.json"),
            "query": "小米SU7高速碰撞起火事故争议",
            "env_file": "",
            "timeout_minutes": 1,
            "poll_seconds": 1,
            "engine_artifact": ["insight=/tmp/insight.md"],
            "resume_search_status": "",
            "resume_engine": [],
        },
    )()
    Path(args.request_file).write_text(
        json.dumps(
            {
                "eventOrIssue": "高速碰撞起火事故争议",
                "affectedSubject": "小米SU7",
                "timeWindow": "2025-03-29 至 2025-04-30",
                "profileId": "enterprise_pr",
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    class FakeResponse:
        def __init__(self, payload, status_code=200):
            self.payload = payload
            self.status_code = status_code

        def get_json(self, silent=True):
            return self.payload

    class FakeClient:
        search_posts = []

        def post(self, path, json):
            if path == "/api/crawl/tasks":
                return FakeResponse(
                    {
                        "success": True,
                        "task": {
                            "task_id": "crawl_fresh",
                            "analysis_query": json["analysis_query"],
                            "status": "reportable",
                        },
                    }
                )
            if path == "/api/search":
                self.search_posts.append(json)
                return FakeResponse(
                    {
                        "success": True,
                        "task_id": "search_fresh",
                        "status": "running",
                    }
                )
            raise AssertionError(path)

        def get(self, path):
            if path == "/api/search/status/search_fresh":
                return FakeResponse(
                    {
                        "success": True,
                        "status": "completed",
                        "report_task_id": "report_fresh",
                    }
                )
            if path == "/api/report/progress/report_fresh":
                return FakeResponse(
                    {
                        "success": True,
                        "task": {
                            "status": "completed",
                            "report_file_ready": True,
                            "report_file_path": "final_reports/report.html",
                            "markdown_file_path": "final_reports/report.md",
                            "pdf_file_path": "final_reports/report.pdf",
                        },
                    }
                )
            raise AssertionError(path)

    class FakeAppModule:
        app = type("FakeApp", (), {"test_client": lambda self: FakeClient()})()

    monkeypatch.setattr(smoke, "load_runtime_env", lambda env_file="": None)
    monkeypatch.setattr(smoke, "import_flask_app", lambda: FakeAppModule)

    result = smoke.run_smoke(args, recorder)

    assert result["status"] == "report-ready"
    started = json.loads((tmp_path / "smoke-started.json").read_text(encoding="utf-8"))
    crawl = json.loads((tmp_path / "crawl-created.json").read_text(encoding="utf-8"))
    assert started["mode"] == "fresh_crawl"
    assert started["engine_artifacts"] == {"insight": {"output_file": "/tmp/insight.md"}}
    assert crawl["task_id"] == "crawl_fresh"
    assert FakeClient.search_posts == [
        {
            "query": "小米SU7高速碰撞起火事故争议",
            "data_prep_task_id": "crawl_fresh",
            "engine_artifacts": {"insight": {"output_file": "/tmp/insight.md"}},
        }
    ]
