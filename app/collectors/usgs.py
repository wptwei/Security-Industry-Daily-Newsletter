"""USGS 地震采集器。"""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from typing import List

import requests

from app.collectors.base import BaseCollector
from app.models.event import SecurityEvent
from app.utils.logging import get_logger

logger = get_logger("usgs")

API_URL = "https://earthquake.usgs.gov/fdsnws/event/1/query"


def _mag_to_severity(mag: float) -> int:
    if mag >= 7.0:
        return 5
    if mag >= 6.0:
        return 4
    if mag >= 5.0:
        return 3
    return 2


class USGSCollector(BaseCollector):
    name = "usgs"

    def __init__(self, min_mag: float = 4.5, limit: int = 20, timeout: int = 20,
                 max_per_country: int = 1) -> None:
        self.min_mag = min_mag
        self.limit = limit
        self.timeout = timeout
        # 同国家/地区最多保留几条地震，避免一次推送一堆同区域小震
        self.max_per_country = max_per_country

    def collect(self) -> List[SecurityEvent]:
        resp = requests.get(
            API_URL,
            params={
                "format": "geojson",
                "minmagnitude": self.min_mag,
                "orderby": "time",
                "limit": self.limit,
            },
            timeout=self.timeout,
        )
        resp.raise_for_status()
        data = resp.json()
        events: List[SecurityEvent] = []
        for feature in data.get("features") or []:
            props = feature.get("properties") or {}
            mag = props.get("mag")
            place = (props.get("place") or "").strip()
            title = f"M{mag} 地震 {place}"
            t = props.get("time")
            published = None
            if t:
                published = datetime.fromtimestamp(t / 1000, tz=timezone.utc)
            events.append(
                SecurityEvent(
                    title=title,
                    source=self.name,
                    url=props.get("url") or "",
                    country=place.split(",")[-1].strip() if place else "",
                    raw=f"Magnitude {mag} earthquake at {place}",
                    category="disaster",
                    severity=_mag_to_severity(float(mag or 0)),
                    event_id=str(feature.get("id") or ""),
                    published_at=published,
                )
            )
        # 按 country 分组，每组只保留严重度最高的 max_per_country 条
        by_country: dict = defaultdict(list)
        for e in events:
            key = e.country or "未知地区"
            by_country[key].append(e)
        for key in by_country:
            by_country[key].sort(key=lambda e: (-e.severity, e.title))
        deduped: List[SecurityEvent] = []
        for key, items in by_country.items():
            deduped.extend(items[: self.max_per_country])
        if len(deduped) < len(events):
            logger.info("USGS 源头降采样：%d 条 → %d 条（每国家最多 %d 条）",
                        len(events), len(deduped), self.max_per_country)
        return deduped
