from pathlib import Path


def test_report_engine_only_generates_pdf_when_legacy_dependency_missing(monkeypatch, tmp_path):
    import report_engine_only

    ir_path = tmp_path / "report_ir_demo.json"
    ir_path.write_text('{"metadata": {"topic": "demo"}}', encoding="utf-8")
    calls = {}

    monkeypatch.setattr(report_engine_only.sys, "argv", ["report_engine_only.py"])
    monkeypatch.setattr(report_engine_only, "setup_logger", lambda verbose=False: None)
    monkeypatch.setattr(
        report_engine_only,
        "check_dependencies",
        lambda: (False, "legacy pango unavailable"),
    )
    monkeypatch.setattr(
        report_engine_only,
        "get_latest_engine_reports",
        lambda: {"query": str(tmp_path / "query.md")},
    )
    monkeypatch.setattr(report_engine_only, "confirm_file_selection", lambda latest: True)
    monkeypatch.setattr(report_engine_only, "load_engine_reports", lambda latest: ["query report"])
    monkeypatch.setattr(report_engine_only, "extract_query_from_reports", lambda latest: "demo")

    def fake_generate_report(reports, query, pdf_enabled):
        calls["generate_report_pdf_enabled"] = pdf_enabled
        return {
            "report_id": "report_1",
            "report_filepath": str(tmp_path / "report.html"),
            "report_relative_path": "final_reports/report.html",
            "ir_filepath": str(ir_path),
        }

    def fake_save_pdf(document_ir_path, query):
        calls["save_pdf"] = (document_ir_path, query)
        return str(tmp_path / "report.pdf")

    monkeypatch.setattr(report_engine_only, "generate_report", fake_generate_report)
    monkeypatch.setattr(report_engine_only, "save_pdf", fake_save_pdf)
    monkeypatch.setattr(
        report_engine_only,
        "save_markdown",
        lambda document_ir_path, query: str(tmp_path / "report.md"),
    )

    report_engine_only.main()

    assert calls["generate_report_pdf_enabled"] is True
    assert calls["save_pdf"] == (str(ir_path), "demo")


def test_report_engine_only_skip_pdf_prevents_pdf_generation(monkeypatch, tmp_path):
    import report_engine_only

    ir_path = tmp_path / "report_ir_demo.json"
    ir_path.write_text('{"metadata": {"topic": "demo"}}', encoding="utf-8")
    calls = {}

    monkeypatch.setattr(report_engine_only.sys, "argv", ["report_engine_only.py", "--skip-pdf"])
    monkeypatch.setattr(report_engine_only, "setup_logger", lambda verbose=False: None)
    monkeypatch.setattr(report_engine_only, "check_dependencies", lambda: (False, "missing"))
    monkeypatch.setattr(report_engine_only, "get_latest_engine_reports", lambda: {"query": "query.md"})
    monkeypatch.setattr(report_engine_only, "confirm_file_selection", lambda latest: True)
    monkeypatch.setattr(report_engine_only, "load_engine_reports", lambda latest: ["query report"])
    monkeypatch.setattr(report_engine_only, "extract_query_from_reports", lambda latest: "demo")

    def fake_generate_report(reports, query, pdf_enabled):
        calls["generate_report_pdf_enabled"] = pdf_enabled
        return {
            "report_id": "report_1",
            "report_filepath": str(tmp_path / "report.html"),
            "report_relative_path": "final_reports/report.html",
            "ir_filepath": str(ir_path),
        }

    def fail_save_pdf(*_args, **_kwargs):
        raise AssertionError("save_pdf should not run when --skip-pdf is set")

    monkeypatch.setattr(report_engine_only, "generate_report", fake_generate_report)
    monkeypatch.setattr(report_engine_only, "save_pdf", fail_save_pdf)
    monkeypatch.setattr(
        report_engine_only,
        "save_markdown",
        lambda document_ir_path, query: str(tmp_path / "report.md"),
    )

    report_engine_only.main()

    assert calls["generate_report_pdf_enabled"] is False
