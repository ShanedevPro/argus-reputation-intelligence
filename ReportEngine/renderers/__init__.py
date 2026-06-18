"""
Report Engine渲染器集合。

提供 HTMLRenderer 和 PDFRenderer，支持HTML和PDF输出。
"""

from .argus_html import ArgusHTMLRenderer
from .html_renderer import HTMLRenderer
from .markdown_renderer import MarkdownRenderer

__all__ = [
    "ArgusHTMLRenderer",
    "ArgusPDFExporter",
    "ArgusPDFExportError",
    "HTMLRenderer",
    "PDFRenderer",
    "MarkdownRenderer",
    "PDFLayoutOptimizer",
    "PDFLayoutConfig",
    "PageLayout",
    "KPICardLayout",
    "CalloutLayout",
    "TableLayout",
    "ChartLayout",
    "GridLayout",
]

_PDF_EXPORTS = {
    "ArgusPDFExporter",
    "ArgusPDFExportError",
    "PDFRenderer",
    "PDFLayoutOptimizer",
    "PDFLayoutConfig",
    "PageLayout",
    "KPICardLayout",
    "CalloutLayout",
    "TableLayout",
    "ChartLayout",
    "GridLayout",
}


def __getattr__(name: str):
    if name in {"ArgusPDFExporter", "ArgusPDFExportError"}:
        from .argus_pdf import ArgusPDFExporter, ArgusPDFExportError

        return {
            "ArgusPDFExporter": ArgusPDFExporter,
            "ArgusPDFExportError": ArgusPDFExportError,
        }[name]

    if name == "PDFRenderer":
        from .pdf_renderer import PDFRenderer

        return PDFRenderer

    if name in _PDF_EXPORTS:
        from . import pdf_layout_optimizer

        return getattr(pdf_layout_optimizer, name)

    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
