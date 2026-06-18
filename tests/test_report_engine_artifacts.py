import time
from pathlib import Path


def test_report_task_exposes_pdf_and_export_status_fields():
    from ReportEngine.flask_interface import ReportTask

    task = ReportTask("清华大学苏世民书院", "report_1")
    task.pdf_file_path = "/tmp/report.pdf"
    task.pdf_file_relative_path = "final_reports/pdf/report.pdf"
    task.pdf_file_name = "report.pdf"
    task.export_errors.append("pdf: unavailable")

    payload = task.to_dict()

    assert payload["pdf_file_ready"] is True
    assert payload["pdf_file_path"] == "final_reports/pdf/report.pdf"
    assert payload["pdf_file_name"] == "report.pdf"
    assert payload["export_errors"] == ["pdf: unavailable"]


def test_auto_export_report_artifacts_updates_task(monkeypatch, tmp_path):
    import ReportEngine.flask_interface as report_interface

    task = report_interface.ReportTask("清华大学苏世民书院", "report_1")
    task.status = "completed"
    task.ir_file_path = str(tmp_path / "report_ir.json")
    Path(task.ir_file_path).write_text('{"metadata": {"topic": "demo"}}', encoding="utf-8")

    def fake_export_markdown(export_task):
        export_task.markdown_file_path = str(tmp_path / "report.md")
        export_task.markdown_file_relative_path = "final_reports/report.md"
        export_task.markdown_file_name = "report.md"
        Path(export_task.markdown_file_path).write_text("# demo", encoding="utf-8")

    def fake_export_pdf(export_task, optimize=True):
        export_task.pdf_file_path = str(tmp_path / "report.pdf")
        export_task.pdf_file_relative_path = "final_reports/pdf/report.pdf"
        export_task.pdf_file_name = "report.pdf"
        Path(export_task.pdf_file_path).write_bytes(b"%PDF-1.7\n")

    monkeypatch.setattr(report_interface, "_export_markdown_artifact", fake_export_markdown)
    monkeypatch.setattr(report_interface, "_export_pdf_artifact", fake_export_pdf)

    report_interface.auto_export_report_artifacts(task)

    payload = task.to_dict()
    assert payload["markdown_file_ready"] is True
    assert payload["pdf_file_ready"] is True
    assert payload["export_errors"] == []


def test_export_pdf_artifact_uses_argus_pdf_exporter_first(monkeypatch, tmp_path):
    import ReportEngine.flask_interface as report_interface

    monkeypatch.setattr(report_interface.settings, "OUTPUT_DIR", str(tmp_path))

    task = report_interface.ReportTask("王鹤棣 不舒服文学", "report_1")
    task.status = "completed"
    task.ir_file_path = str(tmp_path / "report_ir.json")
    Path(task.ir_file_path).write_text(
        '{"metadata": {"topic": "王鹤棣 不舒服文学"}}',
        encoding="utf-8",
    )

    calls = []
    rendered_pdf_path = tmp_path / "expected.pdf"

    def fake_render_argus_pdf_to_path(document_ir, pdf_path, ir_file_path):
        calls.append(
            (
                "argus",
                document_ir,
                Path(pdf_path).name,
                ir_file_path,
            )
        )
        Path(pdf_path).write_bytes(b"%PDF-1.4\n%argus\n")
        return Path(pdf_path)

    def fake_render_legacy_pdf_to_bytes(*_args, **_kwargs):
        raise AssertionError("legacy fallback should not be used when Argus succeeds")

    monkeypatch.setattr(
        report_interface,
        "_render_argus_pdf_to_path",
        fake_render_argus_pdf_to_path,
    )
    monkeypatch.setattr(
        report_interface,
        "_render_legacy_pdf_to_bytes",
        fake_render_legacy_pdf_to_bytes,
    )

    report_interface._export_pdf_artifact(task)

    assert calls == [
        (
            "argus",
            {"metadata": {"topic": "王鹤棣 不舒服文学"}},
            Path(task.pdf_file_path).name,
            task.ir_file_path,
        )
    ]
    assert task.to_dict()["pdf_file_ready"] is True
    assert Path(task.pdf_file_path).read_bytes().startswith(b"%PDF-1.4")
    assert Path(task.pdf_file_path).parent == tmp_path / "pdf"


def test_export_pdf_artifact_falls_back_to_legacy_when_argus_pdf_fails(monkeypatch, tmp_path):
    import ReportEngine.flask_interface as report_interface

    monkeypatch.setattr(report_interface.settings, "OUTPUT_DIR", str(tmp_path))

    task = report_interface.ReportTask("王鹤棣 不舒服文学", "report_1")
    task.status = "completed"
    task.ir_file_path = str(tmp_path / "report_ir.json")
    Path(task.ir_file_path).write_text('{"metadata": {"topic": "demo"}}', encoding="utf-8")

    calls = []

    def broken_render_argus_pdf_to_path(*_args, **_kwargs):
        calls.append("argus")
        raise RuntimeError("playwright unavailable")

    def fake_render_legacy_pdf_to_bytes(document_ir, optimize=True, ir_file_path=None):
        calls.append(("legacy", document_ir, optimize, ir_file_path))
        return b"%PDF-1.4\n%legacy fallback\n"

    monkeypatch.setattr(
        report_interface,
        "_render_argus_pdf_to_path",
        broken_render_argus_pdf_to_path,
    )
    monkeypatch.setattr(
        report_interface,
        "_render_legacy_pdf_to_bytes",
        fake_render_legacy_pdf_to_bytes,
    )

    report_interface._export_pdf_artifact(task)

    assert calls[0] == "argus"
    assert calls[1][0] == "legacy"
    assert calls[1][3] == task.ir_file_path
    assert Path(task.pdf_file_path).read_bytes().startswith(b"%PDF-1.4")
    assert task.pdf_file_name.endswith(".pdf")


def test_report_progress_returns_404_for_missing_task():
    from ReportEngine.flask_interface import report_bp
    import ReportEngine.flask_interface as report_interface
    from flask import Flask

    report_interface.current_task = None
    report_interface.tasks_registry.clear()

    app = Flask(__name__)
    app.register_blueprint(report_bp, url_prefix="/api/report")

    response = app.test_client().get("/api/report/progress/missing_task")

    assert response.status_code == 404
    assert response.get_json() == {"success": False, "error": "任务不存在"}


def test_report_result_json_returns_completed_artifact_contract(tmp_path):
    from ReportEngine.flask_interface import ReportTask, report_bp
    import ReportEngine.flask_interface as report_interface
    from flask import Flask

    report_interface.current_task = None
    report_interface.tasks_registry.clear()

    task = ReportTask("BettaFish reputation", "report_1")
    task.status = "completed"
    task.progress = 100
    task.html_content = '<!DOCTYPE html><html><body class="argus-report">Customer report</body></html>'
    task.report_file_path = str(tmp_path / "report.html")
    task.report_file_relative_path = "final_reports/report.html"
    task.report_file_name = "report.html"
    Path(task.report_file_path).write_text(task.html_content, encoding="utf-8")
    report_interface.tasks_registry[task.task_id] = task

    app = Flask(__name__)
    app.register_blueprint(report_bp, url_prefix="/api/report")

    response = app.test_client().get("/api/report/result/report_1/json")

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["success"] is True
    assert payload["html_content"] == (
        '<!DOCTYPE html><html><body class="argus-report">Customer report</body></html>'
    )
    assert payload["task"]["status"] == "completed"
    assert payload["task"]["has_result"] is True
    assert payload["task"]["report_file_ready"] is True
    assert payload["task"]["report_file_name"] == "report.html"


def test_renderer_package_imports_html_without_pdf_extras():
    import importlib
    import sys

    sys.modules.pop("ReportEngine.renderers", None)

    renderers = importlib.import_module("ReportEngine.renderers")

    assert renderers.HTMLRenderer is not None


def test_start_report_task_uses_explicit_engine_files_even_if_latest_gate_would_fail(
    monkeypatch, tmp_path
):
    import ReportEngine.flask_interface as report_interface

    monkeypatch.chdir(tmp_path)
    (tmp_path / "logs").mkdir()
    (tmp_path / "logs" / "forum.log").write_text("forum", encoding="utf-8")

    explicit_files = {
        engine: tmp_path / f"{engine}-explicit.md"
        for engine in ("insight", "media", "query")
    }
    for path in explicit_files.values():
        path.write_text(path.name, encoding="utf-8")

    loaded_paths = {}

    class FakeFileBaseline:
        def check_new_files(self, _directories):
            return {
                "ready": False,
                "baseline_counts": {},
                "current_counts": {},
                "new_files_found": {},
                "missing_engines": ["insight", "media", "query"],
            }

        def get_latest_files(self, _directories):
            raise AssertionError("latest files should not be selected for explicit inputs")

    class FakeReportAgent:
        file_baseline = FakeFileBaseline()

        def check_input_files(self, *_args):
            return {
                "ready": False,
                "missing_files": ["stale latest files"],
                "latest_files": {},
            }

        def load_input_files(self, file_paths):
            loaded_paths.update(file_paths)
            return {"reports": ["insight", "media", "query"], "forum_logs": "forum"}

        def generate_report(self, **_kwargs):
            return {"html_content": "<html></html>"}

    monkeypatch.setattr(report_interface, "report_agent", FakeReportAgent())
    monkeypatch.setattr(report_interface, "current_task", None)
    monkeypatch.setattr(report_interface, "tasks_registry", {})

    result = report_interface.start_report_task(
        query="王鹤棣 不舒服文学",
        auto_export=False,
        engine_files={engine: str(path) for engine, path in explicit_files.items()},
    )

    assert result["success"] is True

    task_id = result["task_id"]
    deadline = time.time() + 3
    while time.time() < deadline:
        task = report_interface.tasks_registry[task_id]
        if task.status in {"completed", "error"}:
            break
        time.sleep(0.05)

    assert report_interface.tasks_registry[task_id].status == "completed"
    assert loaded_paths == {
        "insight": str(explicit_files["insight"]),
        "media": str(explicit_files["media"]),
        "query": str(explicit_files["query"]),
        "forum": "logs/forum.log",
    }


def test_start_report_task_combines_explicit_and_latest_engine_files(
    monkeypatch, tmp_path
):
    import ReportEngine.flask_interface as report_interface

    monkeypatch.chdir(tmp_path)
    (tmp_path / "logs").mkdir()
    (tmp_path / "logs" / "forum.log").write_text("forum", encoding="utf-8")

    explicit_insight = tmp_path / "insight-explicit.md"
    explicit_insight.write_text("insight-explicit", encoding="utf-8")

    latest_files = {
        "media": tmp_path / "media-latest.md",
        "query": tmp_path / "query-latest.md",
    }
    for path in latest_files.values():
        path.write_text(path.name, encoding="utf-8")

    for engine in ("media", "query"):
        engine_dir = tmp_path / f"{engine}_engine_streamlit_reports"
        engine_dir.mkdir()
        (engine_dir / f"{engine}-report.md").write_text(
            f"{engine}-report", encoding="utf-8"
        )

    loaded_paths = {}

    class FakeFileBaseline:
        baseline_data = {}

        def check_new_files(self, directories):
            current_counts = {
                engine: 1 for engine in directories
            }
            return {
                "ready": True,
                "baseline_counts": {},
                "current_counts": current_counts,
                "new_files_found": {engine: 1 for engine in directories},
                "missing_engines": [],
            }

        def get_latest_files(self, directories):
            latest = {}
            for engine, directory in directories.items():
                latest[engine] = str(
                    next(Path(directory).glob("*.md"))
                )
            return latest

    class FakeReportAgent:
        file_baseline = FakeFileBaseline()

        def check_input_files(self, *_args):
            return {
                "ready": False,
                "missing_files": ["insight: stale latest files"],
                "latest_files": {},
            }

        def load_input_files(self, file_paths):
            loaded_paths.update(file_paths)
            return {"reports": ["insight", "media", "query"], "forum_logs": "forum"}

        def generate_report(self, **_kwargs):
            return {"html_content": "<html></html>"}

    monkeypatch.setattr(report_interface, "report_agent", FakeReportAgent())
    monkeypatch.setattr(report_interface, "current_task", None)
    monkeypatch.setattr(report_interface, "tasks_registry", {})

    result = report_interface.start_report_task(
        query="王鹤棣 不舒服文学",
        auto_export=False,
        engine_files={"insight": str(explicit_insight)},
    )

    assert result["success"] is True

    task_id = result["task_id"]
    assert report_interface.tasks_registry[task_id].engine_files == {
        "insight": str(explicit_insight),
        "media": "media_engine_streamlit_reports/media-report.md",
        "query": "query_engine_streamlit_reports/query-report.md",
    }
    deadline = time.time() + 3
    while time.time() < deadline:
        task = report_interface.tasks_registry[task_id]
        if task.status in {"completed", "error"}:
            break
        time.sleep(0.05)

    assert report_interface.tasks_registry[task_id].status == "completed"
    assert loaded_paths == {
        "insight": str(explicit_insight),
        "media": "media_engine_streamlit_reports/media-report.md",
        "query": "query_engine_streamlit_reports/query-report.md",
        "forum": "logs/forum.log",
    }


def test_start_report_task_rejects_missing_explicit_engine_file(monkeypatch, tmp_path):
    import ReportEngine.flask_interface as report_interface

    monkeypatch.chdir(tmp_path)
    (tmp_path / "logs").mkdir()
    (tmp_path / "logs" / "forum.log").write_text("forum", encoding="utf-8")

    existing = tmp_path / "media-explicit.md"
    existing.write_text("media-explicit", encoding="utf-8")

    class FakeFileBaseline:
        def check_new_files(self, *_args):
            raise AssertionError("readiness should fail before latest-file lookup")

        def get_latest_files(self, *_args):
            raise AssertionError("readiness should fail before latest-file lookup")

    class FakeReportAgent:
        file_baseline = FakeFileBaseline()

    monkeypatch.setattr(report_interface, "report_agent", FakeReportAgent())
    monkeypatch.setattr(report_interface, "current_task", None)
    monkeypatch.setattr(report_interface, "tasks_registry", {})

    result = report_interface.start_report_task(
        query="王鹤棣 不舒服文学",
        auto_export=False,
        engine_files={
            "insight": str(tmp_path / "missing-insight.md"),
            "media": str(existing),
            "query": str(tmp_path / "query-explicit.md"),
        },
    )

    assert result["success"] is False
    assert "insight" in result["error"]
    assert "不存在" in result["error"]
