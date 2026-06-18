"""Backend one-click search orchestration for BettaFish."""

from __future__ import annotations

import threading
import time
import importlib.util
import inspect
import json
import re
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Mapping, Optional
from uuid import uuid4

from loguru import logger

from utils.evidence_summary import load_evidence_summary
from utils.research_brief_builder import (
    build_common_research_context,
    build_engine_brief,
)


ENGINE_NAMES = ("insight", "media", "query")
ENGINE_OUTPUT_DIRS = {
    "insight": "insight_engine_streamlit_reports",
    "media": "media_engine_streamlit_reports",
    "query": "query_engine_streamlit_reports",
}
DEFAULT_ENGINE_TIMEOUT_SECONDS = 5400


@dataclass
class EngineRunStatus:
    status: str = "pending"
    output_file: str = ""
    error_message: str = ""
    evidence_status: str = ""
    evidence_source_count: int = 0
    evidence_items: List[Dict[str, Any]] = field(default_factory=list)
    evidence_file: str = ""
    evidence_generated_at: str = ""
    started_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    def mark_running(self) -> None:
        now = datetime.now()
        self.status = "running"
        self.started_at = now
        self.updated_at = now

    def mark_completed(self, output_file: str) -> None:
        self.status = "completed"
        self.output_file = output_file
        self.updated_at = datetime.now()

    def mark_error(self, error_message: str) -> None:
        self.status = "error"
        self.error_message = error_message
        self.updated_at = datetime.now()

    def mark_evidence(self, summary: Mapping[str, Any], evidence_file: str) -> None:
        self.evidence_status = str(summary.get("evidence_status") or "no_data")
        self.evidence_source_count = int(summary.get("source_count") or 0)
        items = summary.get("evidence_items") or []
        self.evidence_items = [dict(item) for item in items if isinstance(item, Mapping)]
        self.evidence_file = evidence_file
        self.evidence_generated_at = str(summary.get("generated_at") or "")
        self.updated_at = datetime.now()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "status": self.status,
            "output_file": self.output_file,
            "error_message": self.error_message,
            "evidence_status": self.evidence_status,
            "evidence_source_count": self.evidence_source_count,
            "evidence_items": self.evidence_items,
            "evidence_file": self.evidence_file,
            "evidence_generated_at": self.evidence_generated_at,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


@dataclass
class SearchTask:
    task_id: str
    query: str
    data_prep_task_id: str = ""
    research_request: Dict[str, Any] = field(default_factory=dict)
    evidence_manifest: Dict[str, Any] = field(default_factory=dict)
    engine_briefs: Dict[str, str] = field(default_factory=dict)
    forum_synthesis: Dict[str, Any] = field(default_factory=dict)
    resumed_engine_artifacts: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    status: str = "pending"
    report_task_id: Optional[str] = None
    data_ready: bool = False
    blocked_reason: str = ""
    error_message: str = ""
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    engines: Dict[str, EngineRunStatus] = field(
        default_factory=lambda: {name: EngineRunStatus() for name in ENGINE_NAMES}
    )

    def mark_status(self, status: str, error_message: str = "") -> None:
        self.status = status
        if error_message:
            self.error_message = error_message
        self.updated_at = datetime.now()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "success": True,
            "task_id": self.task_id,
            "query": self.query,
            "data_prep_task_id": self.data_prep_task_id,
            "research_brief": {
                "enabled": bool(self.engine_briefs),
                "engine_briefs": sorted(self.engine_briefs.keys()),
            },
            "forum_synthesis": self.forum_synthesis,
            "status": self.status,
            "report_task_id": self.report_task_id,
            "data_ready": self.data_ready,
            "blocked_reason": self.blocked_reason,
            "error_message": self.error_message,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "status_url": f"/api/search/status/{self.task_id}",
            "engines": {name: status.to_dict() for name, status in self.engines.items()},
        }


EngineRunner = Callable[[str], Any]
BaselineResetter = Callable[..., None]
ReportStarter = Callable[..., Mapping[str, Any]]
EnginePreflight = Callable[[], Mapping[str, str]]
ForumSynthesisRunner = Callable[[SearchTask], Mapping[str, Any]]


class SearchOrchestrator:
    def __init__(
        self,
        engine_runners: Optional[Mapping[str, EngineRunner]] = None,
        reset_report_baseline: Optional[BaselineResetter] = None,
        start_report_task: Optional[ReportStarter] = None,
        engine_preflight: Optional[EnginePreflight] = None,
        forum_synthesis_runner: Optional[ForumSynthesisRunner] = None,
        run_async: bool = True,
        engine_concurrency: Optional[str] = None,
        engine_timeout_seconds: Optional[float] = None,
    ):
        uses_default_engine_runners = engine_runners is None
        self.engine_runners = dict(engine_runners or _default_engine_runners())
        self.reset_report_baseline = reset_report_baseline or _reset_report_baseline
        self.start_report_task = start_report_task or _default_start_report_task
        self.forum_synthesis_runner = (
            forum_synthesis_runner
            if forum_synthesis_runner is not None
            else _default_forum_synthesis_runner
            if uses_default_engine_runners
            else _noop_forum_synthesis_runner
        )
        self.engine_preflight = (
            engine_preflight
            if engine_preflight is not None
            else _default_engine_preflight
            if uses_default_engine_runners
            else lambda: {}
        )
        self.run_async = bool(run_async)
        normalized_concurrency = str(
            engine_concurrency or _default_engine_concurrency()
        ).strip().lower()
        self.engine_concurrency = (
            "concurrent" if normalized_concurrency == "concurrent" else "sequential"
        )
        self.engine_timeout_seconds = (
            _default_engine_timeout_seconds()
            if engine_timeout_seconds is None
            else float(engine_timeout_seconds)
        )
        self._tasks: Dict[str, SearchTask] = {}
        self._lock = threading.RLock()

    def start_search(
        self,
        query: str,
        *,
        research_request: Optional[Mapping[str, Any]] = None,
        evidence_manifest: Optional[Mapping[str, Any]] = None,
        data_prep_task_id: str = "",
        engine_artifacts: Optional[Mapping[str, Any]] = None,
    ) -> Dict[str, Any]:
        query = (query or "").strip()
        if not query:
            return {"success": False, "message": "搜索查询不能为空"}

        research_request_payload = dict(research_request or {})
        evidence_manifest_payload = dict(evidence_manifest or {})
        engine_briefs: Dict[str, str] = {}
        if research_request_payload or evidence_manifest_payload:
            context = build_common_research_context(
                query=query,
                research_request=research_request_payload,
                evidence_manifest=evidence_manifest_payload,
                data_prep_task_id=data_prep_task_id,
            )
            engine_briefs = {
                name: build_engine_brief(name, context) for name in ENGINE_NAMES
            }

        try:
            resumed_engines = self._validate_engine_artifacts(
                {} if engine_artifacts is None else engine_artifacts,
                query=query,
            )
        except (TypeError, ValueError) as exc:
            return {"success": False, "message": str(exc)}

        task = SearchTask(
            task_id=f"search_{int(time.time())}_{uuid4().hex[:8]}",
            query=query,
            data_prep_task_id=str(data_prep_task_id or "").strip(),
            research_request=research_request_payload,
            evidence_manifest=evidence_manifest_payload,
            engine_briefs=engine_briefs,
            resumed_engine_artifacts=resumed_engines,
        )

        with self._lock:
            self._tasks[task.task_id] = task

        if self.run_async:
            threading.Thread(target=self._run_task, args=(task,), daemon=True).start()
        else:
            self._run_task(task)

        return task.to_dict()

    def get_status(self, task_id: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            task = self._tasks.get(task_id)
            return self._status_snapshot(task) if task else None

    def _status_snapshot(self, task: SearchTask) -> Dict[str, Any]:
        now = datetime.now()
        if task.status == "running":
            task.updated_at = now
            for status in task.engines.values():
                if status.status == "running":
                    status.updated_at = now
        return task.to_dict()

    def _run_task(self, task: SearchTask) -> None:
        try:
            self._set_task_status(task, "running")
            self._reset_report_baseline_for_task(task)
            self._apply_resumed_engine_artifacts(task)
            missing_dependencies = {
                engine_name: message
                for engine_name, message in dict(self.engine_preflight() or {}).items()
                if task.engines.get(engine_name, EngineRunStatus()).status != "completed"
            }
            if missing_dependencies:
                with self._lock:
                    for engine_name, message in missing_dependencies.items():
                        if engine_name in task.engines:
                            task.engines[engine_name].mark_error(message)
                    failed = self._failed_engine_names(task)
                self._set_task_status(task, "error", f"引擎失败: {', '.join(failed)}")
                return

            if self.engine_concurrency == "concurrent":
                self._run_engines_concurrently(task)
            else:
                self._run_engines_sequentially(task)

            failed = [
                name
                for name, status in task.engines.items()
                if status.status == "error"
            ]
            if failed:
                self._set_task_status(task, "error", self._format_engine_failure(task))
                return

            if not self._evaluate_data_gate(task):
                return

            forum_result = dict(self.forum_synthesis_runner(task) or {})
            with self._lock:
                task.forum_synthesis = forum_result
            if not forum_result.get("success"):
                message = forum_result.get("message") or "ForumEngine synthesis failed"
                self._set_task_status(task, "error", message)
                return

            data_bundles = self._build_report_data_bundles(task)
            engine_files = self._build_report_engine_files(task)
            report_result = dict(
                self._call_start_report_task(
                    task.query,
                    data_bundles=data_bundles,
                    engine_files=engine_files,
                )
                or {}
            )
            if not report_result.get("success"):
                message = report_result.get("error") or report_result.get("message") or "ReportEngine启动失败"
                self._set_task_status(task, "error", message)
                return

            with self._lock:
                task.report_task_id = report_result.get("task_id")
            self._set_task_status(task, "completed")
        except Exception as exc:
            logger.exception(f"搜索编排任务失败: {exc}")
            self._set_task_status(task, "error", str(exc))

    def _run_engines_sequentially(self, task: SearchTask) -> None:
        for engine_name in ENGINE_NAMES:
            if task.engines[engine_name].status == "completed":
                continue

            if self.engine_timeout_seconds <= 0:
                self._run_one_engine(task, engine_name)
            else:
                executor = ThreadPoolExecutor(max_workers=1)
                future = executor.submit(self._run_one_engine, task, engine_name)
                try:
                    completed, _pending = wait(
                        {future},
                        timeout=self.engine_timeout_seconds,
                        return_when=FIRST_COMPLETED,
                    )
                    if not completed:
                        message = (
                            f"Engine timed out after {self.engine_timeout_seconds:g} seconds"
                        )
                        with self._lock:
                            task.engines[engine_name].mark_error(message)
                            task.updated_at = datetime.now()
                        self._set_task_status(task, "error", f"引擎超时: {engine_name}")
                        return
                    future.result()
                finally:
                    executor.shutdown(wait=False, cancel_futures=True)

            if task.engines[engine_name].status == "error":
                return

    def _run_engines_concurrently(self, task: SearchTask) -> None:
        engine_names = [
            engine_name
            for engine_name in ENGINE_NAMES
            if task.engines[engine_name].status != "completed"
        ]
        if not engine_names:
            return

        executor = ThreadPoolExecutor(max_workers=len(engine_names))
        futures = {
            executor.submit(self._run_one_engine, task, engine_name): engine_name
            for engine_name in engine_names
        }
        pending = set(futures)
        deadline = (
            time.monotonic() + self.engine_timeout_seconds
            if self.engine_timeout_seconds > 0
            else None
        )

        try:
            while pending:
                wait_timeout = None
                if deadline is not None:
                    wait_timeout = max(0.0, deadline - time.monotonic())
                    if wait_timeout == 0:
                        break

                completed, pending = wait(
                    pending,
                    timeout=wait_timeout,
                    return_when=FIRST_COMPLETED,
                )
                if not completed:
                    break

                for future in completed:
                    future.result()
                failed = self._failed_engine_names(task)
                if failed:
                    self._set_task_status(task, "error", self._format_engine_failure(task))
                    return

            if pending:
                timed_out = [futures[future] for future in pending]
                message = f"Engine timed out after {self.engine_timeout_seconds:g} seconds"
                with self._lock:
                    for engine_name in timed_out:
                        task.engines[engine_name].mark_error(message)
                        task.updated_at = datetime.now()
                self._set_task_status(task, "error", f"引擎超时: {', '.join(timed_out)}")
        finally:
            executor.shutdown(wait=False, cancel_futures=True)

    def _build_report_data_bundles(self, task: SearchTask) -> List[Dict[str, Any]]:
        if not task.evidence_manifest:
            return []
        manifest = dict(task.evidence_manifest)
        sentiment = _load_insight_sentiment_analysis(task.engines.get("insight"))
        if sentiment and not isinstance(manifest.get("sentiment_analysis"), Mapping):
            manifest["sentiment_analysis"] = sentiment
        return [
            {
                **manifest,
                "type": "weibo_evidence_manifest",
            }
        ]

    def _run_one_engine(self, task: SearchTask, engine_name: str) -> None:
        runner = self.engine_runners[engine_name]
        with self._lock:
            task.engines[engine_name].mark_running()
            task.updated_at = datetime.now()

        try:
            argus_context = task.engine_briefs.get(engine_name, "")
            if _runner_accepts_argus_context(runner):
                result = runner(task.query, argus_context=argus_context)
            else:
                result = runner(task.query)
            output_file = _normalize_output_file(result, engine_name)
            evidence_summary, evidence_file = _load_engine_evidence_summary(
                engine_name, output_file
            )
            with self._lock:
                if task.engines[engine_name].status == "error":
                    return
                task.engines[engine_name].mark_completed(output_file)
                task.engines[engine_name].mark_evidence(evidence_summary, evidence_file)
                task.updated_at = datetime.now()
        except Exception as exc:
            logger.exception(f"{engine_name} 引擎运行失败: {exc}")
            with self._lock:
                if task.engines[engine_name].status != "error":
                    task.engines[engine_name].mark_error(str(exc))
                task.updated_at = datetime.now()

    def _set_task_status(self, task: SearchTask, status: str, error_message: str = "") -> None:
        with self._lock:
            task.mark_status(status, error_message)

    def _failed_engine_names(self, task: SearchTask) -> List[str]:
        with self._lock:
            return [
                name
                for name, status in task.engines.items()
                if status.status == "error"
            ]

    def _format_engine_failure(self, task: SearchTask) -> str:
        with self._lock:
            failed = [
                (name, status.error_message)
                for name, status in task.engines.items()
                if status.status == "error"
            ]
        failed_names = [name for name, _message in failed]
        has_timeout = any("timed out" in message or "超时" in message for _name, message in failed)
        label = "引擎超时" if has_timeout else "引擎失败"
        return f"{label}: {', '.join(failed_names)}"

    def _evaluate_data_gate(self, task: SearchTask) -> bool:
        no_data_engines = [
            name
            for name, status in task.engines.items()
            if status.evidence_status != "ready"
        ]
        with self._lock:
            task.data_ready = not no_data_engines
            if no_data_engines:
                labels = ", ".join(no_data_engines)
                task.blocked_reason = f"证据不足，未启动正式分析: {labels}"
                task.mark_status("blocked")
                return False

            task.blocked_reason = ""
            task.updated_at = datetime.now()
            return True

    def _validate_engine_artifacts(
        self,
        engine_artifacts: Mapping[str, Any],
        *,
        query: str,
    ) -> Dict[str, Dict[str, Any]]:
        if not isinstance(engine_artifacts, Mapping):
            raise TypeError("engine_artifacts must be a JSON object")

        resumed: Dict[str, Dict[str, Any]] = {}
        for engine_name, raw_payload in engine_artifacts.items():
            if engine_name not in ENGINE_NAMES:
                raise ValueError(f"unknown engine artifact: {engine_name}")
            payload = dict(raw_payload or {})
            output_file = str(payload.get("output_file") or "").strip()
            if not output_file:
                raise ValueError(f"{engine_name} resume artifact is missing output_file")
            path = Path(output_file)
            if not path.exists() or not path.is_file():
                raise ValueError(f"{engine_name} resume artifact file does not exist")
            resolved_path = path.resolve()
            engine_output_dir = Path(ENGINE_OUTPUT_DIRS[engine_name]).resolve()
            if not _path_is_relative_to(resolved_path, engine_output_dir):
                raise ValueError(
                    f"{engine_name} resume artifact must be inside engine output directory"
                )
            evidence_summary, evidence_file = _load_engine_evidence_summary(
                engine_name,
                output_file,
            )
            if evidence_summary.get("evidence_status") != "ready":
                raise ValueError(
                    f"{engine_name} resume artifact does not have ready evidence"
                )
            evidence_engine_name = str(evidence_summary.get("engine_name") or "").strip()
            if evidence_engine_name != engine_name:
                raise ValueError(
                    f"{engine_name} resume artifact evidence engine_name does not match"
                )
            evidence_report_file = str(evidence_summary.get("report_file") or "").strip()
            if evidence_report_file and Path(evidence_report_file).resolve() != resolved_path:
                raise ValueError(
                    f"{engine_name} resume artifact evidence report_file does not match"
                )
            evidence_query = str(evidence_summary.get("query") or "").strip()
            if not _queries_match_for_resume(evidence_query, query):
                raise ValueError(
                    f"{engine_name} resume artifact query does not match current search"
                )
            resumed[engine_name] = {
                "output_file": output_file,
                "evidence_summary": evidence_summary,
                "evidence_file": evidence_file,
            }
        return resumed

    def _reset_report_baseline_for_task(self, task: SearchTask) -> None:
        exclude_files = {
            engine_name: [str(payload["output_file"])]
            for engine_name, payload in task.resumed_engine_artifacts.items()
        }
        _call_reset_report_baseline(self.reset_report_baseline, exclude_files)

    def _apply_resumed_engine_artifacts(self, task: SearchTask) -> None:
        if not task.resumed_engine_artifacts:
            return
        with self._lock:
            for engine_name, payload in task.resumed_engine_artifacts.items():
                status = task.engines[engine_name]
                status.mark_completed(payload["output_file"])
                status.mark_evidence(
                    payload["evidence_summary"],
                    payload["evidence_file"],
                )
            task.updated_at = datetime.now()

    def _build_report_engine_files(self, task: SearchTask) -> Dict[str, str]:
        return {
            engine_name: status.output_file
            for engine_name, status in task.engines.items()
            if engine_name in ENGINE_NAMES and str(status.output_file or "").strip()
        }

    def _call_start_report_task(
        self,
        query: str,
        *,
        data_bundles: Optional[List[Dict[str, Any]]] = None,
        engine_files: Optional[Mapping[str, str]] = None,
    ) -> Mapping[str, Any]:
        kwargs: Dict[str, Any] = {}
        if data_bundles:
            kwargs["data_bundles"] = data_bundles
        if engine_files and _call_start_report_accepts_engine_files(self.start_report_task):
            kwargs["engine_files"] = dict(engine_files)
        return self.start_report_task(query, **kwargs)


def _normalize_output_file(result: Any, engine_name: str) -> str:
    if isinstance(result, Mapping):
        for key in ("output_file", "report_file", "path"):
            value = result.get(key)
            if value:
                return str(value)
    if isinstance(result, (str, Path)):
        return str(result)
    return _latest_markdown_file(ENGINE_OUTPUT_DIRS[engine_name])


def _default_engine_timeout_seconds() -> float:
    try:
        from config import settings as root_settings

        value = getattr(
            root_settings,
            "ARGUS_SEARCH_ENGINE_TIMEOUT_SECONDS",
            DEFAULT_ENGINE_TIMEOUT_SECONDS,
        )
        return float(value or 0)
    except Exception as exc:
        logger.warning(f"读取搜索引擎超时配置失败，使用默认值: {exc}")
        return float(DEFAULT_ENGINE_TIMEOUT_SECONDS)


def _default_engine_concurrency() -> str:
    try:
        from config import settings as root_settings

        value = str(
            getattr(root_settings, "ARGUS_SEARCH_ENGINE_CONCURRENCY", "sequential")
            or "sequential"
        ).strip().lower()
        return "concurrent" if value == "concurrent" else "sequential"
    except Exception as exc:
        logger.warning(f"读取搜索引擎并发配置失败，使用顺序模式: {exc}")
        return "sequential"


def _load_engine_evidence_summary(engine_name: str, output_file: str) -> tuple[Dict[str, Any], str]:
    evidence_file = str(Path(output_file).with_suffix(".evidence.json")) if output_file else ""
    default_summary = {
        "engine_name": engine_name,
        "report_file": output_file,
        "evidence_status": "no_data",
        "source_count": 0,
        "evidence_items": [],
        "generated_at": "",
    }
    if not evidence_file:
        return default_summary, evidence_file

    try:
        loaded = load_evidence_summary(evidence_file)
        if not isinstance(loaded, Mapping):
            raise ValueError("evidence summary must be a JSON object")
    except Exception as exc:
        logger.warning(f"{engine_name} 证据摘要加载失败: {exc}")
        return default_summary, evidence_file

    summary = {**default_summary, **dict(loaded)}
    summary["engine_name"] = summary.get("engine_name") or engine_name
    summary["report_file"] = summary.get("report_file") or output_file
    summary["evidence_status"] = summary.get("evidence_status") or "no_data"
    summary["source_count"] = int(summary.get("source_count") or 0)
    items = summary.get("evidence_items") or []
    summary["evidence_items"] = [dict(item) for item in items if isinstance(item, Mapping)]
    return summary, evidence_file


def _load_insight_sentiment_analysis(status: EngineRunStatus | None) -> Dict[str, Any]:
    if not status or not status.output_file:
        return {}
    sentiment_file = Path(status.output_file).with_suffix(".sentiment.json")
    if not sentiment_file.exists():
        return {}
    try:
        payload = json.loads(sentiment_file.read_text(encoding="utf-8"))
    except Exception as exc:
        logger.warning(f"Insight 情绪分析摘要加载失败: {exc}")
        return {}
    if not isinstance(payload, Mapping):
        return {}

    distribution = payload.get("sentiment_distribution")
    total_analyzed = payload.get("total_analyzed")
    if not isinstance(distribution, Mapping) and not total_analyzed:
        return {}

    sentiment: Dict[str, Any] = {}
    if total_analyzed is not None:
        sentiment["total_analyzed"] = total_analyzed
    if isinstance(distribution, Mapping):
        sentiment["sentiment_distribution"] = dict(distribution)
    if payload.get("analysis_performed") is not None:
        sentiment["analysis_performed"] = payload.get("analysis_performed")
    return sentiment


def _latest_markdown_file(directory: str) -> str:
    path = Path(directory)
    if not path.exists():
        return ""
    markdown_files = [candidate for candidate in path.iterdir() if candidate.suffix == ".md"]
    if not markdown_files:
        return ""
    return str(max(markdown_files, key=lambda candidate: candidate.stat().st_mtime))


def _default_engine_runners() -> Dict[str, EngineRunner]:
    return {
        "insight": _run_insight_engine,
        "media": _run_media_engine,
        "query": _run_query_engine,
    }


def _default_engine_preflight() -> Dict[str, str]:
    missing: Dict[str, str] = {}
    if importlib.util.find_spec("tavily") is None:
        missing["query"] = (
            "Missing Python package tavily-python. Run python -m pip install "
            "-r requirements.txt in the backend environment."
        )
    if importlib.util.find_spec("sqlalchemy") is None:
        missing["insight"] = (
            "Missing Python package SQLAlchemy. Run python -m pip install "
            "-r requirements.txt in the backend environment."
        )
    return missing


def _runner_accepts_argus_context(runner: EngineRunner) -> bool:
    try:
        signature = inspect.signature(runner)
    except (TypeError, ValueError):
        return False
    return (
        "argus_context" in signature.parameters
        or any(
            parameter.kind == inspect.Parameter.VAR_KEYWORD
            for parameter in signature.parameters.values()
        )
    )


def _run_insight_engine(query: str, *, argus_context: str = "") -> str:
    from config import settings as root_settings
    from InsightEngine import DeepSearchAgent, Settings

    config = Settings(
        INSIGHT_ENGINE_API_KEY=root_settings.INSIGHT_ENGINE_API_KEY,
        INSIGHT_ENGINE_BASE_URL=root_settings.INSIGHT_ENGINE_BASE_URL,
        INSIGHT_ENGINE_MODEL_NAME=root_settings.INSIGHT_ENGINE_MODEL_NAME,
        DB_HOST=root_settings.DB_HOST,
        DB_USER=root_settings.DB_USER,
        DB_PASSWORD=root_settings.DB_PASSWORD,
        DB_NAME=root_settings.DB_NAME,
        DB_PORT=root_settings.DB_PORT,
        DB_CHARSET=root_settings.DB_CHARSET,
        DB_DIALECT=root_settings.DB_DIALECT,
        MAX_REFLECTIONS=_root_int_setting(
            "ARGUS_SEARCH_ENGINE_MAX_REFLECTIONS", 1
        ),
        MAX_PARAGRAPHS=_root_int_setting("ARGUS_SEARCH_ENGINE_MAX_PARAGRAPHS", 5),
        MAX_AUTO_SENTIMENT_SEARCHES=_root_int_setting(
            "ARGUS_INSIGHT_MAX_AUTO_SENTIMENT_SEARCHES", 1
        ),
        KEYWORD_OPTIMIZER_MAX_KEYWORDS=_root_int_setting(
            "KEYWORD_OPTIMIZER_MAX_KEYWORDS", 8
        ),
        MAX_CONTENT_LENGTH=500000,
        OUTPUT_DIR=ENGINE_OUTPUT_DIRS["insight"],
    )
    DeepSearchAgent(config).research(query, save_report=True, argus_context=argus_context)
    return _latest_markdown_file(ENGINE_OUTPUT_DIRS["insight"])


def _run_media_engine(query: str, *, argus_context: str = "") -> str:
    from config import settings as root_settings
    from MediaEngine import DeepSearchAgent, AnspireSearchAgent, TavilySearchAgent, Settings

    config_kwargs = {
        "MEDIA_ENGINE_API_KEY": root_settings.MEDIA_ENGINE_API_KEY,
        "MEDIA_ENGINE_BASE_URL": root_settings.MEDIA_ENGINE_BASE_URL,
        "MEDIA_ENGINE_MODEL_NAME": root_settings.MEDIA_ENGINE_MODEL_NAME,
        "SEARCH_TOOL_TYPE": root_settings.SEARCH_TOOL_TYPE,
        "MAX_REFLECTIONS": _root_int_setting(
            "ARGUS_SEARCH_ENGINE_MAX_REFLECTIONS", 1
        ),
        "MAX_PARAGRAPHS": _root_int_setting("ARGUS_SEARCH_ENGINE_MAX_PARAGRAPHS", 5),
        "SEARCH_CONTENT_MAX_LENGTH": 20000,
        "OUTPUT_DIR": ENGINE_OUTPUT_DIRS["media"],
    }
    if root_settings.SEARCH_TOOL_TYPE == "BochaAPI":
        config_kwargs["BOCHA_WEB_SEARCH_API_KEY"] = root_settings.BOCHA_WEB_SEARCH_API_KEY
        agent_cls = DeepSearchAgent
    elif root_settings.SEARCH_TOOL_TYPE == "AnspireAPI":
        config_kwargs["ANSPIRE_API_KEY"] = root_settings.ANSPIRE_API_KEY
        agent_cls = AnspireSearchAgent
    elif root_settings.SEARCH_TOOL_TYPE == "TavilyAPI":
        config_kwargs["TAVILY_API_KEY"] = root_settings.TAVILY_API_KEY
        agent_cls = TavilySearchAgent
    else:
        raise ValueError(f"未知的搜索工具类型: {root_settings.SEARCH_TOOL_TYPE}")

    agent_cls(Settings(**config_kwargs)).research(
        query, save_report=True, argus_context=argus_context
    )
    return _latest_markdown_file(ENGINE_OUTPUT_DIRS["media"])


def _run_query_engine(query: str, *, argus_context: str = "") -> str:
    from config import settings as root_settings
    from QueryEngine import DeepSearchAgent, Settings

    config = Settings(
        QUERY_ENGINE_API_KEY=root_settings.QUERY_ENGINE_API_KEY,
        QUERY_ENGINE_BASE_URL=root_settings.QUERY_ENGINE_BASE_URL,
        QUERY_ENGINE_MODEL_NAME=root_settings.QUERY_ENGINE_MODEL_NAME,
        TAVILY_API_KEY=root_settings.TAVILY_API_KEY,
        MAX_REFLECTIONS=_root_int_setting(
            "ARGUS_SEARCH_ENGINE_MAX_REFLECTIONS", 1
        ),
        MAX_PARAGRAPHS=_root_int_setting("ARGUS_SEARCH_ENGINE_MAX_PARAGRAPHS", 5),
        SEARCH_CONTENT_MAX_LENGTH=20000,
        OUTPUT_DIR=ENGINE_OUTPUT_DIRS["query"],
    )
    DeepSearchAgent(config).research(query, save_report=True, argus_context=argus_context)
    return _latest_markdown_file(ENGINE_OUTPUT_DIRS["query"])


def _root_int_setting(name: str, default: int) -> int:
    try:
        from config import settings as root_settings

        value = int(getattr(root_settings, name, default) or default)
    except Exception:
        value = default
    return max(0, value)


def _call_reset_report_baseline(
    reset_report_baseline: BaselineResetter,
    exclude_files: Mapping[str, List[str]],
) -> None:
    if _resetter_accepts_exclude_files(reset_report_baseline):
        reset_report_baseline(exclude_files=exclude_files)
    else:
        reset_report_baseline()


def _resetter_accepts_exclude_files(resetter: BaselineResetter) -> bool:
    try:
        signature = inspect.signature(resetter)
    except (TypeError, ValueError):
        return False
    return (
        "exclude_files" in signature.parameters
        or any(
            parameter.kind == inspect.Parameter.VAR_KEYWORD
            for parameter in signature.parameters.values()
        )
    )


def _call_start_report_accepts_engine_files(start_report_task: ReportStarter) -> bool:
    try:
        signature = inspect.signature(start_report_task)
    except (TypeError, ValueError):
        return False
    return (
        "engine_files" in signature.parameters
        or any(
            parameter.kind == inspect.Parameter.VAR_KEYWORD
            for parameter in signature.parameters.values()
        )
    )


def _reset_report_baseline(
    exclude_files: Optional[Mapping[str, List[str]]] = None,
) -> None:
    from ReportEngine import flask_interface as report_interface

    if not report_interface.report_agent:
        if not report_interface.initialize_report_engine():
            raise RuntimeError("Report Engine未初始化")
    baseline = report_interface.report_agent.file_baseline
    baseline_counts = baseline.initialize_baseline(ENGINE_OUTPUT_DIRS)

    excluded_counts = _count_existing_excluded_markdown_files(exclude_files or {})
    if not excluded_counts:
        return

    for engine_name, excluded_count in excluded_counts.items():
        current_count = int(baseline_counts.get(engine_name, 0) or 0)
        baseline.baseline_data[engine_name] = max(0, current_count - excluded_count)
    save_baseline = getattr(baseline, "_save_baseline", None)
    if callable(save_baseline):
        save_baseline()


def _count_existing_excluded_markdown_files(
    exclude_files: Mapping[str, List[str]],
) -> Dict[str, int]:
    counts: Dict[str, int] = {}
    for engine_name, files in exclude_files.items():
        if engine_name not in ENGINE_OUTPUT_DIRS:
            continue
        engine_output_dir = Path(ENGINE_OUTPUT_DIRS[engine_name]).resolve()
        unique_paths = {
            Path(file_path).resolve()
            for file_path in files or []
            if str(file_path or "").strip()
        }
        count = sum(
            1
            for path in unique_paths
            if path.exists()
            and path.is_file()
            and path.suffix == ".md"
            and _path_is_relative_to(path, engine_output_dir)
        )
        if count:
            counts[engine_name] = count
    return counts


def _path_is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False


def _queries_match_for_resume(artifact_query: str, current_query: str) -> bool:
    artifact_text = _normalize_resume_query_text(artifact_query)
    current_text = _normalize_resume_query_text(current_query)
    if not artifact_text or not current_text:
        return False
    if artifact_text == current_text:
        return True
    if artifact_text in current_text or current_text in artifact_text:
        return True

    artifact_phrases = _resume_query_phrases(artifact_text)
    if not artifact_phrases:
        return False
    return all(phrase in current_text for phrase in artifact_phrases)


def _normalize_resume_query_text(value: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[《》“”\"'（）()，,。！？!?:：、/\\-]+", " ", str(value or ""))).strip().lower()


def _resume_query_phrases(value: str) -> set[str]:
    return {
        token
        for token in re.split(r"\s+", _normalize_resume_query_text(value))
        if len(token) >= 2
    }


def _default_start_report_task(query: str, **kwargs: Any) -> Mapping[str, Any]:
    from ReportEngine import flask_interface as report_interface

    return report_interface.start_report_task(query=query, auto_export=True, **kwargs)


def _default_forum_synthesis_runner(task: SearchTask) -> Mapping[str, Any]:
    from utils.forum_synthesis import run_forum_synthesis

    return run_forum_synthesis(task)


def _noop_forum_synthesis_runner(_task: SearchTask) -> Mapping[str, Any]:
    return {
        "success": True,
        "skipped": True,
        "message": "ForumEngine synthesis skipped for injected engine runners.",
    }
