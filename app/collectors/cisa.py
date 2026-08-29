"""CISA 已知被利用漏洞（KEV）采集器。"""
from __future__ import annotations

from datetime import datetime
from typing import List

import requests

from app.collectors.base import BaseCollector
from app.models.event import SecurityEvent
from app.utils.logging import get_logger

logger = get_logger("cisa")

KEV_URL = "https://www.cisa.gov/sites/default/files/feeds/known_exploited_vulnerabilities.json"


class CISACollector(BaseCollector):
    name = "cisa"

    def __init__(self, limit: int = 10, timeout: int = 20) -> None:
        self.limit = limit
        self.timeout = timeout

    def collect(self) -> List[SecurityEvent]:
        resp = requests.get(KEV_URL, timeout=self.timeout)
        resp.raise_for_status()
        data = resp.json()
        vulns = sorted(
            data.get("vulnerabilities") or [],
            key=lambda v: v.get("dateAdded", ""),
            reverse=True,
        )
        events: List[SecurityEvent] = []
        for v in vulns[: self.limit]:
            cve = v.get("cveID") or ""
            name = v.get("vulnerabilityName") or ""
            product = v.get("product") or ""
            title = f"{cve} {name}（{product}）"
            events.append(
                SecurityEvent(
                    title=title,
                    source=self.name,
                    url=f"https://nvd.nist.gov/vuln/detail/{cve}" if cve else "",
                    raw=f"{title}. {v.get('shortDescription') or ''}",
                    category="cyber",
                    severity=4,  # 已知在野利用 = 高
                    event_id=cve,
                    published_at=self._parse_date(v.get("dateAdded")),
                )
            )
        return events

    @staticmethod
    def _parse_date(raw: str):
        if not raw:
            return None
        try:
            return datetime.strptime(raw, "%Y-%m-%d")
        except ValueError:
            return None
