from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

from ReportEngine.core import DocumentComposer
from ReportEngine.renderers import ArgusHTMLRenderer
from ReportEngine.utils.config import settings


def build_all_blocks_demo_ir() -> Dict[str, Any]:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    metadata = {
        "title": "Argus Renderer All Blocks Demo",
        "subtitle": "Renderer QA fixture",
        "query": "Argus renderer visual QA",
        "generatedAt": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "hero": {
            "summary": "Synthetic Document IR for checking ArgusHTMLRenderer coverage.",
            "kpis": [
                {"label": "Blocks", "value": "20+", "delta": "full coverage", "tone": "neutral"},
                {"label": "Charts", "value": "9", "delta": "ECharts", "tone": "neutral"},
            ],
        },
    }
    chapters = [
        {
            "chapterId": "S1",
            "anchor": "overview",
            "title": "Executive Overview",
            "order": 10,
            "blocks": [
                {"type": "heading", "level": 2, "text": "Executive Overview", "anchor": "overview-heading"},
                {
                    "type": "paragraph",
                    "inlines": [
                        {"text": "This synthetic IR covers every ArgusHTMLRenderer V1 block path."},
                    ],
                },
                {
                    "type": "kpiGrid",
                    "items": [
                        {"label": "Mentions", "value": "12,480", "delta": "+18%", "deltaTone": "up"},
                        {"label": "Risk", "value": "Medium", "delta": "watch", "deltaTone": "neutral"},
                        {"label": "Evidence", "value": "Scoped", "delta": "reviewed", "deltaTone": "neutral"},
                    ],
                },
                {
                    "type": "callout",
                    "variant": "risk",
                    "title": "Risk note",
                    "blocks": [
                        {
                            "type": "paragraph",
                            "inlines": [{"text": "Unsupported or weak evidence must remain visible to reviewers."}],
                        }
                    ],
                },
                {
                    "type": "list",
                    "listType": "bullet",
                    "items": [
                        [{"type": "paragraph", "inlines": [{"text": "Stable layout"}]}],
                        [{"type": "paragraph", "inlines": [{"text": "Escaped report text"}]}],
                    ],
                },
            ],
        },
        {
            "chapterId": "S2",
            "anchor": "data-blocks",
            "title": "Data Blocks",
            "order": 20,
            "blocks": [
                {
                    "type": "table",
                    "caption": "Channel summary",
                    "rows": [
                        {
                            "cells": [
                                {"blocks": [{"type": "paragraph", "inlines": [{"text": "Channel"}]}]},
                                {"blocks": [{"type": "paragraph", "inlines": [{"text": "Signal"}]}]},
                            ]
                        },
                        {
                            "cells": [
                                {"blocks": [{"type": "paragraph", "inlines": [{"text": "Weibo"}]}]},
                                {"blocks": [{"type": "paragraph", "inlines": [{"text": "Discussion increased"}]}]},
                            ]
                        },
                    ],
                },
                {
                    "type": "widget",
                    "widgetId": "demo-line",
                    "widgetType": "chart.js/line",
                    "props": {"title": "Sentiment trend"},
                    "data": {
                        "labels": ["Mon", "Tue", "Wed", "Thu"],
                        "datasets": [{"label": "Positive", "data": [12, 18, 16, 22]}],
                    },
                },
                {
                    "type": "widget",
                    "widgetId": "demo-bar",
                    "widgetType": "chart.js/bar",
                    "props": {"title": "Channel volume"},
                    "data": {
                        "labels": ["Weibo", "News", "Forum"],
                        "datasets": [{"label": "Volume", "data": [42, 24, 18]}],
                    },
                },
                {
                    "type": "widget",
                    "widgetId": "demo-horizontal-bar",
                    "widgetType": "chart.js/bar",
                    "props": {"title": "Channel reach", "options": {"indexAxis": "y"}},
                    "data": {
                        "labels": ["Weibo", "Short video", "Forum", "News"],
                        "datasets": [{"label": "Reach", "data": [58, 42, 27, 36]}],
                    },
                },
                {
                    "type": "widget",
                    "widgetId": "demo-pie",
                    "widgetType": "chart.js/pie",
                    "props": {"title": "Position mix"},
                    "data": {
                        "labels": ["Supportive", "Neutral", "Questioning"],
                        "datasets": [{"label": "Position", "data": [36, 28, 21]}],
                    },
                },
                {
                    "type": "widget",
                    "widgetId": "demo-doughnut",
                    "widgetType": "chart.js/doughnut",
                    "props": {"title": "Topic share"},
                    "data": {
                        "labels": ["Policy", "Economic", "Social", "Technology"],
                        "datasets": [{"label": "Share", "data": [24, 30, 28, 18]}],
                    },
                },
                {
                    "type": "widget",
                    "widgetId": "demo-radar",
                    "widgetType": "chart.js/radar",
                    "props": {"title": "Response quality"},
                    "data": {
                        "labels": ["Transparency", "Speed", "Consistency", "Engagement", "Depth"],
                        "datasets": [{"label": "Official", "data": [78, 88, 82, 66, 91]}],
                    },
                },
                {
                    "type": "widget",
                    "widgetId": "demo-polar-area",
                    "widgetType": "chart.js/polarArea",
                    "props": {"title": "Channel penetration"},
                    "data": {
                        "labels": ["Short video", "Weibo", "Forum", "News"],
                        "datasets": [{"label": "Penetration", "data": [62, 54, 38, 45]}],
                    },
                },
                {
                    "type": "widget",
                    "widgetId": "demo-scatter",
                    "widgetType": "chart.js/scatter",
                    "props": {"title": "Sentiment vs engagement"},
                    "data": {
                        "datasets": [
                            {
                                "label": "Posts",
                                "data": [
                                    {"x": -0.65, "y": 120},
                                    {"x": -0.25, "y": 190},
                                    {"x": 0.05, "y": 260},
                                    {"x": 0.42, "y": 340},
                                    {"x": 0.78, "y": 410},
                                ],
                            }
                        ],
                    },
                },
                {
                    "type": "widget",
                    "widgetId": "demo-bubble",
                    "widgetType": "chart.js/bubble",
                    "props": {"title": "Exposure impact"},
                    "data": {
                        "datasets": [
                            {
                                "label": "Channels",
                                "data": [
                                    {"x": 8, "y": 35, "r": 12},
                                    {"x": 12, "y": -28, "r": 10},
                                    {"x": 18, "y": 22, "r": 14},
                                    {"x": 25, "y": 48, "r": 16},
                                ],
                            }
                        ],
                    },
                },
            ],
        },
        {
            "chapterId": "S3",
            "anchor": "analysis-blocks",
            "title": "Analysis Blocks",
            "order": 30,
            "blocks": [
                {
                    "type": "swotTable",
                    "title": "SWOT",
                    "strengths": [{"title": "Reputation asset", "text": "Strong alumni and academic visibility."}],
                    "weaknesses": [{"title": "Service friction", "text": "Repeated complaints need review."}],
                    "opportunities": [{"title": "Clarify story", "text": "Publish clearer evidence-backed updates."}],
                    "threats": [{"title": "Narrative drift", "text": "Rumors may outrun confirmed facts."}],
                },
                {
                    "type": "pestTable",
                    "title": "PEST",
                    "political": [{"title": "Policy", "text": "Public institutions remain under close scrutiny."}],
                    "economic": [{"title": "Budget", "text": "Funding perception affects stakeholder expectations."}],
                    "social": [{"title": "Community", "text": "Student experience dominates discussion."}],
                    "technological": [{"title": "Platforms", "text": "Short-form channels accelerate issue spread."}],
                },
                {
                    "type": "engineQuote",
                    "engine": "insight",
                    "title": "Insight Agent",
                    "blocks": [{"type": "paragraph", "inlines": [{"text": "Evidence quality is mixed."}]}],
                },
                {
                    "type": "blockquote",
                    "blocks": [{"type": "paragraph", "inlines": [{"text": "A sample quoted observation."}]}],
                },
                {"type": "code", "language": "text", "content": "risk = evidence * reach"},
                {"type": "math", "latex": "risk = probability \\\\times impact"},
                {"type": "figure", "caption": "Figure placeholder without external image"},
                {"type": "hr"},
                {"type": "toc"},
            ],
        },
    ]
    return DocumentComposer().build_document(f"argus-all-blocks-{timestamp}", metadata, chapters)


def load_ir(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def default_output_path(source: str) -> Path:
    out_dir = Path(settings.OUTPUT_DIR) / "argus_html"
    out_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_source = "".join(ch if ch.isalnum() or ch in ("-", "_") else "_" for ch in source)[:40]
    safe_source = safe_source or "report"
    return out_dir / f"argus_report_{safe_source}_{timestamp}.html"


def main() -> int:
    parser = argparse.ArgumentParser(description="Render ReportEngine Document IR with ArgusHTMLRenderer.")
    parser.add_argument("ir_json", nargs="?", help="Path to Document IR JSON.")
    parser.add_argument("--demo", choices=["all-blocks"], help="Render a built-in demo IR instead of a file.")
    parser.add_argument("--output", help="Output HTML path.")
    args = parser.parse_args()

    if args.demo == "all-blocks":
        document_ir = build_all_blocks_demo_ir()
        source_name = "all_blocks_demo"
        ir_file_path = None
    elif args.ir_json:
        ir_path = Path(args.ir_json)
        document_ir = load_ir(ir_path)
        source_name = ir_path.stem
        ir_file_path = str(ir_path)
    else:
        parser.error("Provide an IR JSON path or --demo all-blocks.")

    output_path = Path(args.output) if args.output else default_output_path(source_name)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    html = ArgusHTMLRenderer().render(document_ir, ir_file_path=ir_file_path)
    output_path.write_text(html, encoding="utf-8")
    print(output_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
