"""MediaCrawler-backed Weibo data prep provider."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from .base import WeiboCollectionBundle, WeiboDataCaps


@dataclass(frozen=True)
class MediaCrawlerWeiboProvider:
    name: str = "mediacrawler"

    def collect(
        self,
        request: Mapping[str, Any],
        caps: WeiboDataCaps,
    ) -> WeiboCollectionBundle:
        from utils.weibo_data_prep import build_weibo_collection_bundle

        return build_weibo_collection_bundle(self.name, request, caps)
