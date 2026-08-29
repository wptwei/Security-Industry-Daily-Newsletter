"""外交部/领事安全提醒采集器（可选，默认关闭）。

官方页面无稳定公开 API，易受改版影响。默认通过一个可配置的 RSS 地址抓取；
未配置 MFA_FEED 时直接返回空列表（静默跳过）。如需启用，请在 .env 填入
一个提供外交部领事提醒聚合的 RSS 地址。
"""
from __future__ import annotations

from typing import List

from app.collectors.base import BaseCollector
from app.collectors.rss import RSSCollector
from app.models.event import SecurityEvent
from app.utils.logging import get_logger

logger = get_logger("mfa")


class MFACollector(BaseCollector):
    name = "mfa"

    def __init__(self, feed_url: str = "", limit: int = 15, user_agent: str = "") -> None:
        self.feed_url = (feed_url or "").strip()
        self.limit = limit
        self.user_agent = user_agent

    def collect(self) -> List[SecurityEvent]:
        if not self.feed_url:
            logger.info("未配置 MFA_FEED，跳过外交部提醒采集")
            return []
        # 复用通用 RSS 采集器，领域固定为 personnel
        return RSSCollector(
            feed_url=self.feed_url,
            category="personnel",
            limit=self.limit,
            user_agent=self.user_agent,
        ).collect()
