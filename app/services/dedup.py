"""跨天去重：本地 JSON 记录最近出现的 key 与标题指纹，按窗口过滤。

除精确 key（源 ID / 规范化 URL / 规范化标题）外，还按「标题相似度」判断同一事件
在不同媒体的改写报道，避免连续几天推送高度重合的内容。
"""
from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, List, Set
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from app.models.event import SecurityEvent
from app.utils.logging import get_logger

logger = get_logger("dedup")

# 去重日期统一用北京时间（UTC+8），与机器/云端时区无关
BEIJING_TZ = timezone(timedelta(hours=8))

# 标题相似度阈值（Jaccard）：越高越严格，0.78 可识别「同一事件的不同说法」
DEFAULT_SIMILARITY = 0.78
# 标题 token 太少时不做相似度判定，避免误杀
_MIN_TOKENS = 6


def _today() -> date:
    return datetime.now(BEIJING_TZ).date()


def _title_tokens(title: str) -> Set[str]:
    """标题切词：英文按单词、中文按二元组，用于相似度比较。"""
    text = unicodedata.normalize("NFKC", title or "").casefold()
    tokens: Set[str] = set(re.findall(r"[a-z0-9]{2,}", text))
    for run in re.findall(r"[㐀-鿿]+", text):
        if len(run) == 1:
            tokens.add(run)
        else:
            tokens.update(run[i:i + 2] for i in range(len(run) - 1))
    return tokens


def _similarity(a: Set[str], b: Set[str]) -> float:
    if not a or not b:
        return 0.0
    overlap = len(a & b)
    if not overlap:
        return 0.0
    return overlap / len(a | b)


class DedupStore:
    """以本地 JSON 记录每个事件最近一次出现日期，按去重窗口过滤。"""

    def __init__(self, path: Path, days: int = 7, similarity: float = DEFAULT_SIMILARITY) -> None:
        self.path = Path(path)
        self.days = days
        self.similarity = similarity
        self._seen: Dict[str, str] = {}
        # 标题指纹 -> {"tokens": [...], "date": "YYYY-MM-DD"}
        self._titles: Dict[str, dict] = {}
        self._load()

    def _load(self) -> None:
        if not self.path.exists():
            return
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return
        if not isinstance(data, dict):
            return
        keys = data.get("keys")
        if isinstance(keys, dict):
            # 新格式：{"keys": {...}, "titles": {...}}
            self._seen = {k: v for k, v in keys.items() if isinstance(v, str)}
            raw_titles = data.get("titles")
            if isinstance(raw_titles, dict):
                for fp, rec in raw_titles.items():
                    if not isinstance(rec, dict):
                        continue
                    when = rec.get("date")
                    tokens = rec.get("tokens")
                    if isinstance(when, str) and isinstance(tokens, list):
                        self._titles[fp] = {
                            "tokens": [t for t in tokens if isinstance(t, str)],
                            "date": when,
                        }
        else:
            # 兼容旧的扁平格式：{key: date}
            self._seen = {k: v for k, v in data.items() if isinstance(v, str)}

    def _date_in_window(self, text: str) -> bool:
        try:
            last_date = datetime.strptime(text, "%Y-%m-%d").date()
        except ValueError:
            return False
        return (_today() - last_date).days < self.days

    def is_recent(self, uid: str) -> bool:
        last = self._seen.get(uid)
        if not last:
            return False
        return self._date_in_window(last)

    @staticmethod
    def _keys(event: SecurityEvent) -> Set[str]:
        """Combine source ID with normalized article URL and sufficiently specific title."""
        keys = {event.uid}
        if event.url:
            try:
                parsed = urlsplit(event.url)
            except ValueError:
                parsed = None
            if parsed is not None and parsed.scheme.lower() in ("http", "https") and parsed.hostname:
                query = urlencode(sorted(
                    (k, v) for k, v in parse_qsl(parsed.query, keep_blank_values=True)
                    if not k.lower().startswith("utm_") and k.lower() not in ("fbclid", "gclid")
                ))
                canonical = urlunsplit(("https", parsed.netloc.lower(), parsed.path.rstrip("/") or "/", query, ""))
                keys.add("url:" + hashlib.sha256(canonical.encode("utf-8")).hexdigest())
        title = unicodedata.normalize("NFKC", event.original_title).casefold()
        has_cjk = bool(re.search(r"[㐀-鿿]", title))
        title = re.sub(r"[^\w]+", "", title)
        if len(title) >= (12 if has_cjk else 30):
            keys.add("title:" + hashlib.sha256(title.encode("utf-8")).hexdigest())
        return keys

    @staticmethod
    def _title_fingerprint(event: SecurityEvent) -> str:
        norm = unicodedata.normalize("NFKC", event.original_title or "").casefold()
        norm = re.sub(r"[^\w]+", "", norm)
        if not norm:
            return ""
        return hashlib.sha256(norm.encode("utf-8")).hexdigest()

    def _similar_in_window(self, tokens: Set[str]) -> bool:
        if len(tokens) < _MIN_TOKENS:
            return False
        for rec in self._titles.values():
            if not self._date_in_window(rec["date"]):
                continue
            other = set(rec["tokens"])
            if len(other) < _MIN_TOKENS:
                continue
            if _similarity(tokens, other) >= self.similarity:
                return True
        return False

    def filter(self, events: List[SecurityEvent]) -> List[SecurityEvent]:
        fresh: List[SecurityEvent] = []
        batch_keys: Dict[str, int] = {}
        batch_tokens: List[Set[str]] = []
        skipped_recent = 0
        skipped_similar = 0

        for event in events:
            keys = self._keys(event)
            if any(self.is_recent(key) for key in keys):
                skipped_recent += 1
                continue

            tokens = _title_tokens(event.original_title)
            # 与窗口内已推送内容的标题高度相似 -> 视为同一事件
            if self._similar_in_window(tokens):
                skipped_similar += 1
                continue

            # 与本批已接受条目的重复（同一事件多源）：保留正文更完整的一条
            match = next((batch_keys[key] for key in keys if key in batch_keys), None)
            if match is None:
                match = next(
                    (
                        i for i, other in enumerate(batch_tokens)
                        if min(len(tokens), len(other)) >= _MIN_TOKENS
                        and _similarity(tokens, other) >= self.similarity
                    ),
                    None,
                )
            if match is not None:
                if len(event.raw) > len(fresh[match].raw):
                    previous = fresh[match]
                    fresh[match] = event
                    batch_tokens[match] = tokens
                    for key in self._keys(previous) | keys:
                        batch_keys[key] = match
                else:
                    for key in keys:
                        batch_keys[key] = match
                continue

            position = len(fresh)
            fresh.append(event)
            batch_tokens.append(tokens)
            for key in keys:
                batch_keys[key] = position

        if skipped_recent:
            logger.info("去重：跳过 %d 条近期已出现的事件", skipped_recent)
        if skipped_similar:
            logger.info("去重：跳过 %d 条与近期内容高度相似的报道", skipped_similar)
        return fresh

    def mark_seen(self, events: List[SecurityEvent]) -> None:
        today = _today().isoformat()
        for event in events:
            for key in self._keys(event):
                self._seen[key] = today
            tokens = _title_tokens(event.original_title)
            fingerprint = self._title_fingerprint(event)
            if fingerprint and len(tokens) >= _MIN_TOKENS:
                self._titles[fingerprint] = {"tokens": sorted(tokens), "date": today}
        self._prune()

    def _prune(self) -> None:
        self._seen = {k: v for k, v in self._seen.items() if self._date_in_window(v)}
        self._titles = {k: v for k, v in self._titles.items() if self._date_in_window(v["date"])}

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"keys": self._seen, "titles": self._titles}
        self.path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )
