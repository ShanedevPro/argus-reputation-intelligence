from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from ReportEngine.renderers.argus_pdf import ArgusPDFExportError, ArgusPDFExporter
from ReportEngine.scripts.render_argus_html import build_all_blocks_demo_ir


def load_ir(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Render ReportEngine Document IR to PDF using ArgusHTMLRenderer and Playwright."
    )
    parser.add_argument("ir_json", nargs="?", help="Path to Document IR JSON.")
    parser.add_argument("--demo", choices=["all-blocks"], help="Render a built-in demo IR instead of a file.")
    parser.add_argument("--output", required=True, help="Output PDF path.")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.demo == "all-blocks":
        document_ir = build_all_blocks_demo_ir()
        ir_file_path = None
    elif args.ir_json:
        ir_path = Path(args.ir_json)
        document_ir = load_ir(ir_path)
        ir_file_path = str(ir_path)
    else:
        parser.error("Provide an IR JSON path or --demo all-blocks.")

    output_path = Path(args.output).expanduser().resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        ArgusPDFExporter().render_to_pdf(
            document_ir,
            output_path,
            ir_file_path=ir_file_path,
        )
    except ArgusPDFExportError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    print(output_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
