"""安防情报智能体：编排 采集 -> 去重 -> 分类分级 -> 摘要 -> 报告 -> 推送。"""
from __future__ import annotations

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
from app.services.sector import SectorClassifier
from app.services.sensitive import SensitiveFilter
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
        emergency_quota: int = 2,
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
        events: List[SecurityEvent] = []
        for collector in self.collectors:
            try:
                batch = collector.collect()
                logger.info("采集器 %s 采集到 %d 条", collector.name, len(batch))
                events.extend(batch)
            except NotImplementedError as exc:
                logger.warning("采集器 %s 未实现：%s", collector.name, exc)
            except Exception as exc:  # 单个采集器失败不影响整体
                logger.error("采集器 %s 失败：%s", collector.name, exc)
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

        # 过滤国内政治敏感话题（避免对外汇报出现政治敏感内容）
        events, sensitive_removed = self.sensitive_filter.filter(events)
        if sensitive_removed:
            logger.info("政治敏感过滤：剔除 %d 条涉及国内政治敏感话题的事件", sensitive_removed)

        events = self._select_top(events)

        if not events:
            logger.warning("本次未采集到任何情报，跳过报告与推送")
            return []

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
        active_results = [status for status in push_results.values() if not status.startswith("跳过")]
        if active_results and all(status == "成功" for status in active_results):
            self.dedup.mark_seen(events)
            self.dedup.save()
        else:
            logger.warning("推送未全部成功，保留事件供下次重试")
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

    def _select_top(self, events: List[SecurityEvent]) -> List[SecurityEvent]:
        """精准精选：行业事件优先，突发事件固定限量，总量控制在 top_n。

        策略：
        1. 行业事件（非 emergency）按严重度降序优先入选，最多 top_n - emergency_quota 条。
        2. 突发事件（地缘/恐袭/灾害等）固定最多 emergency_quota 条（默认 2），
           不因行业不足而补足，从而压低突发事件占比。
        3. 相似事件去重：同类主题（地震/袭击/火灾/并购等）最多推 2 条，
           不限制国家，只减少同质事件。
        4. 总数最多 top_n，行业不足时总条数会少于 top_n（宁缺毋滥）。
        """
        industry = [e for e in events if e.sector != "emergency"]
        emergency = [e for e in events if e.sector == "emergency"]

        industry.sort(key=lambda e: (-e.severity, e.title))
        emergency.sort(key=lambda e: (-e.severity, e.title))

        selected_industry = industry[: self.top_n - self.emergency_quota]
        selected_emergency = emergency[: self.emergency_quota]

        selected = selected_industry + selected_emergency

        # 相似事件去重：同主题最多 2 条（不限制国家）
        # 单来源配额：同一 source 名最多 max_per_source 条（0=不限制）
        selected.sort(key=lambda e: (-e.severity, e.title))
        result: List[SecurityEvent] = []
        topic_count: dict = {}  # pyright: ignore[reportMissingTypeArgument]
        source_count: dict = {}  # pyright: ignore[reportMissingTypeArgument]
        max_per_source = getattr(self, "max_per_source", 0) or 0

        def _allow(e: SecurityEvent) -> bool:
            topic = self._similarity_key(e)
            if topic_count.get(topic, 0) >= 2:
                return False
            if max_per_source and source_count.get(e.source, 0) >= max_per_source:
                return False
            return True

        def _commit(e: SecurityEvent) -> None:
            topic = self._similarity_key(e)
            topic_count[topic] = topic_count.get(topic, 0) + 1
            source_count[e.source] = source_count.get(e.source, 0) + 1

        for e in selected:
            if not _allow(e):
                continue
            result.append(e)
            _commit(e)
            if len(result) >= self.top_n:
                break

        # 若去重后不足 top_n，用剩余事件补足
        if len(result) < self.top_n:
            used = set(e.uid for e in result)
            for e in selected:
                if e.uid in used:
                    continue
                if not _allow(e):
                    continue
                result.append(e)
                used.add(e.uid)
                _commit(e)
                if len(result) >= self.top_n:
                    break

        # 最终按严重度降序稳定排序
        result.sort(key=lambda e: (-e.severity, e.title))
        return result
