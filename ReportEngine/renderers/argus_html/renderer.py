from __future__ import annotations

import html
from pathlib import Path
from typing import Any, Dict, List

from .blocks import ArgusBlockRenderer
from .theme import ARGUS_CHART_HYDRATION_JS, ARGUS_CSS


class ArgusHTMLRenderer:
    """Render ReportEngine Document IR as a polished Argus single-file HTML report."""

    def __init__(self, config: Dict[str, Any] | None = None):
        self.config = config or {}

    def render(self, document_ir: Dict[str, Any], ir_file_path: str | None = None) -> str:
        document = document_ir or {}
        metadata = document.get("metadata", {}) or {}
        chapters = document.get("chapters", []) or []
        title = metadata.get("title") or metadata.get("query") or "Argus Report"
        block_renderer = ArgusBlockRenderer()
        body = self._render_document(metadata, chapters, block_renderer, document.get("reportId"), ir_file_path)
        return (
            "<!DOCTYPE html>\n"
            '<html lang="zh-CN">\n'
            "<head>\n"
            '  <meta charset="utf-8">\n'
            '  <meta name="viewport" content="width=device-width, initial-scale=1">\n'
            f"  <title>{html.escape(str(title))}</title>\n"
            f"  <style>{ARGUS_CSS}</style>\n"
            f"  {self._echarts_tag()}\n"
            "</head>\n"
            f"{body}\n"
            "</html>"
        )

    def _render_document(
        self,
        metadata: Dict[str, Any],
        chapters: List[Dict[str, Any]],
        block_renderer: ArgusBlockRenderer,
        report_id: Any,
        ir_file_path: str | None,
    ) -> str:
        cover = self._render_cover(metadata, block_renderer)
        toc = self._render_toc(chapters, metadata)
        content = "\n".join(block_renderer.render_chapter(chapter) for chapter in chapters)
        footer = self._render_footer(metadata, report_id)
        return (
            "<body>\n"
            '  <main class="argus-report">\n'
            '    <article class="argus-paper">\n'
            f"{cover}\n"
            f"{toc}\n"
            f'        <div class="argus-content argus-prose">{content}</div>\n'
            f"{footer}\n"
            "    </article>\n"
            "  </main>\n"
            f"  <script>{ARGUS_CHART_HYDRATION_JS}</script>\n"
            "</body>"
        )

    def _render_cover(
        self,
        metadata: Dict[str, Any],
        block_renderer: ArgusBlockRenderer,
    ) -> str:
        title = html.escape(str(metadata.get("title") or metadata.get("query") or "Argus Report"), quote=True)
        subtitle = html.escape(str(metadata.get("subtitle") or "Executive Intelligence Brief"), quote=True)
        tagline = html.escape(str(metadata.get("tagline") or ""), quote=True)
        hero = metadata.get("hero") if isinstance(metadata.get("hero"), dict) else {}
        summary = html.escape(str(hero.get("summary") or metadata.get("summary") or ""), quote=True)
        tagline_html = f'<p class="argus-tagline">{tagline}</p>' if tagline else ""
        summary_html = f'<p class="argus-cover-summary">{summary}</p>' if summary else ""
        highlights_html = self._render_text_list(hero.get("highlights") or [], "argus-hero-highlights")
        actions_html = self._render_text_list(hero.get("actions") or [], "argus-hero-actions")
        kpis = block_renderer.render_kpi_grid({"type": "kpiGrid", "items": hero.get("kpis") or []})
        meta_html = self._render_meta(metadata)
        return (
            '      <header class="argus-cover">\n'
            '        <div class="argus-label">Argus Executive Brief</div>\n'
            f'        <h1 class="argus-title">{title}</h1>\n'
            f'        <p class="argus-subtitle">{subtitle}</p>\n'
            f"        {tagline_html}\n"
            f"        {summary_html}\n"
            f"        {highlights_html}\n"
            f"        {kpis}\n"
            f"        {actions_html}\n"
            f'        <div class="argus-meta">{meta_html}</div>\n'
            "      </header>"
        )

    def _render_text_list(self, items: Any, class_name: str) -> str:
        if not isinstance(items, list):
            return ""
        rendered = []
        for item in items:
            text = html.escape(str(item), quote=True).strip()
            if text:
                rendered.append(f"<li>{text}</li>")
        if not rendered:
            return ""
        return f'<ul class="{class_name}">{"".join(rendered)}</ul>'

    def _render_meta(self, metadata: Dict[str, Any]) -> str:
        generated = html.escape(str(metadata.get("generatedAt") or metadata.get("generated_at") or ""), quote=True)
        query = html.escape(str(metadata.get("query") or ""), quote=True)
        meta_items = [
            ("Query", query),
            ("Generated", generated),
        ]
        return "".join(
            f'<span class="argus-meta-item">{label}: {value}</span>'
            for label, value in meta_items
            if value
        )

    def _render_toc(self, chapters: List[Dict[str, Any]], metadata: Dict[str, Any]) -> str:
        custom_entries = {}
        toc = metadata.get("toc") if isinstance(metadata.get("toc"), dict) else {}
        toc_title = html.escape(str(toc.get("title") or "目录"), quote=True)
        for entry in toc.get("customEntries") or []:
            if not isinstance(entry, dict):
                continue
            for key in (entry.get("chapterId"), entry.get("anchor")):
                if key:
                    custom_entries[str(key)] = entry
        links = []
        for chapter in chapters:
            chapter_id = str(chapter.get("chapterId") or "")
            anchor_value = str(chapter.get("anchor") or chapter_id or "section")
            entry = custom_entries.get(chapter_id) or custom_entries.get(anchor_value) or {}
            anchor = html.escape(anchor_value, quote=True)
            title = html.escape(str(entry.get("display") or chapter.get("title") or chapter.get("chapterId") or "Section"), quote=True)
            description = html.escape(str(entry.get("description") or ""), quote=True)
            description_html = (
                f'<span class="argus-toc-description">{description}</span>'
                if description
                else ""
            )
            links.append(
                f'<a href="#{anchor}">'
                f'<span class="argus-toc-title">{title}</span>'
                f"{description_html}"
                "</a>"
            )
        return f'        <nav class="argus-toc"><div class="argus-label">{toc_title}</div><div class="argus-toc-links">{"".join(links)}</div></nav>'

    def _render_footer(self, metadata: Dict[str, Any], report_id: Any) -> str:
        return (
            '      <footer class="argus-footer">'
            "<span>Argus 声誉智能报告</span>"
            "</footer>"
        )

    def _echarts_tag(self) -> str:
        chart_path = Path(__file__).resolve().parents[1] / "libs" / "echarts.min.js"
        try:
            return f"<script>{chart_path.read_text(encoding='utf-8')}</script>"
        except Exception:
            return "<script>window.echarts = window.echarts || null;</script>"
