"""In-memory crawl task contract for SaaS data preparation."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from threading import RLock
from typing import Any, Dict, Iterable, Optional
from uuid import uuid4


DEFAULT_PLATFORMS = ("wb",)


@dataclass
class CrawlTask:
    task_id: str
    analysis_query: str
    data_request: str
    platforms: list[str]
    provider: str = "mediacrawler"
    caps: Dict[str, Any] = field(default_factory=dict)
    status: str = "created"
    cloud_job_id: str = ""
    cloud_status_url: str = ""
    error_message: str = ""
    import_result: Dict[str, Any] = field(default_factory=dict)
    readiness: Dict[str, Any] = field(default_factory=dict)
    bundle_metadata: Dict[str, Any] = field(default_factory=dict)
    reportability: Dict[str, Any] = field(default_factory=dict)
    evidence_manifest: Dict[str, Any] = field(default_factory=dict)
    next_action: str = (
        "请运行微博采集任务，导入结果后再检查数据是否足以进入分析。"
    )
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "task_id": self.task_id,
            "analysis_query": self.analysis_query,
            "data_request": self.data_request,
            "platforms": self.platforms,
            "provider": self.provider,
            "caps": self.caps,
            "status": self.status,
            "cloud_job_id": self.cloud_job_id,
            "cloud_status_url": self.cloud_status_url,
            "error_message": self.error_message,
            "import_result": self.import_result,
            "readiness": self.readiness,
            "bundle_metadata": self.bundle_metadata,
            "reportability": self.reportability,
            "evidence_manifest": self.evidence_manifest,
            "next_action": self.next_action,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "status_url": f"/api/crawl/tasks/{self.task_id}",
        }

    def mark_status(self, status: str, next_action: str = "") -> None:
        self.status = status
        if next_action:
            self.next_action = next_action
        self.updated_at = datetime.now()

    def mark_cloud_submitted(self, *, job_id: str = "", status_url: str = "") -> None:
        self.status = "queued"
        self.cloud_job_id = job_id
        self.cloud_status_url = status_url
        self.next_action = (
            "云端微博采集任务已提交。任务完成后导入采集结果，再检查数据是否足以进入分析。"
        )
        self.updated_at = datetime.now()

    def mark_failed(self, message: str) -> None:
        self.status = "failed"
        self.error_message = message
        self.next_action = (
            "微博数据准备失败。请检查采集配置，或收窄研究请求后重试。"
        )
        self.updated_at = datetime.now()

    def mark_imported(
        self,
        import_result: Dict[str, Any],
        readiness: Optional[Dict[str, Any]] = None,
    ) -> None:
        self.status = "imported"
        self.import_result = import_result
        self.readiness = readiness or {}
        self.error_message = ""
        self.next_action = (
            "微博采集结果已导入。开始 Argus 分析前请重新检查数据可用性。"
        )
        self.updated_at = datetime.now()

    def mark_reportable(
        self,
        import_result: Dict[str, Any],
        readiness: Dict[str, Any],
        reportability: Dict[str, Any],
        bundle_metadata: Dict[str, Any],
        evidence_manifest: Optional[Dict[str, Any]] = None,
    ) -> None:
        self.status = "reportable"
        self.import_result = import_result
        self.readiness = readiness
        self.reportability = reportability
        self.bundle_metadata = bundle_metadata
        self.evidence_manifest = evidence_manifest or {}
        self.error_message = ""
        self.next_action = "微博数据已达到报告分析门槛，可以开始 BettaFish 分析。"
        self.updated_at = datetime.now()

    def mark_insufficient(
        self,
        readiness: Optional[Dict[str, Any]],
        reportability: Dict[str, Any],
        bundle_metadata: Dict[str, Any],
        import_result: Optional[Dict[str, Any]] = None,
        evidence_manifest: Optional[Dict[str, Any]] = None,
    ) -> None:
        self.status = "insufficient_data"
        self.import_result = import_result or {}
        self.readiness = readiness or {}
        self.reportability = reportability
        self.bundle_metadata = bundle_metadata
        self.evidence_manifest = evidence_manifest or {}
        self.error_message = ""
        stop_reason = reportability.get("stop_reason") or "insufficient_data"
        self.next_action = (
            f"微博样本不足，暂不能进入正式分析（{stop_reason}）。"
            "请收窄事件、微博线索或时间范围后重试。"
        )
        self.updated_at = datetime.now()


class CrawlTaskStore:
    def __init__(self):
        self._tasks: dict[str, CrawlTask] = {}
        self._lock = RLock()

    def create_task(
        self,
        *,
        analysis_query: str,
        data_request: str = "",
        platforms: Optional[Iterable[str]] = None,
        provider: str = "mediacrawler",
        caps: Optional[Dict[str, Any]] = None,
    ) -> CrawlTask:
        normalized_query = analysis_query.strip()
        normalized_request = data_request.strip() or normalized_query
        task = CrawlTask(
            task_id=f"crawl_{int(datetime.now().timestamp())}_{uuid4().hex[:8]}",
            analysis_query=normalized_query,
            data_request=normalized_request,
            platforms=normalize_platforms(platforms),
            provider=str(provider).strip() or "mediacrawler",
            caps=dict(caps or {}),
        )
        with self._lock:
            self._tasks[task.task_id] = task
        return task

    def get_task(self, task_id: str) -> Optional[CrawlTask]:
        with self._lock:
            return self._tasks.get(task_id)


def normalize_platforms(platforms: Optional[Iterable[str]]) -> list[str]:
    normalized: list[str] = []
    for platform in platforms or DEFAULT_PLATFORMS:
        value = str(platform).strip()
        if not value:
            continue
        if value.lower() == "weibo":
            value = "wb"
        if value not in normalized:
            normalized.append(value)
    return normalized or list(DEFAULT_PLATFORMS)
