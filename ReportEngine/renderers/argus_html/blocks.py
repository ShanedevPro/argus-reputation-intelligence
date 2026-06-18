from __future__ import annotations

import html
import re
from typing import Any, Dict, Iterable, List

from .charts import ArgusChartRenderer


class ArgusBlockRenderer:
    """Render supported ReportEngine IR blocks into safe Argus HTML components."""

    def __init__(self):
        self._chart_ids: set[str] = set()
        self.chart_renderer = ArgusChartRenderer()

    def render_chapter(self, chapter: Dict[str, Any]) -> str:
        anchor = self.escape(chapter.get("anchor") or chapter.get("chapterId") or "section")
        raw_title = chapter.get("title") or chapter.get("chapterId") or "Section"
        title = self.escape(raw_title)
        blocks = chapter.get("blocks") if isinstance(chapter.get("blocks"), list) else []
        skipped_anchor = ""
        if blocks and self._is_duplicate_chapter_heading(blocks[0], raw_title):
            heading_anchor = blocks[0].get("anchor")
            skipped_anchor = (
                f'<span class="argus-heading-anchor" id="{self.escape(heading_anchor)}"></span>'
                if heading_anchor
                else ""
            )
            blocks = blocks[1:]
        return (
            f'<section class="argus-section" id="{anchor}">'
            f"<h2>{title}</h2>"
            f"{skipped_anchor}"
            f"{self.render_blocks(blocks)}"
            "</section>"
        )

    def render_blocks(self, blocks: Iterable[Any]) -> str:
        return "".join(self.render_block(block) for block in blocks or [])

    def render_block(self, block: Any) -> str:
        if isinstance(block, str):
            return f"<p>{self.escape(block)}</p>"
        if not isinstance(block, dict):
            return ""
        block_type = block.get("type")
        handlers = {
            "heading": self.render_heading,
            "paragraph": self.render_paragraph,
            "list": self.render_list,
            "table": self.render_table,
            "blockquote": self.render_blockquote,
            "engineQuote": self.render_engine_quote,
            "hr": lambda b: "<hr>",
            "code": self.render_code,
            "math": self.render_math,
            "figure": self.render_figure,
            "callout": self.render_callout,
            "kpiGrid": self.render_kpi_grid,
            "widget": self.render_widget,
            "swotTable": self.render_swot,
            "pestTable": self.render_pest,
            "toc": lambda b: "",
        }
        handler = handlers.get(block_type)
        if handler:
            return handler(block)
        return (
            '<div class="argus-callout"><strong>Unsupported block:</strong> '
            f"{self.escape(block_type or 'unknown')}</div>"
        )

    def _is_duplicate_chapter_heading(self, block: Any, chapter_title: Any) -> bool:
        if not isinstance(block, dict) or block.get("type") != "heading":
            return False
        return self.normalized_text(block.get("text")) == self.normalized_text(chapter_title)

    @staticmethod
    def escape(value: Any) -> str:
        return html.escape("" if value is None else str(value), quote=True)

    @staticmethod
    def normalized_text(value: Any) -> str:
        return " ".join(str(value or "").split())

    def safe_class_token(self, value: Any, default: str = "neutral") -> str:
        candidate = re.sub(r"[^A-Za-z0-9_-]+", "-", str(value or default).strip().lower()).strip("-")
        return candidate or default

    def safe_tone(self, value: Any) -> str:
        tone = self.safe_class_token(value, "neutral")
        if tone in {"up", "down", "warning", "neutral", "success", "risk"}:
            return tone
        return "neutral"

    def safe_callout_variant(self, value: Any) -> str:
        variant = self.safe_class_token(value, "note")
        if variant in {"note", "info", "success", "warning", "risk", "neutral"}:
            return variant
        return "note"

    def render_inlines(self, inlines: Iterable[Any]) -> str:
        parts = []
        for inline in inlines or []:
            if isinstance(inline, str):
                parts.append(self.escape(inline))
                continue
            if not isinstance(inline, dict):
                continue
            text = self.escape(inline.get("text") or "")
            for mark in inline.get("marks") or []:
                if not isinstance(mark, dict):
                    continue
                text = self.apply_mark(text, mark)
            parts.append(text)
        return "".join(parts)

    def apply_mark(self, text: str, mark: Dict[str, Any]) -> str:
        mark_type = mark.get("type")
        if mark_type == "bold":
            return f"<strong>{text}</strong>"
        if mark_type == "italic":
            return f"<em>{text}</em>"
        if mark_type == "underline":
            return f"<u>{text}</u>"
        if mark_type == "strike":
            return f"<s>{text}</s>"
        if mark_type == "code":
            return f"<code>{text}</code>"
        if mark_type == "link":
            href = self.safe_href(mark.get("href") or mark.get("value") or "#")
            title = self.escape(mark.get("title") or "")
            title_attr = f' title="{title}"' if title else ""
            return f'<a href="{href}"{title_attr}>{text}</a>'
        if mark_type == "highlight":
            return f"<mark>{text}</mark>"
        return text

    def safe_href(self, href: Any) -> str:
        value = str(href or "#").strip()
        if value.startswith(("#", "/", "http://", "https://", "mailto:")):
            return self.escape(value)
        return "#"

    def render_heading(self, block: Dict[str, Any]) -> str:
        level = self.safe_int(block.get("level") or 2, default=2)
        level = max(2, min(4, level))
        anchor = block.get("anchor")
        anchor_attr = f' id="{self.escape(anchor)}"' if anchor else ""
        text = self.escape(block.get("text") or "")
        subtitle = block.get("subtitle")
        subtitle_html = f'<span class="argus-muted"> {self.escape(subtitle)}</span>' if subtitle else ""
        return f"<h{level}{anchor_attr}>{text}{subtitle_html}</h{level}>"

    def render_paragraph(self, block: Dict[str, Any]) -> str:
        align = block.get("align")
        align_attr = (
            f' style="text-align: {self.escape(align)}"'
            if align in {"left", "center", "right", "justify"}
            else ""
        )
        return f"<p{align_attr}>{self.render_inlines(block.get('inlines') or [])}</p>"

    def render_list(self, block: Dict[str, Any]) -> str:
        tag = "ol" if block.get("listType") == "ordered" else "ul"
        items = []
        for item in block.get("items") or []:
            if isinstance(item, list):
                items.append(f"<li>{self.render_blocks(item)}</li>")
            else:
                items.append(f"<li>{self.escape(item)}</li>")
        return f"<{tag}>" + "".join(items) + f"</{tag}>"

    def render_blockquote(self, block: Dict[str, Any]) -> str:
        return f'<blockquote>{self.render_blocks(block.get("blocks") or [])}</blockquote>'

    def render_engine_quote(self, block: Dict[str, Any]) -> str:
        engine = self.escape(block.get("title") or block.get("engine") or "Engine")
        return (
            '<aside class="argus-callout">'
            f'<div class="argus-label">{engine}</div>{self.render_blocks(block.get("blocks") or [])}'
            "</aside>"
        )

    def render_code(self, block: Dict[str, Any]) -> str:
        language = self.escape(block.get("language") or "")
        content = self.escape(block.get("content") or block.get("code") or "")
        return f'<pre data-language="{language}"><code>{content}</code></pre>'

    def render_math(self, block: Dict[str, Any]) -> str:
        latex = self.escape(block.get("latex") or block.get("text") or "")
        return f'<div class="argus-callout"><code>{latex}</code></div>'

    def render_figure(self, block: Dict[str, Any]) -> str:
        caption = self.escape(block.get("caption") or block.get("title") or "Figure")
        alt = self.escape(block.get("alt") or caption)
        src = self.safe_href(block.get("src") or block.get("url") or "")
        if src == "#":
            return f'<figure class="argus-callout"><figcaption>{caption}</figcaption></figure>'
        return f'<figure><img src="{src}" alt="{alt}"><figcaption>{caption}</figcaption></figure>'

    def render_kpi_grid(self, block: Dict[str, Any]) -> str:
        items = block.get("items") or []
        if not items:
            return ""
        cards = []
        for item in items:
            if not isinstance(item, dict):
                continue
            label = self.escape(item.get("label") or "")
            value = self.escape(item.get("value") or "")
            unit = self.escape(item.get("unit") or "")
            delta = self.escape(item.get("delta") or "")
            tone = self.safe_tone(item.get("deltaTone") or item.get("tone") or "neutral")
            tone_class = f"argus-tone-{tone}"
            cards.append(
                f'<div class="argus-kpi {tone_class}">'
                f'<div class="argus-kpi-label">{label}</div>'
                f'<div class="argus-kpi-value">{value}<span class="argus-kpi-unit">{unit}</span></div>'
                f'<div class="argus-kpi-delta {tone_class}">{delta}</div>'
                "</div>"
            )
        return '<div class="argus-kpi-grid">' + "".join(cards) + "</div>"

    def render_callout(self, block: Dict[str, Any]) -> str:
        variant = self.safe_callout_variant(block.get("variant") or block.get("tone") or "note")
        title = self.escape(block.get("title") or "")
        title_html = f'<strong class="argus-callout-title">{title}</strong>' if title else ""
        return (
            f'<aside class="argus-callout argus-callout-{variant}">'
            f"{title_html}{self.render_blocks(block.get('blocks') or [])}</aside>"
        )

    def render_table(self, block: Dict[str, Any]) -> str:
        caption = self.escape(block.get("caption") or "")
        caption_html = f"<caption>{caption}</caption>" if caption else ""
        rows = []
        for row_index, row in enumerate(block.get("rows") or []):
            if not isinstance(row, dict):
                continue
            is_header_row = row_index == 0
            tag = "th" if is_header_row else "td"
            scope_attr = ' scope="col"' if is_header_row else ""
            row_class = ' class="argus-table-header-row"' if is_header_row else ""
            cells = []
            for cell in row.get("cells") or []:
                if not isinstance(cell, dict):
                    continue
                align = cell.get("align")
                align_attr = (
                    f' style="text-align: {self.escape(align)}"'
                    if align in {"left", "center", "right"}
                    else ""
                )
                colspan = self.safe_int(cell.get("colspan") or 1, default=1)
                rowspan = self.safe_int(cell.get("rowspan") or 1, default=1)
                span_attrs = f' colspan="{max(1, colspan)}" rowspan="{max(1, rowspan)}"'
                cells.append(
                    f'<{tag}{scope_attr} class="argus-table-cell"{span_attrs}{align_attr}>'
                    f"{self.render_blocks(cell.get('blocks') or [])}"
                    f"</{tag}>"
                )
            rows.append(f"<tr{row_class}>" + "".join(cells) + "</tr>")
        return (
            '<div class="argus-table-wrap"><table class="argus-table">'
            f"{caption_html}<tbody>{''.join(rows)}</tbody></table></div>"
        )

    def render_swot(self, block: Dict[str, Any]) -> str:
        groups = [
            ("优势", block.get("strengths") or []),
            ("短板", block.get("weaknesses") or []),
            ("机会", block.get("opportunities") or []),
            ("风险", block.get("threats") or []),
        ]
        cards = [self.render_named_items(label, items, "argus-analysis-card") for label, items in groups if items]
        title = self.escape(block.get("title") or "SWOT")
        return f'<h3>{title}</h3><div class="argus-analysis-grid argus-swot">{"".join(cards)}</div>'

    def render_pest(self, block: Dict[str, Any]) -> str:
        groups = [
            ("Political", block.get("political") or []),
            ("Economic", block.get("economic") or []),
            ("Social", block.get("social") or []),
            ("Technological", block.get("technological") or []),
        ]
        cards = [self.render_named_items(label, items, "argus-analysis-card") for label, items in groups if items]
        title = self.escape(block.get("title") or "PEST")
        return f'<h3>{title}</h3><div class="argus-analysis-grid argus-pest">{"".join(cards)}</div>'

    def render_named_items(self, label: str, items: List[Any], class_name: str) -> str:
        rendered = [f'<div class="argus-analysis-card-title">{self.escape(label)}</div>']
        for item in items:
            if isinstance(item, dict):
                item_title = self.escape(item.get("title") or item.get("label") or "")
                text = self.escape(item.get("text") or item.get("detail") or item.get("description") or "")
                rendered.append(f'<p class="argus-analysis-card-item"><strong>{item_title}</strong><br>{text}</p>')
            else:
                rendered.append(f'<p class="argus-analysis-card-item">{self.escape(item)}</p>')
        return f'<div class="{class_name}">{"".join(rendered)}</div>'

    def render_widget(self, block: Dict[str, Any]) -> str:
        widget_id = self.unique_dom_id(block.get("widgetId") or f"chart-{len(self._chart_ids) + 1}")
        return self.chart_renderer.render_widget(block, widget_id)

    def safe_dom_id(self, value: Any) -> str:
        candidate = re.sub(r"[^A-Za-z0-9_-]+", "-", str(value or "chart")).strip("-")
        return candidate or "chart"

    def unique_dom_id(self, value: Any) -> str:
        base = self.safe_dom_id(value)
        if base not in self._chart_ids:
            self._chart_ids.add(base)
            return base
        index = 2
        while f"{base}-{index}" in self._chart_ids:
            index += 1
        candidate = f"{base}-{index}"
        self._chart_ids.add(candidate)
        return candidate

    @staticmethod
    def safe_int(value: Any, default: int = 1) -> int:
        try:
            return int(value)
        except (TypeError, ValueError):
            return default
