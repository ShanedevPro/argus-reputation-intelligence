from __future__ import annotations

import asyncio
import os
import queue
import tempfile
import threading
from pathlib import Path
from typing import Any, Dict, Iterable

from .argus_html import ArgusHTMLRenderer


class ArgusPDFExportError(RuntimeError):
    """Raised when Argus HTML to PDF export cannot run."""


def _candidate_chrome_paths() -> Iterable[Path]:
    env_path = os.environ.get("ARGUS_CHROME_PATH")
    if env_path:
        yield Path(env_path)

    for path in (
        "/usr/bin/google-chrome",
        "/usr/bin/google-chrome-stable",
        "/usr/bin/chromium",
        "/usr/bin/chromium-browser",
    ):
        yield Path(path)


def find_chrome_executable() -> Path | None:
    for path in _candidate_chrome_paths():
        if path.exists() and os.access(path, os.X_OK):
            return path
    return None


def _load_async_playwright():
    try:
        from playwright.async_api import async_playwright
    except ModuleNotFoundError as exc:
        raise ArgusPDFExportError(
            "Python Playwright is not installed; cannot export Argus PDF."
        ) from exc
    return async_playwright


async def _print_html_to_pdf(
    html_path: Path,
    pdf_path: Path,
    *,
    chrome_path: str | None = None,
) -> None:
    async_playwright = _load_async_playwright()
    launch_options: dict[str, Any] = {"headless": True}
    if chrome_path:
        launch_options["executable_path"] = chrome_path

    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(**launch_options)
        try:
            page = await browser.new_page(viewport={"width": 1240, "height": 1754})
            await page.goto(html_path.resolve().as_uri(), wait_until="networkidle")
            await page.evaluate(
                "() => document.fonts && document.fonts.ready ? document.fonts.ready : Promise.resolve()"
            )
            await page.wait_for_function(
                "() => window.__ARGUS_PRINT_READY__ === true",
                timeout=30000,
            )
            await page.emulate_media(media="print")
            await page.pdf(
                path=str(pdf_path),
                format="A4",
                print_background=True,
                prefer_css_page_size=True,
            )
        finally:
            await browser.close()


def _run_print_html_to_pdf(
    html_path: Path,
    pdf_path: Path,
    *,
    chrome_path: str | None = None,
) -> None:
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        asyncio.run(
            _print_html_to_pdf(
                html_path,
                pdf_path,
                chrome_path=chrome_path,
            )
        )
        return

    errors: queue.Queue[BaseException] = queue.Queue(maxsize=1)

    def run_in_thread() -> None:
        try:
            asyncio.run(
                _print_html_to_pdf(
                    html_path,
                    pdf_path,
                    chrome_path=chrome_path,
                )
            )
        except BaseException as exc:
            errors.put(exc)

    thread = threading.Thread(target=run_in_thread, name="argus-pdf-export")
    thread.start()
    thread.join()

    if not errors.empty():
        raise errors.get()


class ArgusPDFExporter:
    def __init__(
        self,
        *,
        html_renderer: ArgusHTMLRenderer | None = None,
        chrome_path: str | None = None,
    ):
        self.html_renderer = html_renderer or ArgusHTMLRenderer()
        if chrome_path is not None:
            self.chrome_path = chrome_path
        else:
            discovered_chrome = find_chrome_executable()
            self.chrome_path = str(discovered_chrome) if discovered_chrome else None

    def render_to_pdf(
        self,
        document_ir: Dict[str, Any],
        output_path: str | Path,
        *,
        ir_file_path: str | None = None,
    ) -> Path:
        output = Path(output_path)
        output.parent.mkdir(parents=True, exist_ok=True)

        try:
            html = self.html_renderer.render(document_ir, ir_file_path=ir_file_path)
            with tempfile.TemporaryDirectory(prefix="argus-pdf-") as temp_dir:
                html_path = Path(temp_dir) / "argus_report.html"
                html_path.write_text(html, encoding="utf-8")
                _run_print_html_to_pdf(
                    html_path,
                    output,
                    chrome_path=self.chrome_path,
                )
        except ArgusPDFExportError:
            raise
        except Exception as exc:
            raise ArgusPDFExportError(f"Argus PDF export failed: {exc}") from exc

        return output

    def render_to_bytes(
        self,
        document_ir: Dict[str, Any],
        *,
        ir_file_path: str | None = None,
    ) -> bytes:
        with tempfile.TemporaryDirectory(prefix="argus-pdf-bytes-") as temp_dir:
            output_path = Path(temp_dir) / "report.pdf"
            self.render_to_pdf(document_ir, output_path, ir_file_path=ir_file_path)
            return output_path.read_bytes()


__all__ = ["ArgusPDFExporter", "ArgusPDFExportError", "find_chrome_executable"]
