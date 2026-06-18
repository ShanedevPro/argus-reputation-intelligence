"""Argus context helpers for the restored BettaFish engines."""

from __future__ import annotations

import json
import re
from datetime import date, datetime
from typing import Any


ARGUS_CONTEXT_JSON_RE = re.compile(
    r"<ARGUS_CONTEXT_JSON>\s*(.*?)\s*</ARGUS_CONTEXT_JSON>",
    flags=re.DOTALL,
)


def build_report_structure_input(query: str, argus_context: str | None = None) -> str:
    clean_query = str(query or "").strip()
    context = str(argus_context or "").strip()
    if not context:
        return clean_query
    return (
        f"{clean_query}\n\n"
        "<ARGUS_ENGINE_CONTEXT>\n"
        f"{context}\n"
        "</ARGUS_ENGINE_CONTEXT>"
    )


def coerce_argus_context(value: Any) -> str:
    return str(value or "").strip()


def extract_argus_time_window(value: Any) -> tuple[str, str] | None:
    """Return the confirmed Argus date window as ISO dates when available."""
    text = str(value or "")
    candidates: list[str] = []

    match = ARGUS_CONTEXT_JSON_RE.search(text)
    if match:
        try:
            payload = json.loads(match.group(1))
            request = payload.get("research_request") if isinstance(payload, dict) else {}
            if isinstance(request, dict):
                candidates.append(str(request.get("timeWindow") or ""))
        except (TypeError, ValueError, json.JSONDecodeError):
            pass

    candidates.append(text)
    for candidate in candidates:
        window = _parse_time_window(candidate)
        if window:
            return window
    return None


def clamp_date_range_to_argus_window(
    start_date: str,
    end_date: str,
    argus_context: Any,
) -> tuple[str, str, bool]:
    """Clamp generated tool dates to the user-confirmed Argus window."""
    window = extract_argus_time_window(argus_context)
    if not window:
        return start_date, end_date, False

    parsed_start = _parse_iso_date(start_date)
    parsed_end = _parse_iso_date(end_date)
    window_start = _parse_iso_date(window[0])
    window_end = _parse_iso_date(window[1])
    if not parsed_start or not parsed_end or not window_start or not window_end:
        return start_date, end_date, False

    clamped_start = max(parsed_start, window_start)
    clamped_end = min(parsed_end, window_end)
    if clamped_start > clamped_end:
        clamped_start, clamped_end = window_start, window_end

    next_start = clamped_start.isoformat()
    next_end = clamped_end.isoformat()
    return next_start, next_end, (next_start, next_end) != (start_date, end_date)


def is_datetime_within_argus_window(value: Any, argus_context: Any) -> bool:
    """Return False only when a known timestamp is outside the confirmed window."""
    window = extract_argus_time_window(argus_context)
    if not window:
        return True

    candidate = _coerce_date(value)
    window_start = _parse_iso_date(window[0])
    window_end = _parse_iso_date(window[1])
    if not candidate or not window_start or not window_end:
        return True
    return window_start <= candidate <= window_end


def _parse_time_window(value: str) -> tuple[str, str] | None:
    text = str(value or "")
    iso_dates = re.findall(r"\d{4}-\d{1,2}-\d{1,2}", text)
    if len(iso_dates) >= 2:
        return _normalize_date_pair(iso_dates[0], iso_dates[1])

    chinese_dates = re.findall(
        r"(\d{4})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日?",
        text,
    )
    if len(chinese_dates) >= 2:
        first = "-".join(chinese_dates[0])
        second = "-".join(chinese_dates[1])
        return _normalize_date_pair(first, second)

    return None


def _normalize_date_pair(start: str, end: str) -> tuple[str, str] | None:
    start_date = _parse_iso_date(start)
    end_date = _parse_iso_date(end)
    if not start_date or not end_date:
        return None
    if start_date > end_date:
        start_date, end_date = end_date, start_date
    return start_date.isoformat(), end_date.isoformat()


def _parse_iso_date(value: str) -> date | None:
    match = re.fullmatch(r"\s*(\d{4})-(\d{1,2})-(\d{1,2})\s*", str(value or ""))
    if not match:
        return None
    try:
        return date(int(match.group(1)), int(match.group(2)), int(match.group(3)))
    except ValueError:
        return None


def _coerce_date(value: Any) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, (int, float)):
        try:
            timestamp = float(value)
            if timestamp > 1_000_000_000_000:
                timestamp = timestamp / 1000
            return datetime.fromtimestamp(timestamp).date()
        except (OverflowError, OSError, ValueError):
            return None
    text = str(value or "").strip()
    if not text:
        return None
    iso_prefix = re.match(r"(\d{4}-\d{1,2}-\d{1,2})", text)
    if iso_prefix:
        return _parse_iso_date(iso_prefix.group(1))
    return None
