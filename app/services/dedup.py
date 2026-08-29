"""跨天去重：本地 JSON 记录最近出现的 uid，按窗口过滤。"""
from __future__ import annotations

import json
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Dict, List

from app.models.event import SecurityEvent
from app.utils.logging import get_logger

logger = get_logger("dedup")


class DedupStore:
    """以本地 JSON 记录每个事件最近一次出现日期，按去重窗口过滤。"""

    def __init__(self, path: Path, days: int = 7) -> None:
        self.path = Path(path)
        self.days = days
        self._seen: Dict[str, str] = {}
        self._load()

    def _load(self) -> None:
        if not self.path.exists():
            return
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                self._seen = {k: v for k, v in data.items() if isinstance(v, str)}
        except (json.JSONDecodeError, OSError):
            self._seen = {}

    def is_recent(self, uid: str) -> bool:
        last = self._seen.get(uid)
        if not last:
            return False
        try:
            last_date = datetime.strptime(last, "%Y-%m-%d").date()
        except ValueError:
            return False
        return (date.today() - last_date).days < self.days

    def filter(self, events: List[SecurityEvent]) -> List[SecurityEvent]:
        fresh = [e for e in events if not self.is_recent(e.uid)]
        skipped = len(events) - len(fresh)
        if skipped:
            logger.info("去重：跳过 %d 条近期已出现的事件", skipped)
        return fresh

    def mark_seen(self, events: List[SecurityEvent]) -> None:
        today = date.today().isoformat()
        for event in events:
            self._seen[event.uid] = today
        self._prune()

    def _prune(self) -> None:
        cutoff = (date.today() - timedelta(days=self.days)).isoformat()
        self._seen = {uid: d for uid, d in self._seen.items() if d >= cutoff}

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps(self._seen, ensure_ascii=False, indent=2), encoding="utf-8"
        )
