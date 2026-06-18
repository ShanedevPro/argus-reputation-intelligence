#!/usr/bin/env python
"""
PDF导出脚本
"""
import json
import sys
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
DEFAULT_PDF_OUTPUT_DIR = PROJECT_ROOT / "final_reports" / "pdf"

# 添加项目路径到sys.path，便于从任意工作目录运行脚本。
sys.path.insert(0, str(PROJECT_ROOT))


def resolve_input_report(argv):
    """Return an explicit report path or the latest generated report IR."""
    if len(argv) > 1:
        return Path(argv[1]).expanduser().resolve()

    candidates = sorted(
        (PROJECT_ROOT / "final_reports" / "ir").glob("report_ir_*.json"),
        key=lambda path: (path.stat().st_mtime_ns, path.name),
    )
    return candidates[-1] if candidates else None


def _render_argus_pdf_to_path(document_ir, output_path, ir_file_path):
    from ReportEngine.renderers.argus_pdf import ArgusPDFExporter

    return ArgusPDFExporter().render_to_pdf(
        document_ir,
        output_path,
        ir_file_path=ir_file_path,
    )


def _render_legacy_pdf_to_bytes(document_ir, optimize=True, ir_file_path=None):
    from ReportEngine.renderers.pdf_renderer import PDFRenderer

    return PDFRenderer().render_to_bytes(
        document_ir,
        optimize_layout=optimize,
        ir_file_path=ir_file_path,
    )


def export_pdf(ir_file_path, output_dir=DEFAULT_PDF_OUTPUT_DIR):
    """导出PDF"""
    try:
        ir_file_path = Path(ir_file_path)
        # 读取IR文件
        print(f"正在读取报告文件: {ir_file_path}")
        with open(ir_file_path, 'r', encoding='utf-8') as f:
            document_ir = json.load(f)

        # 确定输出文件名
        topic = document_ir.get('metadata', {}).get('topic', 'report')
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        pdf_filename = f"report_{topic}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
        output_path = output_dir / pdf_filename

        print("正在生成Argus同源PDF...")
        try:
            _render_argus_pdf_to_path(document_ir, output_path, str(ir_file_path))
        except Exception as exc:
            print(f"Argus PDF导出失败，回退到legacy PDFRenderer: {exc}")
            pdf_bytes = _render_legacy_pdf_to_bytes(
                document_ir,
                optimize=True,
                ir_file_path=str(ir_file_path),
            )
            print(f"正在保存PDF到: {output_path}")
            with open(output_path, 'wb') as f:
                f.write(pdf_bytes)

        print(f"✅ PDF导出成功！")
        print(f"文件位置: {output_path}")
        print(f"文件大小: {output_path.stat().st_size / 1024 / 1024:.2f} MB")

        return str(output_path)

    except Exception as e:
        print(f"❌ PDF导出失败: {str(e)}")
        import traceback
        traceback.print_exc()
        return None

if __name__ == "__main__":
    report_path = resolve_input_report(sys.argv)

    if report_path and report_path.exists():
        print("="*50)
        print("开始导出PDF")
        print("="*50)
        result = export_pdf(report_path)
        if result:
            print(f"\n📄 PDF文件已生成: {result}")
    else:
        print("❌ 未找到报告IR文件，请传入 report_ir_*.json 路径")
