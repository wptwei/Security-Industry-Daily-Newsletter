"""NVD 近期 CVE 采集器（可选，默认关闭；接口限流，建议配 API key）。"""
from __future__ import annotations

from typing import List

import requests

from app.collectors.base import BaseCollector
from app.models.event import SecurityEvent
from app.utils.logging import get_logger

logger = get_logger("nvd")

API_URL = "https://services.nvd.nist.gov/rest/json/cves/2.0"


def _cvss_severity(vuln_item: dict) -> int:
    """从 CVSS v3/v2 基础分粗算严重度。"""
    cve = vuln_item.get("cve") or {}
    metrics = cve.get("metrics") or {}
    score = None
    for key in ("cvssMetricV31", "cvssMetricV30", "cvssMetricV2"):
        for m in metrics.get(key) or []:
            base = (m.get("cvssData") or {}).get("baseScore")
            if base is not None:
                score = float(base)
                break
        if score is not None:
            break
    if score is None:
        return 3
    if score >= 9.0:
        return 4
    if score >= 7.0:
        return 3
    return 2


class NVDCollector(BaseCollector):
    name = "nvd"

    def __init__(self, limit: int = 10, api_key: str = "", user_agent: str = "", timeout: int = 20) -> None:
        self.limit = limit
        self.api_key = api_key
        self.user_agent = user_agent
        self.timeout = timeout

    def collect(self) -> List[SecurityEvent]:
        headers = {"User-Agent": self.user_agent}
        if self.api_key:
            headers["apiKey"] = self.api_key
        resp = requests.get(
            API_URL,
            params={"resultsPerPage": self.limit, "startIndex": 0},
            headers=headers,
            timeout=self.timeout,
        )
        resp.raise_for_status()
        data = resp.json()
        events: List[SecurityEvent] = []
        for item in data.get("vulnerabilities") or []:
            cve = item.get("cve") or {}
            cve_id = cve.get("id") or ""
            if not cve_id:
                continue
            desc = ""
            for d in cve.get("descriptions") or []:
                if d.get("lang") == "en":
                    desc = d.get("value") or ""
                    break
            if not desc and cve.get("descriptions"):
                desc = cve["descriptions"][0].get("value") or ""
            events.append(
                SecurityEvent(
                    title=cve_id,
                    source=self.name,
                    url=f"https://nvd.nist.gov/vuln/detail/{cve_id}",
                    raw=f"{cve_id}: {desc}",
                    category="cyber",
                    severity=_cvss_severity(item),
                    event_id=cve_id,
                )
            )
        return events
