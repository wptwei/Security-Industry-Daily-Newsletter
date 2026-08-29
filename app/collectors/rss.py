"""通用 RSS 采集器：feedparser 解析任意 RSS/Atom 信源。"""
from __future__ import annotations

import re
from datetime import datetime
from typing import List
from urllib.parse import urlparse

import feedparser
import requests

from app.collectors.base import BaseCollector
from app.models.event import SecurityEvent
from app.utils.logging import get_logger

logger = get_logger("rss")


def _strip_html(raw: str) -> str:
    """去掉 HTML 标签，压缩空白，得到纯文本。"""
    if not raw:
        return ""
    text = re.sub(r"<[^>]+>", " ", raw)
    text = re.sub(r"&nbsp;|&#160;", " ", text)
    text = re.sub(r"&amp;", "&", text)
    text = re.sub(r"&lt;", "<", text)
    text = re.sub(r"&gt;", ">", text)
    text = re.sub(r"&quot;", '"', text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


class RSSCollector(BaseCollector):
    """按 `URL|领域` 配置实例化，一份 feed 一个采集器。"""

    def __init__(self, feed_url: str, category: str = "geopolitical", limit: int = 15,
                 user_agent: str = "", timeout: int = 20) -> None:
        self.feed_url = feed_url
        self.category = category
        self.limit = limit
        self.user_agent = user_agent
        self.timeout = timeout
        host = urlparse(feed_url).netloc.replace("www.", "") or "feed"
        self.name = f"rss:{host}"

    def collect(self) -> List[SecurityEvent]:
        headers = {"User-Agent": self.user_agent} if self.user_agent else {}
        try:
            resp = requests.get(self.feed_url, timeout=self.timeout, headers=headers)
            resp.raise_for_status()
            content = resp.content
        except Exception as exc:
            logger.warning("RSS 抓取失败 %s：%s", self.feed_url, exc)
            return []
        feed = feedparser.parse(content)
        if feed.get("bozo") and not feed.entries:
            logger.warning("RSS 解析异常 %s：%s", self.feed_url, feed.get("bozo_exception"))
        events: List[SecurityEvent] = []
        for entry in feed.entries[: self.limit]:
            title = (entry.get("title") or "").strip()
            link = entry.get("link") or ""
            if not title:
                continue
            # 优先取完整正文 content，其次 summary，再去 HTML 得到纯文本
            summary = entry.get("summary") or ""
            content_full = ""
            content_list = entry.get("content") or []
            if content_list:
                content_full = content_list[0].get("value") or ""
            raw_body = _strip_html(content_full) or _strip_html(summary)
            published = None
            for key in ("published_parsed", "updated_parsed"):
                parsed = entry.get(key)
                if parsed:
                    try:
                        published = datetime(*parsed[:6])
                    except (TypeError, ValueError):
                        published = None
                    break
            events.append(
                SecurityEvent(
                    title=title,
                    source=self.name,
                    url=link,
                    category=self.category,
                    raw=f"{title}. {raw_body}" if raw_body else title,
                    event_id=link or title,
                    published_at=published,
                )
            )
        return events
