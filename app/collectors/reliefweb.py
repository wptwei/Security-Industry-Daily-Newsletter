"""ReliefWeb 采集器：灾害/人道主义报告。"""
from __future__ import annotations

from datetime import datetime
from typing import List

import requests

from app.collectors.base import BaseCollector
from app.models.event import SecurityEvent
from app.utils.logging import get_logger

logger = get_logger("reliefweb")

API_URL = "https://api.reliefweb.int/v2/reports"


class ReliefWebCollector(BaseCollector):
    name = "reliefweb"

    def __init__(self, appname: str = "security-intel-agent", limit: int = 20, timeout: int = 20) -> None:
        self.appname = appname
        self.limit = limit
        self.timeout = timeout

    def collect(self) -> List[SecurityEvent]:
        params = [
            ("appname", self.appname),
            ("limit", str(self.limit)),
            ("sort[]", "date:desc"),
            ("query[value]", "disaster OR epidemic OR conflict OR flood OR earthquake"),
            ("fields[include][]", "title"),
            ("fields[include][]", "url"),
            ("fields[include][]", "country"),
            ("fields[include][]", "primary_country"),
            ("fields[include][]", "date"),
        ]
        resp = requests.get(API_URL, params=params, timeout=self.timeout)
        if resp.status_code == 403:
            logger.warning(
                "ReliefWeb 返回 403：需到 reliefweb.int 注册一个已批准的 appname，"
                "填入 RELIEFWEB_APPNAME 后重试（当前 appname 未获批）"
            )
            return []
        resp.raise_for_status()
        data = resp.json()
        events: List[SecurityEvent] = []
        for item in data.get("data") or []:
            fields = item.get("fields") or {}
            title = (fields.get("title") or "").strip()
            if not title:
                continue
            countries = [c.get("name", "") for c in fields.get("country") or [] if c.get("name")]
            date_obj = fields.get("date") or {}
            date_raw = date_obj.get("original") or date_obj.get("created") or ""
            events.append(
                SecurityEvent(
                    title=title,
                    source=self.name,
                    url=fields.get("url") or "",
                    country=", ".join(countries[:3]),
                    raw=title,
                    event_id=str(item.get("id") or ""),
                    published_at=self._parse_date(date_raw),
                )
            )
        return events

    @staticmethod
    def _parse_date(raw: str):
        if not raw:
            return None
        for fmt in ("%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d"):
            try:
                return datetime.strptime(raw, fmt)
            except ValueError:
                continue
        return None
