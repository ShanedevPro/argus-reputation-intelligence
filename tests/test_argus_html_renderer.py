import json
import html as html_lib
import re


def build_sample_ir():
    return {
        "version": "1.0",
        "reportId": "argus-test-report",
        "metadata": {
            "title": "武汉大学品牌声誉简报",
            "subtitle": "Argus Executive Brief",
            "query": "武汉大学品牌声誉",
            "generatedAt": "2026-05-13T00:00:00Z",
            "hero": {
                "summary": "用于验证 ArgusHTMLRenderer 的真实报告气质。",
                "kpis": [
                    {"label": "声量", "value": "12,480", "delta": "+18%", "tone": "up"},
                    {"label": "负面风险", "value": "中", "delta": "需观察", "tone": "neutral"},
                ],
            },
        },
        "chapters": [
            {
                "chapterId": "S1",
                "anchor": "executive-summary",
                "title": "核心发现",
                "order": 10,
                "blocks": [
                    {"type": "heading", "level": 2, "text": "核心发现", "anchor": "findings"},
                    {
                        "type": "paragraph",
                        "inlines": [
                            {"text": "品牌关注度上升，"},
                            {"text": "<script>alert(1)</script>", "marks": [{"type": "bold"}]},
                            {"text": " 必须被转义。"},
                        ],
                    },
                    {
                        "type": "kpiGrid",
                        "items": [
                            {"label": "讨论量", "value": "12,480", "delta": "+18%", "deltaTone": "up"},
                            {"label": "风险等级", "value": "中", "delta": "可控", "deltaTone": "neutral"},
                        ],
                    },
                    {
                        "type": "callout",
                        "variant": "risk",
                        "title": "风险提示",
                        "blocks": [
                            {"type": "paragraph", "inlines": [{"text": "部分讨论证据不足，应标注不确定性。"}]}
                        ],
                    },
                    {
                        "type": "table",
                        "caption": "渠道摘要",
                        "rows": [
                            {
                                "cells": [
                                    {"blocks": [{"type": "paragraph", "inlines": [{"text": "渠道"}]}]},
                                    {"blocks": [{"type": "paragraph", "inlines": [{"text": "观察"}]}]},
                                ]
                            },
                            {
                                "cells": [
                                    {"blocks": [{"type": "paragraph", "inlines": [{"text": "微博"}]}]},
                                    {"blocks": [{"type": "paragraph", "inlines": [{"text": "讨论增长"}]}]},
                                ]
                            },
                        ],
                    },
                    {
                        "type": "widget",
                        "widgetId": "sentiment-trend",
                        "widgetType": "chart.js/line",
                        "props": {"title": "情绪趋势"},
                        "data": {
                            "labels": ["Mon", "Tue", "Wed"],
                            "datasets": [{"label": "正面", "data": [12, 18, 16]}],
                        },
                    },
                    {
                        "type": "swotTable",
                        "title": "SWOT",
                        "strengths": [{"title": "校友影响", "text": "正向声誉资产"}],
                        "threats": [{"title": "争议扩散", "text": "需监测"}],
                    },
                    {
                        "type": "pestTable",
                        "title": "PEST",
                        "social": [{"title": "公共情绪", "text": "讨论集中在校园生活体验"}],
                    },
                ],
            }
        ],
    }


def build_delivery_polish_ir():
    ir = build_sample_ir()
    ir["metadata"].update(
        {
            "tagline": "把声誉信号转化为可执行的管理判断。",
            "hero": {
                "summary": "用于验证 Phase 2 交付级 HTML 的真实报告结构。",
                "highlights": [
                    "品牌关注度上升，但焦虑叙事仍需要解释。",
                    "核心声量集中在学科声誉、学生体验与校园文化。",
                ],
                "actions": [
                    "优先回应高频焦虑点。",
                    "把樱花季流量沉淀为全年品牌资产。",
                ],
                "kpis": [
                    {"label": "声量", "value": "12,480", "delta": "+18%", "tone": "up"},
                    {"label": "负面风险", "value": "中", "delta": "需观察", "tone": "warning"},
                ],
            },
            "toc": {
                "customEntries": [
                    {
                        "chapterId": "S1",
                        "anchor": "executive-summary",
                        "display": "核心发现",
                        "description": "快速判断品牌声誉状态与优先行动。",
                    }
                ]
            },
        }
    )
    blocks = ir["chapters"][0]["blocks"]
    blocks.append(
        {
            "type": "callout",
            "variant": "warning",
            "title": "观察项",
            "blocks": [{"type": "paragraph", "inlines": [{"text": "该风险需要持续监测。"}]}],
        }
    )
    blocks.append(
        {
            "type": "widget",
            "widgetId": "sentiment-trend",
            "widgetType": "chart.js/bar",
            "props": {"title": "重复 ID 图表"},
            "data": {"labels": ["A"], "datasets": [{"label": "B", "data": [1]}]},
        }
    )
    return ir


def extract_echart_option(rendered_html, chart_id):
    pattern = (
        rf'<script type="application/json" id="argus-echart-option-{re.escape(chart_id)}">'
        r"(.*?)</script>"
    )
    match = re.search(pattern, rendered_html, re.DOTALL)
    assert match, f"Missing ECharts option payload for {chart_id}"
    return json.loads(html_lib.unescape(match.group(1)))


def render_single_widget(widget_block):
    from ReportEngine.renderers import ArgusHTMLRenderer

    ir = build_sample_ir()
    ir["chapters"][0]["blocks"] = [widget_block]
    return ArgusHTMLRenderer().render(ir)


def test_argus_renderer_outputs_single_file_html_and_escapes_text():
    from ReportEngine.renderers import ArgusHTMLRenderer

    html = ArgusHTMLRenderer().render(build_sample_ir())

    assert html.startswith("<!DOCTYPE html>")
    assert "<html" in html
    assert "argus-report" in html
    assert "Argus Executive Brief" in html
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in html
    assert "<script>alert(1)</script>" not in html


def test_argus_renderer_covers_core_report_blocks():
    from ReportEngine.renderers import ArgusHTMLRenderer

    html = ArgusHTMLRenderer().render(build_sample_ir())

    expected_markers = [
        "argus-kpi-grid",
        "argus-callout",
        "argus-table",
        "argus-chart-frame",
        "argus-swot",
        "argus-pest",
        "sentiment-trend",
    ]
    for marker in expected_markers:
        assert marker in html


def test_argus_renderer_deduplicates_first_heading_that_matches_chapter_title():
    from ReportEngine.renderers import ArgusHTMLRenderer

    html = ArgusHTMLRenderer().render(build_sample_ir())

    assert '<section class="argus-section" id="executive-summary"><h2>核心发现</h2>' in html
    assert '<h2 id="findings">核心发现</h2>' not in html


def test_argus_renderer_structures_cover_metadata_for_mobile_wrapping():
    from ReportEngine.renderers import ArgusHTMLRenderer

    html = ArgusHTMLRenderer().render(build_sample_ir())

    assert '<div class="argus-meta">' in html
    assert '<span class="argus-meta-item">Query: 武汉大学品牌声誉</span>' in html
    assert " | Generated:" not in html
    assert " | Source:" not in html


def test_argus_renderer_embeds_echarts_option_json_not_chartjs_runtime():
    from ReportEngine.renderers import ArgusHTMLRenderer

    html = ArgusHTMLRenderer().render(build_sample_ir())

    assert 'type="application/json"' in html
    assert "argus-echart" in html
    assert "argus-echart-option-sentiment-trend" in html
    assert "echarts.init" in html
    assert "window.Chart" not in html
    assert "new Chart(" not in html
    assert "<canvas" not in html

    option = extract_echart_option(html, "sentiment-trend")
    assert option["xAxis"]["type"] == "category"
    assert option["xAxis"]["data"] == ["Mon", "Tue", "Wed"]
    assert option["series"][0]["type"] == "line"
    assert option["series"][0]["data"] == [12, 18, 16]


def test_argus_renderer_can_render_existing_ir_file(tmp_path):
    from ReportEngine.renderers import ArgusHTMLRenderer

    ir_path = tmp_path / "sample_ir.json"
    output_path = tmp_path / "argus_report.html"
    ir_path.write_text(json.dumps(build_sample_ir(), ensure_ascii=False), encoding="utf-8")

    renderer = ArgusHTMLRenderer()
    html = renderer.render(json.loads(ir_path.read_text(encoding="utf-8")), ir_file_path=str(ir_path))
    output_path.write_text(html, encoding="utf-8")

    assert output_path.exists()
    assert output_path.read_text(encoding="utf-8").startswith("<!DOCTYPE html>")


def test_settings_default_html_renderer_is_argus(monkeypatch):
    from ReportEngine.utils.config import Settings

    monkeypatch.delenv("REPORT_ENGINE_HTML_RENDERER", raising=False)

    assert Settings(_env_file=None).REPORT_ENGINE_HTML_RENDERER == "argus"


def test_report_agent_defaults_to_argus_renderer(monkeypatch):
    import ReportEngine.agent as agent_module

    monkeypatch.delenv("REPORT_ENGINE_HTML_RENDERER", raising=False)

    report_agent = agent_module.ReportAgent.__new__(agent_module.ReportAgent)
    report_agent.config = agent_module.Settings(_env_file=None)
    renderer = agent_module.ReportAgent._initialize_html_renderer(report_agent)

    assert renderer.__class__.__name__ == "ArgusHTMLRenderer"


def test_report_agent_can_select_legacy_renderer():
    import ReportEngine.agent as agent_module

    report_agent = agent_module.ReportAgent.__new__(agent_module.ReportAgent)
    report_agent.config = agent_module.Settings(REPORT_ENGINE_HTML_RENDERER="legacy")
    renderer = agent_module.ReportAgent._initialize_html_renderer(report_agent)

    assert renderer.__class__.__name__ == "HTMLRenderer"


def test_report_agent_can_select_argus_renderer():
    import ReportEngine.agent as agent_module

    report_agent = agent_module.ReportAgent.__new__(agent_module.ReportAgent)
    report_agent.config = agent_module.Settings(REPORT_ENGINE_HTML_RENDERER="argus")
    renderer = agent_module.ReportAgent._initialize_html_renderer(report_agent)

    assert renderer.__class__.__name__ == "ArgusHTMLRenderer"


def test_report_agent_invalid_renderer_falls_back_to_legacy():
    import ReportEngine.agent as agent_module

    report_agent = agent_module.ReportAgent.__new__(agent_module.ReportAgent)
    report_agent.config = agent_module.Settings(REPORT_ENGINE_HTML_RENDERER="unknown")
    renderer = agent_module.ReportAgent._initialize_html_renderer(report_agent)

    assert renderer.__class__.__name__ == "HTMLRenderer"


def test_render_argus_html_script_renders_ir_file(tmp_path):
    import sys

    from ReportEngine.scripts.render_argus_html import main

    ir_path = tmp_path / "sample_ir.json"
    output_path = tmp_path / "sample.html"
    ir_path.write_text(json.dumps(build_sample_ir(), ensure_ascii=False), encoding="utf-8")

    old_argv = sys.argv
    try:
        sys.argv = ["render_argus_html", str(ir_path), "--output", str(output_path)]
        assert main() == 0
    finally:
        sys.argv = old_argv

    html = output_path.read_text(encoding="utf-8")
    assert html.startswith("<!DOCTYPE html>")
    assert "argus-report" in html


def test_render_argus_html_script_renders_all_blocks_demo(tmp_path):
    import sys

    from ReportEngine.scripts.render_argus_html import main

    output_path = tmp_path / "demo.html"

    old_argv = sys.argv
    try:
        sys.argv = ["render_argus_html", "--demo", "all-blocks", "--output", str(output_path)]
        assert main() == 0
    finally:
        sys.argv = old_argv

    html = output_path.read_text(encoding="utf-8")
    assert html.startswith("<!DOCTYPE html>")
    assert "Argus Renderer All Blocks Demo" in html
    assert "argus-report" in html


def test_render_argus_pdf_playwright_script_renders_demo_with_stubbed_playwright(tmp_path, monkeypatch):
    import sys

    from ReportEngine.scripts import render_argus_pdf_playwright as pdf_script
    from ReportEngine.renderers.argus_pdf import ArgusPDFExporter

    output_path = tmp_path / "demo.pdf"
    captured = {}

    def fake_render_to_pdf(self, document_ir, output_path_arg, *, ir_file_path=None):
        captured["title"] = document_ir["metadata"]["title"]
        captured["ir_file_path"] = ir_file_path
        output_path_arg.write_bytes(b"%PDF-1.4\n%argus test\n")
        return output_path_arg

    monkeypatch.setattr(ArgusPDFExporter, "render_to_pdf", fake_render_to_pdf)

    old_argv = sys.argv
    try:
        sys.argv = ["render_argus_pdf_playwright", "--demo", "all-blocks", "--output", str(output_path)]
        assert pdf_script.main() == 0
    finally:
        sys.argv = old_argv

    assert output_path.exists()
    assert output_path.read_bytes().startswith(b"%PDF-1.4")
    assert captured["title"] == "Argus Renderer All Blocks Demo"
    assert captured["ir_file_path"] is None


def test_argus_pdf_exporter_renders_argus_html_with_playwright_stub(tmp_path, monkeypatch):
    from ReportEngine.renderers.argus_pdf import ArgusPDFExporter

    output_path = tmp_path / "report.pdf"
    captured = {}

    async def fake_print(html_path, pdf_path, *, chrome_path=None):
        captured["html"] = html_path.read_text(encoding="utf-8")
        captured["chrome_path"] = chrome_path
        pdf_path.write_bytes(b"%PDF-1.4\n%argus pdf\n")

    monkeypatch.setattr(
        "ReportEngine.renderers.argus_pdf._print_html_to_pdf",
        fake_print,
    )

    result = ArgusPDFExporter(chrome_path="/usr/bin/google-chrome").render_to_pdf(
        build_sample_ir(),
        output_path,
        ir_file_path="/tmp/sample_ir.json",
    )

    assert result == output_path
    assert output_path.read_bytes().startswith(b"%PDF-1.4")
    assert "argus-report" in captured["html"]
    assert "Argus Executive Brief" in captured["html"]
    assert "legacy-report" not in captured["html"]
    assert captured["chrome_path"] == "/usr/bin/google-chrome"


def test_argus_pdf_exporter_renders_from_running_event_loop(tmp_path, monkeypatch):
    import asyncio

    from ReportEngine.renderers.argus_pdf import ArgusPDFExporter

    output_path = tmp_path / "report.pdf"
    captured = {}

    async def fake_print(html_path, pdf_path, *, chrome_path=None):
        captured["html"] = html_path.read_text(encoding="utf-8")
        captured["chrome_path"] = chrome_path
        pdf_path.write_bytes(b"%PDF-1.4\n%argus pdf nested loop\n")

    monkeypatch.setattr(
        "ReportEngine.renderers.argus_pdf._print_html_to_pdf",
        fake_print,
    )

    async def render_inside_running_loop():
        return ArgusPDFExporter(chrome_path="/usr/bin/google-chrome").render_to_pdf(
            build_sample_ir(),
            output_path,
            ir_file_path="/tmp/sample_ir.json",
        )

    result = asyncio.run(render_inside_running_loop())

    assert result == output_path
    assert output_path.read_bytes().startswith(b"%PDF-1.4")
    assert "argus-report" in captured["html"]
    assert captured["chrome_path"] == "/usr/bin/google-chrome"


def test_argus_pdf_exporter_reports_missing_playwright(tmp_path, monkeypatch):
    import pytest

    from ReportEngine.renderers.argus_pdf import ArgusPDFExporter, ArgusPDFExportError

    def fake_loader():
        raise ArgusPDFExportError("Python Playwright is not installed")

    monkeypatch.setattr("ReportEngine.renderers.argus_pdf._load_async_playwright", fake_loader)

    with pytest.raises(ArgusPDFExportError, match="Playwright"):
        ArgusPDFExporter().render_to_pdf(build_sample_ir(), tmp_path / "report.pdf")


def test_argus_phase2_cover_uses_customer_metadata_without_source_path():
    from ReportEngine.renderers import ArgusHTMLRenderer

    html = ArgusHTMLRenderer().render(
        build_delivery_polish_ir(),
        ir_file_path="/tmp/private/report_ir_secret.json",
    )

    assert "把声誉信号转化为可执行的管理判断。" in html
    assert "品牌关注度上升，但焦虑叙事仍需要解释。" in html
    assert "优先回应高频焦虑点。" in html
    assert "/tmp/private/report_ir_secret.json" not in html
    assert "Source:" not in html


def test_argus_phase2_footer_is_customer_facing():
    from ReportEngine.renderers import ArgusHTMLRenderer

    html = ArgusHTMLRenderer().render(build_delivery_polish_ir())

    assert "Argus Report Renderer V1" not in html
    assert "argus-footer" in html
    assert "Argus Intelligence Brief" not in html
    assert "Report ID:" not in html
    assert "Argus 声誉智能报告" in html


def test_argus_swot_card_labels_are_chinese_facing():
    from ReportEngine.renderers import ArgusHTMLRenderer

    html = ArgusHTMLRenderer().render(build_sample_ir())

    assert "优势" in html
    assert "风险" in html
    assert "Strengths" not in html
    assert "Weaknesses" not in html
    assert "Opportunities" not in html
    assert "Threats" not in html


def test_argus_phase2_toc_uses_custom_entry_descriptions():
    from ReportEngine.renderers import ArgusHTMLRenderer

    html = ArgusHTMLRenderer().render(build_delivery_polish_ir())

    assert "快速判断品牌声誉状态与优先行动。" in html
    assert "argus-toc-description" in html


def test_argus_toc_renders_before_full_width_content_without_sidebar_layout():
    from ReportEngine.renderers import ArgusHTMLRenderer
    from ReportEngine.renderers.argus_html.theme import ARGUS_CSS

    html = ArgusHTMLRenderer().render(build_delivery_polish_ir())

    assert '<div class="argus-layout">' not in html
    assert html.index('<nav class="argus-toc"') < html.index('<div class="argus-content argus-prose">')
    assert "grid-template-columns: minmax(0, var(--argus-layout-toc)) minmax(0, 1fr)" not in ARGUS_CSS
    assert ".argus-toc {\n  position: sticky;" not in ARGUS_CSS


def test_argus_toc_uses_metadata_title_and_defaults_to_chinese_label():
    from ReportEngine.renderers import ArgusHTMLRenderer

    default_html = ArgusHTMLRenderer().render(build_sample_ir())
    assert '<div class="argus-label">目录</div>' in default_html
    assert "Contents" not in default_html

    ir = build_delivery_polish_ir()
    ir["metadata"]["toc"]["title"] = "风险目录"
    custom_html = ArgusHTMLRenderer().render(ir)
    assert '<div class="argus-label">风险目录</div>' in custom_html


def test_argus_css_includes_print_pagination_rules():
    from ReportEngine.renderers.argus_html.theme import ARGUS_CSS

    expected_rules = [
        "@media print",
        "@page",
        "size: A4",
        "margin: 16mm 14mm 18mm",
        "print-color-adjust: exact",
        "break-after: avoid",
        "break-inside: avoid",
        "display: table-header-group",
    ]
    for rule in expected_rules:
        assert rule in ARGUS_CSS
    assert "break-after: page" not in ARGUS_CSS


def test_argus_html_includes_pdf_print_styles():
    from ReportEngine.renderers import ArgusHTMLRenderer

    html = ArgusHTMLRenderer().render(build_sample_ir())

    assert "@media print" in html
    assert "@page" in html
    assert "print-color-adjust: exact" in html
    assert "break-inside: avoid" in html
    assert "window.__ARGUS_PRINT_READY__" in html


def test_argus_chart_hydration_exposes_print_ready_signal():
    from ReportEngine.renderers.argus_html.theme import ARGUS_CHART_HYDRATION_JS

    assert "window.__ARGUS_PRINT_READY__" in ARGUS_CHART_HYDRATION_JS
    assert "window.__ARGUS_PRINT_READY__ = true" in ARGUS_CHART_HYDRATION_JS


def test_argus_phase2_table_header_uses_semantic_th_cells():
    from ReportEngine.renderers import ArgusHTMLRenderer

    html = ArgusHTMLRenderer().render(build_delivery_polish_ir())

    assert '<th scope="col"' in html
    assert "argus-table-header-row" in html


def test_argus_phase2_tones_emit_stable_component_classes():
    from ReportEngine.renderers import ArgusHTMLRenderer

    html = ArgusHTMLRenderer().render(build_delivery_polish_ir())

    assert "argus-tone-up" in html
    assert "argus-tone-warning" in html
    assert "argus-callout-warning" in html


def test_argus_phase2_duplicate_chart_ids_are_made_unique():
    from ReportEngine.renderers import ArgusHTMLRenderer

    html = ArgusHTMLRenderer().render(build_delivery_polish_ir())

    assert 'id="argus-echart-option-sentiment-trend"' in html
    assert 'id="argus-echart-option-sentiment-trend-2"' in html
    assert 'data-argus-chart-id="sentiment-trend-2"' in html


def test_argus_phase2_chart_frame_uses_echarts_container_class_not_inline_style():
    from ReportEngine.renderers import ArgusHTMLRenderer

    html = ArgusHTMLRenderer().render(build_delivery_polish_ir())

    assert "argus-chart-viewport" in html
    assert "argus-echart" in html
    assert 'style="height: 320px"' not in html


def test_argus_chart_without_title_does_not_show_internal_widget_id():
    html = render_single_widget(
        {
            "type": "widget",
            "widgetId": "chart-s4-emotion-spectrum",
            "widgetType": "chart.js/bar",
            "data": {
                "labels": ["负面", "中性", "正面"],
                "datasets": [{"label": "情绪分布", "data": [8, 4, 2]}],
            },
        }
    )

    assert 'data-argus-chart-id="chart-s4-emotion-spectrum"' in html
    assert '<figcaption class="argus-chart-title"><strong>数据图表</strong></figcaption>' in html
    assert '<strong>chart-s4-emotion-spectrum</strong>' not in html


def test_argus_echarts_converts_bar_pie_radar_scatter_and_bubble_widgets():
    widgets = [
        (
            "bar-demo",
            {
                "type": "widget",
                "widgetId": "bar-demo",
                "widgetType": "chart.js/bar",
                "data": {
                    "labels": ["微博", "新闻"],
                    "datasets": [{"label": "声量", "data": [42, 18]}],
                },
            },
            lambda option: (
                option["series"][0]["type"] == "bar"
                and option["xAxis"]["data"] == ["微博", "新闻"]
                and option["series"][0]["data"] == [42, 18]
            ),
        ),
        (
            "pie-demo",
            {
                "type": "widget",
                "widgetId": "pie-demo",
                "widgetType": "chart.js/pie",
                "data": {
                    "labels": ["支持", "中立"],
                    "datasets": [{"label": "立场", "data": [36, 28]}],
                },
            },
            lambda option: option["series"][0]["data"] == [
                {"name": "支持", "value": 36},
                {"name": "中立", "value": 28},
            ],
        ),
        (
            "radar-demo",
            {
                "type": "widget",
                "widgetId": "radar-demo",
                "widgetType": "chart.js/radar",
                "data": {
                    "labels": ["透明度", "响应"],
                    "datasets": [{"label": "官方渠道", "data": [78, 88]}],
                },
            },
            lambda option: (
                option["radar"]["indicator"] == [
                    {"name": "透明度", "max": 100},
                    {"name": "响应", "max": 100},
                ]
                and option["series"][0]["data"][0]["value"] == [78, 88]
            ),
        ),
        (
            "scatter-demo",
            {
                "type": "widget",
                "widgetId": "scatter-demo",
                "widgetType": "chart.js/scatter",
                "data": {
                    "datasets": [
                        {"label": "帖子", "data": [{"x": 1, "y": 4}, {"x": 2, "y": 8}]}
                    ],
                },
            },
            lambda option: option["series"][0]["data"] == [[1, 4], [2, 8]],
        ),
        (
            "bubble-demo",
            {
                "type": "widget",
                "widgetId": "bubble-demo",
                "widgetType": "chart.js/bubble",
                "data": {
                    "datasets": [
                        {"label": "渠道", "data": [{"x": 1, "y": 4, "r": 12}]}
                    ],
                },
            },
            lambda option: (
                option["series"][0]["type"] == "scatter"
                and option["series"][0]["data"][0]["value"] == [1, 4]
                and option["series"][0]["data"][0]["symbolSize"] == 24
            ),
        ),
    ]

    for chart_id, widget, assertion in widgets:
        option = extract_echart_option(render_single_widget(widget), chart_id)
        assert assertion(option), chart_id


def test_argus_echarts_converts_horizontal_doughnut_and_polar_area_widgets():
    horizontal = extract_echart_option(
        render_single_widget(
            {
                "type": "widget",
                "widgetId": "horizontal-demo",
                "widgetType": "chart.js/bar",
                "props": {"options": {"indexAxis": "y"}},
                "data": {
                    "labels": ["微博", "新闻"],
                    "datasets": [{"label": "声量", "data": [42, 18]}],
                },
            }
        ),
        "horizontal-demo",
    )
    assert horizontal["xAxis"]["type"] == "value"
    assert horizontal["yAxis"]["type"] == "category"
    assert horizontal["yAxis"]["data"] == ["微博", "新闻"]

    doughnut = extract_echart_option(
        render_single_widget(
            {
                "type": "widget",
                "widgetId": "doughnut-demo",
                "widgetType": "chart.js/doughnut",
                "data": {
                    "labels": ["政策", "社会"],
                    "datasets": [{"label": "关注度", "data": [24, 28]}],
                },
            }
        ),
        "doughnut-demo",
    )
    assert doughnut["series"][0]["type"] == "pie"
    assert doughnut["series"][0]["radius"] == ["46%", "70%"]

    polar_area = extract_echart_option(
        render_single_widget(
            {
                "type": "widget",
                "widgetId": "polar-demo",
                "widgetType": "chart.js/polarArea",
                "data": {
                    "labels": ["短视频", "微博"],
                    "datasets": [{"label": "渗透度", "data": [62, 54]}],
                },
            }
        ),
        "polar-demo",
    )
    assert polar_area["series"][0]["type"] == "pie"
    assert polar_area["series"][0]["roseType"] == "area"


def test_argus_echarts_converts_sankey_widgets_to_renderable_flow_option():
    html = render_single_widget(
        {
            "type": "widget",
            "widgetId": "sankey-dissemination",
            "widgetType": "chart.js/sankey",
            "props": {"title": "传播路径"},
            "data": {
                "datasets": [
                    {
                        "data": [
                            {"from": "综艺播出", "to": "王鹤棣发博", "flow": 90},
                            {"from": "王鹤棣发博", "to": "不舒服文学", "flow": 80},
                        ]
                    }
                ]
            },
        }
    )

    option = extract_echart_option(html, "sankey-dissemination")

    assert "Unsupported chart type: sankey" not in html
    assert 'class="argus-chart-frame argus-chart-error-state"' not in html
    assert "argus-echart" in html
    assert option["series"][0]["type"] == "sankey"
    assert option["series"][0]["links"] == [
        {"source": "综艺播出", "target": "王鹤棣发博", "value": 90},
        {"source": "王鹤棣发博", "target": "不舒服文学", "value": 80},
    ]


def test_argus_echarts_uses_native_echarts_option_when_provided():
    html = render_single_widget(
        {
            "type": "widget",
            "widgetId": "native-echart",
            "widgetType": "echarts/bar",
            "props": {
                "title": "原生 ECharts",
                "echartsOption": {
                    "xAxis": {"type": "category", "data": ["A"]},
                    "yAxis": {"type": "value"},
                    "series": [{"type": "bar", "data": [9]}],
                },
            },
        }
    )

    option = extract_echart_option(html, "native-echart")
    assert option["xAxis"]["data"] == ["A"]
    assert option["series"][0]["type"] == "bar"
    assert option["series"][0]["data"] == [9]
    assert "argus-chart-error" in html


def test_argus_echarts_uses_text_from_object_title():
    html = render_single_widget(
        {
            "type": "widget",
            "widgetId": "object-title-chart",
            "widgetType": "chart.js/line",
            "props": {
                "title": {"text": "关键节点时间线", "color": "#1E293B"},
            },
            "data": {
                "labels": ["A", "B"],
                "datasets": [{"label": "热度", "data": [1, 2]}],
            },
        }
    )

    assert "<strong>关键节点时间线</strong>" in html
    assert "&#x27;text&#x27;" not in html
    assert "{&#x27;" not in html


def test_argus_echarts_uses_native_option_alias_when_provided():
    html = render_single_widget(
        {
            "type": "widget",
            "widgetId": "native-option-alias",
            "widgetType": "echarts/line",
            "props": {
                "option": {
                    "xAxis": {"type": "category", "data": ["A", "B"]},
                    "yAxis": {"type": "value"},
                    "series": [{"type": "line", "data": [3, 6]}],
                },
            },
        }
    )

    option = extract_echart_option(html, "native-option-alias")
    assert option["xAxis"]["data"] == ["A", "B"]
    assert option["series"][0]["data"] == [3, 6]


def test_argus_echarts_empty_chart_data_renders_visible_empty_state():
    html = render_single_widget(
        {
            "type": "widget",
            "widgetId": "empty-chart",
            "widgetType": "chart.js/line",
            "props": {"title": "空图表"},
            "data": {"labels": [], "datasets": []},
        }
    )

    assert "argus-chart-empty" in html
    assert "No chart data available." in html
    assert "argus-echart-option-empty-chart" not in html


def test_argus_echarts_invalid_chart_type_renders_customer_facing_fallback():
    html = render_single_widget(
        {
            "type": "widget",
            "widgetId": "bad-chart",
            "widgetType": "chart.js/not-real",
            "data": {"labels": ["A"], "datasets": [{"label": "B", "data": [1]}]},
        }
    )

    assert "argus-chart-error-state" in html
    assert "图表暂无法渲染" in html
    assert "Chart render failed" not in html
    assert "Unsupported chart type" not in html
    assert "not-real" not in html
    assert "argus-echart-option-bad-chart" not in html


def test_argus_phase2_css_exposes_reusable_token_groups():
    from ReportEngine.renderers.argus_html.theme import ARGUS_CSS

    expected_tokens = [
        "--argus-color-canvas",
        "--argus-color-paper",
        "--argus-color-ink",
        "--argus-space-section",
        "--argus-layout-max",
        "--argus-radius-card",
        "--argus-shadow-paper",
    ]
    for token in expected_tokens:
        assert token in ARGUS_CSS
