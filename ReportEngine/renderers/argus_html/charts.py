from __future__ import annotations

import html
import json
import math
from copy import deepcopy
from typing import Any, Dict, List


ARGUS_CHART_COLORS = [
    "#155e8a",
    "#166534",
    "#a16207",
    "#9a3412",
    "#4f46e5",
    "#0f766e",
    "#7c2d12",
]


class ArgusChartRenderer:
    """Convert ReportEngine chart widgets into Argus-styled ECharts markup."""

    def render_widget(self, block: Dict[str, Any], chart_id: str) -> str:
        props = block.get("props") if isinstance(block.get("props"), dict) else {}
        title = self.escape(
            self.display_text(
                props.get("title")
                or block.get("title")
                or block.get("caption")
                or "数据图表"
            )
            or "数据图表"
        )
        safe_chart_id = self.escape(chart_id)
        try:
            option = self.build_option(block)
        except ValueError as error:
            return self.render_error(title, str(error))

        if not self.has_renderable_series(option):
            return self.render_empty(title)

        option_json = json.dumps(option, ensure_ascii=False)
        option_html = html.escape(option_json, quote=False)
        return (
            '<figure class="argus-chart-frame">'
            f'<figcaption class="argus-chart-title"><strong>{title}</strong></figcaption>'
            '<div class="argus-chart-viewport">'
            f'<div class="argus-echart" data-argus-chart-id="{safe_chart_id}"></div>'
            "</div>"
            f'<script type="application/json" id="argus-echart-option-{safe_chart_id}">{option_html}</script>'
            '<div class="argus-chart-error" aria-live="polite"></div>'
            "</figure>"
        )

    def build_option(self, block: Dict[str, Any]) -> Dict[str, Any]:
        props = block.get("props") if isinstance(block.get("props"), dict) else {}
        native_option = props.get("echartsOption") or props.get("option")
        if isinstance(native_option, dict):
            return self.with_defaults(deepcopy(native_option), "axis")

        widget_type = str(block.get("widgetType") or "chart.js/bar")
        chart_type = widget_type.split("/")[-1] if "/" in widget_type else widget_type
        chart_type = chart_type.replace("-", "").lower()
        data = block.get("data") if isinstance(block.get("data"), dict) else {}
        options = props.get("options") if isinstance(props.get("options"), dict) else {}
        horizontal = options.get("indexAxis") == "y"
        stacked = self.is_stacked(options)

        if chart_type == "line":
            return self.cartesian_option(data, "line")
        if chart_type == "bar":
            return self.cartesian_option(data, "bar", horizontal=horizontal, stacked=stacked)
        if chart_type == "horizontalbar":
            return self.cartesian_option(data, "bar", horizontal=True, stacked=stacked)
        if chart_type in {"pie", "doughnut", "polararea"}:
            return self.pie_option(data, chart_type)
        if chart_type == "radar":
            return self.radar_option(data)
        if chart_type == "scatter":
            return self.scatter_option(data)
        if chart_type == "bubble":
            return self.bubble_option(data)
        if chart_type == "sankey":
            return self.sankey_option(data)
        raise ValueError(f"Unsupported chart type: {chart_type or 'unknown'}")

    def cartesian_option(
        self,
        data: Dict[str, Any],
        series_type: str,
        horizontal: bool = False,
        stacked: bool = False,
    ) -> Dict[str, Any]:
        labels = self.labels(data)
        series = []
        for index, dataset in enumerate(self.datasets(data)):
            values = self.numeric_values(dataset.get("data"))
            if not values:
                continue
            item_style = (
                {"borderRadius": [0, 6, 6, 0]} if horizontal else {"borderRadius": [6, 6, 0, 0]}
            )
            series_item: Dict[str, Any] = {
                "name": self.series_name(dataset, index),
                "type": series_type,
                "data": values,
            }
            if series_type == "line":
                series_item.update(
                    {
                        "smooth": True,
                        "symbolSize": 7,
                        "lineStyle": {"width": 2},
                        "areaStyle": {"opacity": 0.08},
                    }
                )
            else:
                series_item.update({"barMaxWidth": 34, "itemStyle": item_style})
                if stacked:
                    series_item["stack"] = "total"
            series.append(series_item)

        axis_label = {"color": "#5b6472", "fontSize": 11}
        axis_line = {"lineStyle": {"color": "#d7dde6"}}
        split_line = {"lineStyle": {"color": "#edf1f5"}}
        option = self.base_option("axis")
        if horizontal:
            option.update(
                {
                    "xAxis": {"type": "value", "axisLabel": axis_label, "splitLine": split_line},
                    "yAxis": {"type": "category", "data": labels, "axisLabel": axis_label, "axisLine": axis_line},
                    "series": series,
                }
            )
        else:
            option.update(
                {
                    "xAxis": {"type": "category", "data": labels, "axisLabel": axis_label, "axisLine": axis_line},
                    "yAxis": {"type": "value", "axisLabel": axis_label, "splitLine": split_line},
                    "series": series,
                }
            )
        return option

    def pie_option(self, data: Dict[str, Any], chart_type: str) -> Dict[str, Any]:
        labels = self.labels(data)
        datasets = self.datasets(data)
        first_dataset = datasets[0] if datasets else {}
        values = self.numeric_values(first_dataset.get("data"))
        series_data = [
            {"name": label, "value": value}
            for label, value in zip(labels, values)
        ]
        radius: str | List[str] = "64%"
        if chart_type == "doughnut":
            radius = ["46%", "70%"]
        series: Dict[str, Any] = {
            "name": self.series_name(first_dataset, 0),
            "type": "pie",
            "radius": radius,
            "center": ["50%", "45%"],
            "data": series_data,
            "label": {"color": "#374151", "fontSize": 11},
            "itemStyle": {"borderColor": "#ffffff", "borderWidth": 2},
        }
        if chart_type == "polararea":
            series["roseType"] = "area"
        option = self.base_option("item")
        option["series"] = [series]
        return option

    def radar_option(self, data: Dict[str, Any]) -> Dict[str, Any]:
        labels = self.labels(data)
        datasets = self.datasets(data)
        max_value = self.radar_max(datasets)
        series_data = []
        for index, dataset in enumerate(datasets):
            values = self.numeric_values(dataset.get("data"))
            if values:
                series_data.append({"name": self.series_name(dataset, index), "value": values})
        option = self.base_option("item")
        option.update(
            {
                "radar": {
                    "indicator": [{"name": label, "max": max_value} for label in labels],
                    "axisName": {"color": "#5b6472", "fontSize": 11},
                    "splitLine": {"lineStyle": {"color": "#e5eaf0"}},
                    "splitArea": {"areaStyle": {"color": ["#ffffff", "#f8fafc"]}},
                },
                "series": [{"type": "radar", "data": series_data, "areaStyle": {"opacity": 0.08}}],
            }
        )
        return option

    def scatter_option(self, data: Dict[str, Any]) -> Dict[str, Any]:
        option = self.xy_option_base()
        option["series"] = [
            {
                "name": self.series_name(dataset, index),
                "type": "scatter",
                "symbolSize": 10,
                "data": self.xy_points(dataset.get("data")),
            }
            for index, dataset in enumerate(self.datasets(data))
            if self.xy_points(dataset.get("data"))
        ]
        return option

    def bubble_option(self, data: Dict[str, Any]) -> Dict[str, Any]:
        option = self.xy_option_base()
        option["series"] = [
            {
                "name": self.series_name(dataset, index),
                "type": "scatter",
                "data": self.bubble_points(dataset.get("data")),
            }
            for index, dataset in enumerate(self.datasets(data))
            if self.bubble_points(dataset.get("data"))
        ]
        return option

    def sankey_option(self, data: Dict[str, Any]) -> Dict[str, Any]:
        nodes = set()
        links = []
        for dataset in self.datasets(data):
            values = dataset.get("data")
            if not isinstance(values, list):
                continue
            for item in values:
                if not isinstance(item, dict):
                    continue
                source = str(item.get("from") or item.get("source") or "").strip()
                target = str(item.get("to") or item.get("target") or "").strip()
                value = item.get("flow", item.get("value"))
                if (
                    not source
                    or not target
                    or not isinstance(value, (int, float))
                    or isinstance(value, bool)
                ):
                    continue
                nodes.add(source)
                nodes.add(target)
                links.append({"source": source, "target": target, "value": value})

        option = self.base_option("item")
        option["series"] = [
            {
                "type": "sankey",
                "data": [{"name": name} for name in sorted(nodes)],
                "links": links,
                "nodeAlign": "justify",
                "lineStyle": {"color": "gradient", "curveness": 0.5},
                "label": {"color": "#374151", "fontSize": 11},
            }
        ]
        return option

    def xy_option_base(self) -> Dict[str, Any]:
        option = self.base_option("item")
        option.update(
            {
                "xAxis": {
                    "type": "value",
                    "axisLabel": {"color": "#5b6472", "fontSize": 11},
                    "splitLine": {"lineStyle": {"color": "#edf1f5"}},
                },
                "yAxis": {
                    "type": "value",
                    "axisLabel": {"color": "#5b6472", "fontSize": 11},
                    "splitLine": {"lineStyle": {"color": "#edf1f5"}},
                },
            }
        )
        return option

    def base_option(self, tooltip_trigger: str) -> Dict[str, Any]:
        return {
            "color": ARGUS_CHART_COLORS,
            "backgroundColor": "transparent",
            "animationDuration": 650,
            "tooltip": {
                "trigger": tooltip_trigger,
                "confine": True,
                "renderMode": "richText",
            },
            "legend": {
                "type": "scroll",
                "bottom": 0,
                "left": "center",
                "itemWidth": 10,
                "itemHeight": 10,
                "textStyle": {"color": "#5b6472", "fontSize": 11},
            },
            "grid": {"left": 44, "right": 22, "top": 28, "bottom": 58, "containLabel": True},
        }

    def with_defaults(self, option: Dict[str, Any], tooltip_trigger: str) -> Dict[str, Any]:
        defaults = self.base_option(tooltip_trigger)
        merged = deepcopy(defaults)
        merged.update(option)
        return merged

    def render_empty(self, title: str) -> str:
        return (
            '<figure class="argus-chart-frame argus-chart-empty">'
            f'<figcaption class="argus-chart-title"><strong>{title}</strong></figcaption>'
            '<div class="argus-chart-empty-message">No chart data available.</div>'
            "</figure>"
        )

    def render_error(self, title: str, message: str) -> str:
        del message
        return (
            '<figure class="argus-chart-frame argus-chart-error-state">'
            f'<figcaption class="argus-chart-title"><strong>{title}</strong></figcaption>'
            '<div class="argus-chart-error argus-chart-error-visible">图表暂无法渲染：请参考本节文字说明。</div>'
            "</figure>"
        )

    def has_renderable_series(self, option: Dict[str, Any]) -> bool:
        series = option.get("series")
        if isinstance(series, dict):
            series = [series]
        if not isinstance(series, list):
            return False
        for item in series:
            if not isinstance(item, dict):
                continue
            if (
                item.get("type") == "sankey"
                and isinstance(item.get("links"), list)
                and item["links"]
            ):
                return True
            data = item.get("data")
            if isinstance(data, list) and len(data) > 0:
                return True
        return False

    @staticmethod
    def labels(data: Dict[str, Any]) -> List[str]:
        labels = data.get("labels")
        if not isinstance(labels, list):
            return []
        return [str(label) for label in labels]

    @staticmethod
    def datasets(data: Dict[str, Any]) -> List[Dict[str, Any]]:
        datasets = data.get("datasets")
        if not isinstance(datasets, list):
            return []
        return [dataset for dataset in datasets if isinstance(dataset, dict)]

    @staticmethod
    def series_name(dataset: Dict[str, Any], index: int) -> str:
        return str(dataset.get("label") or dataset.get("name") or f"Series {index + 1}")

    @staticmethod
    def numeric_values(values: Any) -> List[Any]:
        if not isinstance(values, list):
            return []
        normalized = []
        for value in values:
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                normalized.append(value)
            elif value is None:
                normalized.append(None)
        return normalized

    @staticmethod
    def xy_points(values: Any) -> List[List[Any]]:
        if not isinstance(values, list):
            return []
        points = []
        for value in values:
            if not isinstance(value, dict):
                continue
            x_value = value.get("x")
            y_value = value.get("y")
            if isinstance(x_value, (int, float)) and isinstance(y_value, (int, float)):
                points.append([x_value, y_value])
        return points

    @staticmethod
    def bubble_points(values: Any) -> List[Dict[str, Any]]:
        if not isinstance(values, list):
            return []
        points = []
        for value in values:
            if not isinstance(value, dict):
                continue
            x_value = value.get("x")
            y_value = value.get("y")
            radius = value.get("r")
            if not isinstance(x_value, (int, float)) or not isinstance(y_value, (int, float)):
                continue
            symbol_size = radius * 2 if isinstance(radius, (int, float)) else 10
            points.append({"value": [x_value, y_value], "symbolSize": max(4, symbol_size)})
        return points

    def radar_max(self, datasets: List[Dict[str, Any]]) -> int:
        max_observed = 0.0
        for dataset in datasets:
            for value in self.numeric_values(dataset.get("data")):
                if isinstance(value, (int, float)):
                    max_observed = max(max_observed, float(value))
        if max_observed <= 100:
            return 100
        return int(math.ceil(max_observed / 50.0) * 50)

    @staticmethod
    def is_stacked(options: Dict[str, Any]) -> bool:
        scales = options.get("scales")
        if not isinstance(scales, dict):
            return False
        for axis_options in scales.values():
            if isinstance(axis_options, dict) and axis_options.get("stacked") is True:
                return True
        return False

    @staticmethod
    def display_text(value: Any) -> str:
        if isinstance(value, dict):
            for key in ("text", "title", "name", "label"):
                text = str(value.get(key) or "").strip()
                if text:
                    return text
            return ""
        if isinstance(value, list):
            parts = [ArgusChartRenderer.display_text(item) for item in value]
            return " ".join(part for part in parts if part).strip()
        return str(value or "").strip()

    @staticmethod
    def escape(value: Any) -> str:
        return html.escape("" if value is None else str(value), quote=True)
