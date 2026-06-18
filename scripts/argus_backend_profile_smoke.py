#!/usr/bin/env python3
"""Backend-only Argus profile smoke with durable diagnostics.

This runner exercises the same Flask search/report endpoints as the frontend
workflow after data prep. It is intentionally not a product workflow; it exists
so long local smokes leave a clear last-known stage when the process is killed.
"""

from __future__ import annotations

import argparse
import faulthandler
import json
import os
import sys
import time
import traceback
from datetime import datetime
from pathlib import Path
from typing import Any, Mapping

try:
    from dotenv import load_dotenv
except Exception:  # pragma: no cover - optional runtime helper
    load_dotenv = None


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_POLL_SECONDS = 30


class SmokeRecorder:
    def __init__(self, output_dir: Path | str):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.stage = "created"
        self.details: dict[str, Any] = {}
        self.started_at = datetime.now()

    def write_start(self, payload: Mapping[str, Any]) -> None:
        self._write_json(
            "smoke-started.json",
            {
                **dict(payload),
                "started_at": self.started_at.isoformat(),
            },
        )

    def set_stage(self, stage: str, details: Mapping[str, Any] | None = None) -> None:
        self.stage = stage
        self.details = dict(details or {})
        self.write_heartbeat()

    def write_heartbeat(self) -> None:
        self._write_json(
            "heartbeat.json",
            {
                "stage": self.stage,
                "details": self.details,
                "updated_at": datetime.now().isoformat(),
            },
        )

    def write_exit(
        self,
        *,
        exit_code: int,
        result: Mapping[str, Any] | None = None,
        exception: str = "",
    ) -> None:
        self._write_json(
            "smoke-exit.json",
            {
                "exit_code": exit_code,
                "stage": self.stage,
                "details": self.details,
                "result": dict(result or {}),
                "exception": exception,
                "started_at": self.started_at.isoformat(),
                "finished_at": datetime.now().isoformat(),
            },
        )

    def write_artifact(self, filename: str, payload: Mapping[str, Any]) -> None:
        self._write_json(filename, dict(payload))

    def _write_json(self, filename: str, payload: Mapping[str, Any]) -> None:
        path = self.output_dir / filename
        tmp_path = path.with_suffix(path.suffix + ".tmp")
        tmp_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp_path.replace(path)


def restore_crawl_task_from_payload(payload: Mapping[str, Any], crawl_tasks: Any) -> Any:
    task_payload = dict(payload.get("task") or payload)
    analysis_query = str(task_payload.get("analysis_query") or "").strip()
    if not analysis_query:
        raise ValueError("cached crawl payload is missing task.analysis_query")

    task = crawl_tasks.create_task(
        analysis_query=analysis_query,
        data_request=str(task_payload.get("data_request") or analysis_query),
        platforms=task_payload.get("platforms") or ["wb"],
        provider=str(task_payload.get("provider") or "tikhub"),
        caps=dict(task_payload.get("caps") or {}),
    )
    reportability = dict(task_payload.get("reportability") or {})
    if (
        task_payload.get("status") != "reportable"
        or reportability.get("status") != "reportable"
        or reportability.get("can_start_analysis") is not True
    ):
        raise ValueError("cached crawl payload is not reportable")

    task.mark_reportable(
        import_result=dict(task_payload.get("import_result") or {}),
        readiness=dict(task_payload.get("readiness") or {}),
        reportability=reportability,
        bundle_metadata=dict(task_payload.get("bundle_metadata") or {}),
        evidence_manifest=dict(task_payload.get("evidence_manifest") or {}),
    )
    return task


def load_json(path: Path | str) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def build_engine_artifacts_from_args(args: argparse.Namespace) -> dict[str, dict[str, str]]:
    artifacts: dict[str, dict[str, str]] = {}
    for item in args.engine_artifact or []:
        engine, sep, path = str(item).partition("=")
        if not sep or not engine.strip() or not path.strip():
            raise ValueError("--engine-artifact must use engine=/path/to/report.md")
        artifacts[engine.strip()] = {"output_file": path.strip()}

    if args.resume_engine and not args.resume_search_status:
        raise ValueError("--resume-search-status is required with --resume-engine")

    if args.resume_search_status:
        payload = load_json(args.resume_search_status)
        engines = dict(payload.get("engines") or {})
        for engine_name in args.resume_engine or []:
            status = engines.get(engine_name)
            if status is None:
                raise ValueError(f"{engine_name} is missing from resume status")
            status = dict(status or {})
            if status.get("status") != "completed" or status.get("evidence_status") != "ready":
                raise ValueError(f"{engine_name} is not completed with ready evidence in resume status")
            output_file = str(status.get("output_file") or "").strip()
            if not output_file:
                raise ValueError(f"{engine_name} resume status is missing output_file")
            artifacts[engine_name] = {"output_file": output_file}
    return artifacts


def load_runtime_env(env_file: str = "") -> None:
    if load_dotenv is None:
        return
    if env_file:
        load_dotenv(Path(env_file), override=False)
    load_dotenv(ROOT / ".env", override=False)


def import_flask_app() -> Any:
    import app as flask_app_module

    return flask_app_module


def create_fresh_crawl_task(
    client: Any,
    *,
    query: str,
    request_file: str,
) -> dict[str, Any]:
    if not query.strip():
        raise ValueError("--query is required when --crawl-response is not provided")
    if not request_file:
        raise ValueError("--request-file is required when --crawl-response is not provided")

    request_payload = load_json(request_file)
    response = client.post(
        "/api/crawl/tasks",
        json={
            "analysis_query": query,
            "data_request": request_payload,
            "platforms": ["wb"],
        },
    )
    payload = response.get_json(silent=True) or {}
    if response.status_code >= 400 or not payload.get("task"):
        raise RuntimeError(f"crawl start failed: {response.status_code} {payload}")

    task = dict(payload["task"])
    if task.get("status") != "reportable":
        raise RuntimeError(
            f"crawl not reportable: {task.get('status')} {task.get('error_message') or task.get('next_action') or ''}"
        )
    return task


def run_smoke(
    args: argparse.Namespace,
    recorder: SmokeRecorder | None = None,
) -> dict[str, Any]:
    recorder = recorder or SmokeRecorder(args.output_dir)
    mode = "cached_crawl" if args.crawl_response else "fresh_crawl"
    engine_artifacts = build_engine_artifacts_from_args(args)
    recorder.write_start(
        {
            "event": args.event_label,
            "crawl_response": args.crawl_response,
            "request_file": getattr(args, "request_file", ""),
            "query": getattr(args, "query", ""),
            "mode": mode,
            "timeout_minutes": args.timeout_minutes,
            "poll_seconds": args.poll_seconds,
            "engine_artifacts": engine_artifacts,
        }
    )

    load_runtime_env(args.env_file)
    os.environ["ARGUS_SEARCH_ENGINE_CONCURRENCY"] = "sequential"
    os.environ.setdefault("ARGUS_SEARCH_ENGINE_MAX_REFLECTIONS", "1")
    os.environ.setdefault("ARGUS_SEARCH_ENGINE_MAX_PARAGRAPHS", "5")
    os.environ.setdefault("ARGUS_INSIGHT_MAX_AUTO_SENTIMENT_SEARCHES", "1")
    os.environ.setdefault("KEYWORD_OPTIMIZER_MAX_KEYWORDS", "8")

    sys.path.insert(0, str(ROOT))
    recorder.set_stage("importing_app")
    flask_app_module = import_flask_app()

    client = flask_app_module.app.test_client()
    if args.crawl_response:
        recorder.set_stage("restoring_crawl", {"crawl_response": args.crawl_response})
        task = restore_crawl_task_from_payload(
            load_json(args.crawl_response),
            flask_app_module.crawl_tasks,
        )
        crawl_task_payload = task.to_dict()
        recorder.write_artifact("restored-crawl-task.json", crawl_task_payload)
    else:
        recorder.set_stage("creating_crawl", {"request_file": args.request_file})
        crawl_task_payload = create_fresh_crawl_task(
            client,
            query=args.query,
            request_file=args.request_file,
        )
        recorder.write_artifact("crawl-created.json", crawl_task_payload)

    crawl_task_id = str(crawl_task_payload["task_id"])
    analysis_query = str(crawl_task_payload.get("analysis_query") or args.query or "").strip()
    recorder.set_stage("starting_search", {"crawl_task_id": crawl_task_id})
    search_response = client.post(
        "/api/search",
        json={
            "query": analysis_query,
            "data_prep_task_id": crawl_task_id,
            "engine_artifacts": engine_artifacts,
        },
    )
    search_payload = search_response.get_json(silent=True) or {}
    recorder.write_artifact("search-started.json", search_payload)
    if search_response.status_code >= 400 or not search_payload.get("task_id"):
        raise RuntimeError(f"search start failed: {search_response.status_code} {search_payload}")

    search_task_id = str(search_payload["task_id"])
    deadline = time.monotonic() + max(1, int(args.timeout_minutes)) * 60
    report_task_id = ""
    last_search_payload: dict[str, Any] = {}
    last_report_payload: dict[str, Any] = {}

    while time.monotonic() < deadline:
        recorder.set_stage("polling_search", {"search_task_id": search_task_id})
        search_status = client.get(f"/api/search/status/{search_task_id}")
        last_search_payload = search_status.get_json(silent=True) or {}
        recorder.write_artifact("search-latest.json", last_search_payload)
        status = str(last_search_payload.get("status") or "")
        if last_search_payload.get("report_task_id"):
            report_task_id = str(last_search_payload["report_task_id"])

        if status in {"error", "blocked"}:
            result = {
                "status": status,
                "search_task_id": search_task_id,
                "report_task_id": report_task_id,
                "message": last_search_payload.get("error_message")
                or last_search_payload.get("blocked_reason")
                or "",
            }
            recorder.set_stage("search_terminal", result)
            return result

        if report_task_id:
            recorder.set_stage("polling_report", {"report_task_id": report_task_id})
            report_status = client.get(f"/api/report/progress/{report_task_id}")
            last_report_payload = report_status.get_json(silent=True) or {}
            recorder.write_artifact("report-latest.json", last_report_payload)
            report_task = dict(last_report_payload.get("task") or {})
            if report_task.get("status") == "completed" and report_task.get("report_file_ready"):
                result = {
                    "status": "report-ready",
                    "search_task_id": search_task_id,
                    "report_task_id": report_task_id,
                    "report_file_path": report_task.get("report_file_path") or "",
                    "markdown_file_path": report_task.get("markdown_file_path") or "",
                    "pdf_file_path": report_task.get("pdf_file_path") or "",
                }
                recorder.set_stage("report_ready", result)
                return result
            if report_task.get("status") == "error":
                result = {
                    "status": "report-error",
                    "search_task_id": search_task_id,
                    "report_task_id": report_task_id,
                    "message": report_task.get("error_message") or "",
                }
                recorder.set_stage("report_terminal", result)
                return result

        time.sleep(max(1, int(args.poll_seconds)))

    result = {
        "status": "timeout",
        "search_task_id": search_task_id,
        "report_task_id": report_task_id,
        "last_search_status": last_search_payload.get("status"),
        "last_report_status": (last_report_payload.get("task") or {}).get("status"),
    }
    recorder.set_stage("timeout", result)
    return result


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--crawl-response", default="")
    parser.add_argument("--request-file", default="")
    parser.add_argument("--query", default="")
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--event-label", default="profile-smoke")
    parser.add_argument("--env-file", default=os.environ.get("ARGUS_ENV_FILE", ""))
    parser.add_argument("--timeout-minutes", type=int, default=120)
    parser.add_argument("--poll-seconds", type=int, default=DEFAULT_POLL_SECONDS)
    parser.add_argument("--resume-search-status", default="")
    parser.add_argument("--resume-engine", action="append", default=[])
    parser.add_argument("--engine-artifact", action="append", default=[])
    args = parser.parse_args(argv)
    if not args.crawl_response and not (args.request_file and args.query):
        parser.error("either --crawl-response or both --request-file and --query are required")
    return args


def main(argv: list[str] | None = None) -> int:
    faulthandler.enable()
    args = parse_args(list(argv or sys.argv[1:]))
    recorder = SmokeRecorder(args.output_dir)
    try:
        result = run_smoke(args, recorder)
        recorder.write_artifact("smoke-result.json", result)
        exit_code = 0 if result.get("status") == "report-ready" else 1
        recorder.write_exit(exit_code=exit_code, result=result)
        return exit_code
    except BaseException as exc:
        exception = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
        recorder.set_stage("exception", {"error": str(exc)})
        recorder.write_exit(exit_code=1, exception=exception)
        print(exception, file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
