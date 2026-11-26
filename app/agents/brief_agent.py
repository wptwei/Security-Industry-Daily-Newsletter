"""安防情报智能体：编排 采集 -> 去重 -> 分类分级 -> 摘要 -> 报告 -> 推送。"""
from __future__ import annotations

import re
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from typing import List

from app.collectors.base import BaseCollector
from app.models.event import SecurityEvent
from app.services.classifier import Classifier
from app.services.dedup import DedupStore
from app.services.pusher import Pusher
from app.services.report import ReportService
from app.services.severity import SeverityRater
from app.services.summarizer import Summarizer
from app.services.tagger import Tagger
from app.services.sector import INDUSTRY_SOURCES, SectorClassifier
from app.services.sensitive import SensitiveFilter
from app.utils.article import fetch_article_text
from app.utils.logging import get_logger

logger = get_logger("brief_agent")


class BriefAgent:
    def __init__(
        self,
        collectors: List[BaseCollector],
        classifier: Classifier,
        rater: SeverityRater,
        dedup: DedupStore,
        summarizer: Summarizer,
        report: ReportService,
        pusher: Pusher,
        tagger: Tagger = None,  # pyright: ignore[reportArgumentType]
        sector_classifier: SectorClassifier = None,  # pyright: ignore[reportArgumentType]
        sensitive_filter: SensitiveFilter = None,  # pyright: ignore[reportArgumentType]
        top_n: int = 15,
        severity_highlight: int = 4,
        time_window_hours: int = 24,
        emergency_quota: int = 0,
        max_per_source: int = 0,
    ) -> None:
        self.collectors = collectors
        self.classifier = classifier
        self.rater = rater
        self.dedup = dedup
        self.summarizer = summarizer
        self.report = report
        self.pusher = pusher
        self.tagger = tagger or Tagger()
        self.sector_classifier = sector_classifier or SectorClassifier()
        self.sensitive_filter = sensitive_filter or SensitiveFilter()
        self.top_n = top_n
        self.severity_highlight = severity_highlight
        self.emergency_quota = emergency_quota
        self.time_window_hours = time_window_hours
        self.max_per_source = max_per_source

    def fetch_events(self) -> List[SecurityEvent]:
        def collect_one(collector: BaseCollector) -> List[SecurityEvent]:
            try:
                batch = collector.collect()
                logger.info("采集器 %s 采集到 %d 条", collector.name, len(batch))
                return batch
            except NotImplementedError as exc:
                logger.warning("采集器 %s 未实现：%s", collector.name, exc)
            except Exception as exc:  # 单个采集器失败不影响整体
                logger.error("采集器 %s 失败：%s", collector.name, exc)
            return []

        events: List[SecurityEvent] = []
        with ThreadPoolExecutor(max_workers=min(8, max(1, len(self.collectors)))) as pool:
            for batch in pool.map(collect_one, self.collectors):
                events.extend(batch)
        return events

    def _filter_recent(self, events: List[SecurityEvent]) -> List[SecurityEvent]:
        """时间窗口过滤：只保留报告生成前 time_window_hours 小时内的新闻。

        无发布日期的事件无法证明仍在时间窗口内，跳过。
        """
        now = datetime.now(timezone.utc)
        cutoff = timedelta(hours=self.time_window_hours)
        kept: List[SecurityEvent] = []
        removed = 0
        for e in events:
            pt = e.published_at
            if pt is None:
                removed += 1
                continue
            # 旧采集器若仍返回 naive 时间，按 UTC 解释。
            if pt.tzinfo is None:
                pt = pt.replace(tzinfo=timezone.utc)
            age = now - pt.astimezone(timezone.utc)
            if age > cutoff or age < -timedelta(hours=6):
                removed += 1
                continue
            kept.append(e)
        if removed:
            logger.info("时间窗口过滤：剔除 %d 条过期、无日期或时间异常的新闻（窗口 %d 小时）",
                        removed, self.time_window_hours)
        return kept

    def run_daily(self) -> List[SecurityEvent]:
        events = self.fetch_events()
        events = self._filter_recent(events)
        events = self.dedup.filter(events)
        for e in events:
            e.category = self.classifier.classify(e)
            e.severity = self.rater.rate(e)
            self.tagger.tag(e)
            e.sector = self.sector_classifier.classify(e)
        # 聚焦物理安防：过滤掉纯网络/合规/公共卫生类
        before = len(events)
        events = [e for e in events if self.classifier.is_physical_security(e)]
        if len(events) < before:
            logger.info("物理安防聚焦：过滤掉 %d 条非物理安防类事件", before - len(events))

        # 同一会议/展会的多篇报道合并（不同媒体改写标题时相似度判定不敏感）
        events = self._dedupe_event_reports(events)

        # 过滤国内政治敏感话题（避免对外汇报出现政治敏感内容）
        events, sensitive_removed = self.sensitive_filter.filter(events)
        if sensitive_removed:
            logger.info("政治敏感过滤：剔除 %d 条涉及国内政治敏感话题的事件", sensitive_removed)

        events = self._select_top(events)

        if not events:
            logger.warning("本次未采集到任何情报，跳过报告与推送")
            return []

        # 入选条目若只有标题，补抓原文正文，让摘要能写出具体事实
        self._enrich_bodies(events)

        events = self.summarizer.summarize_events(events)
        # LLM may reintroduce content rejected by the earlier source filter.
        events, generated_removed = self.sensitive_filter.filter(events)
        if generated_removed:
            logger.warning("生成后内容过滤：剔除 %d 条事件", generated_removed)
        if not events:
            logger.warning("生成后无可上报事件，跳过报告与推送")
            return []
        assess = self.summarizer.assess(events)
        if self.sensitive_filter.is_sensitive(SecurityEvent(title=assess, source="assessment")):
            logger.warning("生成后态势研判未通过内容过滤，使用规则模板")
            assess = self.summarizer._template_assess(events)

        markdown_text = self.report.render_markdown(events, assess)
        paths = self.report.write_files(events, assess, markdown_text=markdown_text)
        # 邮件正文：优先内嵌海报长图（Outlook/QQ 像素一致），失败则退回表格版
        email_html = self.report.render_email_html(events, assess)
        poster_png = self.report.render_poster_image(events, assess)
        # 无论 SMTP 是否可用，都生成 .eml 草稿文件 + 写入 Outlook 草稿箱（可编辑），便于手动发送
        self.pusher.save_eml(markdown_text, email_html, paths["date"], pdf_path=paths.get("pdf"), poster_png=poster_png)
        self.pusher.save_outlook_draft(email_html, paths["date"], pdf_path=paths.get("pdf"), poster_png=poster_png)
        push_results = self.pusher.push(markdown_text, email_html, paths["date"], pdf_path=paths.get("pdf"), poster_png=poster_png)  # pyright: ignore[reportArgumentType]
        # 只有「真正失败」的渠道才保留事件待重试；「未配置/跳过」不算失败
        # （当前流程以 .eml + Outlook 草稿交付，未配置任何群机器人是正常状态）。
        failed = [name for name, status in push_results.items() if status == "失败"]
        if failed:
            logger.warning("推送失败渠道 %s，保留事件供下次重试", "、".join(failed))
        else:
            self.dedup.mark_seen(events)
            self.dedup.save()
        logger.info("今日安防情报任务完成，共生成 %d 条", len(events))
        return events

    # 相似事件主题词 -> 归为一类，每类最多推 2 条
    SIMILARITY_TOPICS = (
        ("earthquake", "地震"), ("quake", "地震"),
        ("gang", "帮派袭击"), ("gunmen", "帮派袭击"), ("militant", "武装袭击"),
        ("attack", "袭击"), ("bombing", "爆炸"), ("bomb", "爆炸"),
        ("fire", "火灾"), ("blaze", "火灾"),
        ("flood", "洪水"), ("typhoon", "台风"), ("hurricane", "飓风"),
        ("landslide", "滑坡"), ("tsunami", "海啸"), ("wildfire", "山火"),
        ("protest", "抗议"), ("riot", "骚乱"), ("coup", "政变"),
        ("kidnap", "绑架"), ("hostage", "人质"), ("abduction", "绑架"),
        ("merger", "并购"), ("acquisition", "并购"), ("acquires", "并购"),
        ("funding", "融资"), ("investment", "投资"),
        ("launch", "发布"), ("unveil", "发布"), ("release", "发布"),
        ("partnership", "合作"), ("collaboration", "合作"),
        ("exhibition", "展会"), ("summit", "峰会"), ("conference", "会议"),
        ("地震", "地震"), ("帮派", "帮派袭击"), ("袭击", "袭击"),
        ("爆炸", "爆炸"), ("火灾", "火灾"), ("洪水", "洪水"),
        ("台风", "台风"), ("飓风", "飓风"), ("滑坡", "滑坡"),
        ("海啸", "海啸"), ("山火", "山火"), ("抗议", "抗议"),
        ("骚乱", "骚乱"), ("政变", "政变"), ("绑架", "绑架"),
        ("人质", "人质"), ("并购", "并购"), ("收购", "并购"),
        ("融资", "融资"), ("投资", "投资"), ("发布", "发布"),
        ("合作", "合作"), ("展会", "展会"), ("峰会", "峰会"),
    )

    @classmethod
    def _similarity_key(cls, e: SecurityEvent) -> str:
        """提取事件相似主题，用于「相似事件最多 2 条」去重。"""
        text = f"{e.title} {e.raw}".lower()
        for kw, topic in cls.SIMILARITY_TOPICS:
            if kw in text:
                return topic
        # 未命中主题词时，用 sector 兜底
        return e.sector

    @staticmethod
    def _editorial_score(e: SecurityEvent) -> int:
        """优先保留垂直媒体和有可核实正文的行业报道。"""
        title = e.original_title.lower()
        source = e.source.lower()
        origin = (e.origin or "").lower()
        has_body = len((e.raw or "").strip()) - len(e.original_title) >= 400
        vertical = any(host in f"{source} {origin}" for host in INDUSTRY_SOURCES)
        score = (5 if vertical else 0) + (3 if has_body else -2)
        # 聚合源本身降权，但若原始媒体已是行业媒体则不再降权
        if "news.google.com" in source and not vertical:
            score -= 3
        if any(term in title for term in (
            "launch", "deploy", "integrat", "install", "upgrade", "partnership",
            "selected as", "screening", "improv",
            "report", "survey", "guide", "standard", "investment", "acqui",
            "发布", "部署", "集成", "安装", "升级", "合作", "报告", "调研", "指南", "标准", "投资",
        )):
            score += 2
        return score

    @staticmethod
    def _is_editorial_noise(e: SecurityEvent) -> bool:
        """排除摄像头偶然拍到的社会杂闻和促销稿。"""
        title = e.original_title.lower()
        if any(term in title for term in (
            "discount", "deal", "sale price", "% off", "black friday",
            "降价", "折扣", "优惠", "促销", "大减价",
        )):
            return True
        return any(term in title for term in (
            "caught on camera", "caught on security camera", "captured on camera",
            "captured by security camera", "seen on cctv", "security camera catches",
            "camera captures", "camera caught", "surveillance footage shows",
            "摄像头拍到", "监控拍到", "监控曝光", "监控画面显示",
        ))

    # 同一场会议/展会通常会被多家媒体分别报道，需合并为一条
    TOPIC_EVENT_TAGS = {
        "峰会", "展会", "会议", "安博会",
        "ISC West展会", "GSX展会", "IFSEC展会", "Intersec展会",
        "Expoprotection展会", "SICUR展会",
    }

    # 品牌名提取时忽略的通用缩写
    _BRAND_STOP = {"ai", "ip", "it", "ceo", "cto", "uk", "us", "eu", "gdpr", "vms", "poe"}

    @classmethod
    def _brand_tokens(cls, title: str) -> set:
        """从标题中提取英文品牌词（大写开头），用于判断是否为同一场会议。"""
        words = re.findall(r"[A-Z][A-Za-z0-9&.\-]{2,}", title or "")
        return {w.lower().strip(".-") for w in words if w.lower() not in cls._BRAND_STOP}

    def _dedupe_event_reports(self, events: List[SecurityEvent]) -> List[SecurityEvent]:
        """同一场会议/展会的多篇报道（不同媒体改写标题），只保留正文最完整的一条。"""
        result: List[SecurityEvent] = []
        buckets: dict = {}
        merged = 0
        for e in events:
            topics = frozenset(set(e.tags.get("event") or []) & self.TOPIC_EVENT_TAGS)
            brands = self._brand_tokens(e.original_title)
            bucket = (e.sector, topics) if topics else None

            target = None
            if bucket is not None:
                for idx, other_brands in buckets.setdefault(bucket, []):
                    if brands & other_brands:
                        target = idx
                        break

            if target is None:
                if bucket is not None:
                    buckets[bucket].append((len(result), brands))
                result.append(e)
                continue

            merged += 1
            if len(e.raw) > len(result[target].raw):
                result[target] = e
                for i, (idx, other) in enumerate(buckets[bucket]):
                    if idx == target:
                        buckets[bucket][i] = (idx, other | brands)
                        break
        if merged:
            logger.info("会议报道合并：%d 条同场会议的重复报道已合并", merged)
        return result

    def _enrich_bodies(self, events: List[SecurityEvent], timeout: int = 12) -> None:
        """为仅有标题的入选条目抓取原文正文（最多 5 个并发）。

        只影响已入选的少量条目，不会拖慢整体采集。
        """
        # 正文不足 400 字即视为「内容单薄」，补抓原文（短摘要同样会导致摘要空泛）
        targets = [
            e for e in events
            if e.url and len((e.raw or "").strip()) - len(e.original_title) < 400
        ]
        if not targets:
            return

        def fetch(event: SecurityEvent):
            return event, fetch_article_text(event.url, timeout=timeout)

        fetched = 0
        with ThreadPoolExecutor(max_workers=min(5, len(targets))) as pool:
            for event, text in pool.map(fetch, targets):
                if text and len(text) > len(event.raw or ""):
                    event.raw = f"{event.original_title} {text}"
                    fetched += 1
        if fetched:
            logger.info("正文补齐：%d 条仅有标题的情报已抓到原文", fetched)

    def _select_top(self, events: List[SecurityEvent]) -> List[SecurityEvent]:
        """精准精选：行业事件优先，突发事件固定限量，总量控制在 top_n。

        行业报道按信源和正文质量排序，突发事件单独限额。
        在完整候选池上应用配额，避免提前截断造成空位无法补齐。
        """
        industry = [e for e in events if e.sector != "emergency" and not self._is_editorial_noise(e)]
        emergency = [e for e in events if e.sector == "emergency"]

        # 有正文的候选足够填满日报时，不用「只有标题」的条目（避免摘要空泛）
        quota = max(0, self.top_n - self.emergency_quota)
        body_rich = [
            e for e in industry
            if len((e.raw or "").strip()) - len(e.original_title) >= 400
        ]
        if len(body_rich) >= quota:
            industry = body_rich

        industry.sort(key=lambda e: (-self._editorial_score(e), -e.severity, e.title))
        emergency.sort(key=lambda e: (-e.severity, e.title))

        # 相似事件去重：同主题最多 2 条（不限制国家）
        # 单来源配额：同一 source 名最多 max_per_source 条（0=不限制）
        result: List[SecurityEvent] = []
        topic_count: dict = {}  # pyright: ignore[reportMissingTypeArgument]
        source_count: dict = {}  # pyright: ignore[reportMissingTypeArgument]
        max_per_source = getattr(self, "max_per_source", 0) or 0

        def _allow(e: SecurityEvent) -> bool:
            topic = self._similarity_key(e) if e.sector == "emergency" else e.uid
            if topic_count.get(topic, 0) >= 2:
                return False
            source_cap = min(max_per_source, 2) if max_per_source and "news.google.com" in e.source else max_per_source
            if "news.google.com" in e.source and not source_cap:
                source_cap = 2
            if source_cap and source_count.get(e.source, 0) >= source_cap:
                return False
            return True

        def _commit(e: SecurityEvent) -> None:
            topic = self._similarity_key(e) if e.sector == "emergency" else e.uid
            topic_count[topic] = topic_count.get(topic, 0) + 1
            source_count[e.source] = source_count.get(e.source, 0) + 1

        for pool, limit in ((industry, max(0, self.top_n - self.emergency_quota)),
                            (emergency, max(0, self.emergency_quota))):
            added = 0
            for e in pool:
                if added >= limit or len(result) >= self.top_n:
                    break
                if not _allow(e):
                    continue
                result.append(e)
                _commit(e)
                added += 1

        result.sort(key=lambda e: (e.sector == "emergency", -self._editorial_score(e), -e.severity, e.title))
        return result
