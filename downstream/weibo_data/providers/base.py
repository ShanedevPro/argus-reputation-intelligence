"""Shared contracts for Weibo data prep providers."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Protocol


@dataclass(frozen=True)
class WeiboDataCaps:
    max_keywords: int = 6
    max_posts_per_keyword: int = 30
    max_selected_posts: int = 12
    max_comments_per_post: int = 20
    max_comments_per_post_hard: int = 30
    allow_subcomments: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "max_keywords": self.max_keywords,
            "max_posts_per_keyword": self.max_posts_per_keyword,
            "max_selected_posts": self.max_selected_posts,
            "max_comments_per_post": self.max_comments_per_post,
            "max_comments_per_post_hard": self.max_comments_per_post_hard,
            "allow_subcomments": self.allow_subcomments,
        }


@dataclass(frozen=True)
class WeiboCollectionBundle:
    provider: str
    keywords: list[str] = field(default_factory=list)
    posts: list[dict[str, Any]] = field(default_factory=list)
    comments: list[dict[str, Any]] = field(default_factory=list)
    stop_reason: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "provider": self.provider,
            "keywords": self.keywords,
            "posts": self.posts,
            "comments": self.comments,
            "stop_reason": self.stop_reason,
            "metadata": self.metadata,
        }


@dataclass(frozen=True)
class WeiboDataTask:
    provider: str
    platform: str = "weibo"
    keywords: list[str] = field(default_factory=list)
    search: dict[str, Any] = field(default_factory=dict)
    comments: dict[str, Any] = field(default_factory=dict)
    caps: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "provider": self.provider,
            "platform": self.platform,
            "keywords": self.keywords,
            "search": self.search,
            "comments": self.comments,
            "caps": self.caps,
            "metadata": self.metadata,
        }


@dataclass(frozen=True)
class WeiboReportabilityResult:
    status: str
    can_start_analysis: bool
    stop_reason: str
    counts: dict[str, int] = field(default_factory=dict)
    reasons: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "can_start_analysis": self.can_start_analysis,
            "stop_reason": self.stop_reason,
            "counts": self.counts,
            "reasons": self.reasons,
            "metadata": self.metadata,
        }


class WeiboDataProvider(Protocol):
    name: str

    def collect(
        self,
        request: Mapping[str, Any],
        caps: WeiboDataCaps,
    ) -> WeiboCollectionBundle:
        """Collect Weibo posts and comments for a prepared event request."""
