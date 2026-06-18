from pathlib import Path
import os

import export_pdf


def test_export_pdf_defaults_to_project_relative_paths():
    project_root = Path(export_pdf.__file__).resolve().parent

    assert export_pdf.PROJECT_ROOT == project_root
    assert export_pdf.DEFAULT_PDF_OUTPUT_DIR == project_root / "final_reports" / "pdf"


def test_resolve_input_report_uses_cli_argument(tmp_path):
    report_path = tmp_path / "report_ir_demo.json"
    report_path.write_text("{}", encoding="utf-8")

    assert export_pdf.resolve_input_report(["export_pdf.py", str(report_path)]) == report_path


def test_resolve_input_report_finds_latest_project_report(tmp_path, monkeypatch):
    report_dir = tmp_path / "final_reports" / "ir"
    report_dir.mkdir(parents=True)
    older = report_dir / "report_ir_old.json"
    newer = report_dir / "report_ir_new.json"
    older.write_text("{}", encoding="utf-8")
    newer.write_text("{}", encoding="utf-8")
    os.utime(older, (1_700_000_000, 1_700_000_000))
    os.utime(newer, (1_700_000_001, 1_700_000_001))
    monkeypatch.setattr(export_pdf, "PROJECT_ROOT", tmp_path)

    assert export_pdf.resolve_input_report(["export_pdf.py"]) == newer


def test_export_pdf_uses_argus_exporter_first(tmp_path, monkeypatch):
    ir_path = tmp_path / "report_ir_demo.json"
    ir_path.write_text('{"metadata": {"topic": "demo"}}', encoding="utf-8")
    output_dir = tmp_path / "pdf"
    calls = []

    def fake_render_argus_pdf_to_path(document_ir, output_path, ir_file_path):
        calls.append(("argus", document_ir, Path(output_path).name, ir_file_path))
        Path(output_path).write_bytes(b"%PDF-1.4\n%argus\n")
        return Path(output_path)

    def fake_render_legacy_pdf_to_bytes(*_args, **_kwargs):
        raise AssertionError("legacy renderer should not run when Argus succeeds")

    monkeypatch.setattr(export_pdf, "_render_argus_pdf_to_path", fake_render_argus_pdf_to_path)
    monkeypatch.setattr(export_pdf, "_render_legacy_pdf_to_bytes", fake_render_legacy_pdf_to_bytes)

    result = export_pdf.export_pdf(ir_path, output_dir=output_dir)

    assert result is not None
    result_path = Path(result)
    assert result_path.exists()
    assert result_path.read_bytes().startswith(b"%PDF-1.4")
    assert calls == [
        (
            "argus",
            {"metadata": {"topic": "demo"}},
            result_path.name,
            str(ir_path),
        )
    ]


def test_export_pdf_falls_back_to_legacy_renderer(tmp_path, monkeypatch):
    ir_path = tmp_path / "report_ir_demo.json"
    ir_path.write_text('{"metadata": {"topic": "demo"}}', encoding="utf-8")
    output_dir = tmp_path / "pdf"
    calls = []

    def fake_render_argus_pdf_to_path(*_args, **_kwargs):
        calls.append("argus")
        raise RuntimeError("playwright unavailable")

    def fake_render_legacy_pdf_to_bytes(document_ir, optimize=True, ir_file_path=None):
        calls.append(("legacy", document_ir, optimize, ir_file_path))
        return b"%PDF-1.4\n%legacy\n"

    monkeypatch.setattr(export_pdf, "_render_argus_pdf_to_path", fake_render_argus_pdf_to_path)
    monkeypatch.setattr(export_pdf, "_render_legacy_pdf_to_bytes", fake_render_legacy_pdf_to_bytes)

    result = export_pdf.export_pdf(ir_path, output_dir=output_dir)

    assert result is not None
    assert calls == [
        "argus",
        ("legacy", {"metadata": {"topic": "demo"}}, True, str(ir_path)),
    ]
    assert Path(result).read_bytes().startswith(b"%PDF-1.4")
