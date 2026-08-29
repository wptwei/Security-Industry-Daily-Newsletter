"""GDELT 2.0 DOC API 采集器：全球新闻事件（地缘/冲突/骚乱/灾害）。"""
from __future__ import annotations

import time
from datetime import datetime
from typing import List

import requests

from app.collectors.base import BaseCollector
from app.models.event import SecurityEvent
from app.utils.logging import get_logger

logger = get_logger("gdelt")

API_URL = "https://api.gdeltproject.org/api/v2/doc/doc"


def _parse_seendate(raw: str):
    """GDELT seendate 形如 '20260825T120000Z'。"""
    if not raw:
        return None
    try:
        return datetime.strptime(raw, "%Y%m%dT%H%M%SZ")
    except ValueError:
        return None


class GDELTCollector(BaseCollector):
    name = "gdelt"

    def __init__(self, query: str, timespan: str = "1d", limit: int = 30, timeout: int = 20) -> None:
        self.query = query
        self.timespan = timespan
        self.limit = limit
        self.timeout = timeout

    def collect(self) -> List[SecurityEvent]:
        last_exc: Exception = None  # type: ignore[assignment]
        for attempt in (1, 2):
            try:
                resp = requests.get(
                    API_URL,
                    params={
                        "query": self.query,
                        "mode": "artlist",
                        "maxrecords": self.limit,
                        "timespan": self.timespan,
                        "format": "json",
                        "sort": "hybridrel",
                    },
                    timeout=self.timeout,
                )
                resp.raise_for_status()
                data = resp.json()
                events: List[SecurityEvent] = []
                for article in data.get("articles") or []:
                    title = (article.get("title") or "").strip()
                    if not title:
                        continue
                    url = article.get("url") or ""
                    events.append(
                        SecurityEvent(
                            title=title,
                            source=self.name,
                            url=url,
                            country=(article.get("sourcecountry") or "").strip(),
                            raw=title,
                            event_id=url or title,
                            published_at=_parse_seendate(article.get("seendate")),
                        )
                    )
                return events
            except Exception as exc:
                last_exc = exc
                logger.warning("GDELT 第 %d 次请求失败：%s", attempt, exc)
                if attempt == 1:
                    time.sleep(2)
        raise last_exc
