"""Explicit ForumEngine synthesis for search orchestration."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any


def run_forum_synthesis(task: Any, *, log_path: str = "logs/forum.log") -> dict[str, Any]:
    """Run ForumHost over completed engine reports and append a HOST synthesis."""
    from ForumEngine.llm_host import generate_host_speech

    materials: list[str] = []
    for engine_name, status in getattr(task, "engines", {}).items():
        output_file = getattr(status, "output_file", "")
        if not output_file:
            continue
        try:
            content = Path(output_file).read_text(encoding="utf-8")
        except Exception:
            content = ""
        if content.strip():
            materials.append(f"[00:00:00] [{engine_name.upper()}] {content}")

    if not materials:
        return {
            "success": False,
            "message": "No engine materials were available for ForumEngine synthesis.",
        }

    speech = generate_host_speech(materials)
    if not speech:
        return {
            "success": False,
            "message": "ForumEngine synthesis returned no content.",
        }

    path = Path(log_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%H:%M:%S")
    one_line = speech.replace("\n", "\\n").replace("\r", "\\r")
    with path.open("a", encoding="utf-8") as handle:
        handle.write(f"[{timestamp}] [HOST] {one_line}\n")

    return {"success": True, "forum_log_path": str(path), "summary": speech}
