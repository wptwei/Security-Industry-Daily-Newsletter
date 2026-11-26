"""Checks for grounded summaries, freshness, provenance and article deduplication."""

from datetime import timedelta
from unittest.mock import Mock, patch

from app.collectors.html import BEIJING_TZ, _extract_date
from app.collectors.reliefweb import ReliefWebCollector
from app.models.event import SecurityEvent
from app.services.dedup import DedupStore
from app.services.report import ReportService
from app.services.summarizer import Summarizer
from app.agents.brief_agent import BriefAgent


def _summarizer_with_reply(reply):
    summarizer = Summarizer(False, "", "", "")
    summarizer.enabled = True
    summarizer._chat = lambda system, user: reply
    return summarizer


def test_misaligned_llm_numbers_never_reassign_summaries():
    events = [SecurityEvent(title=f"Story {i}", source="rss:test") for i in range(3)]
    reply = "0. A｜first\n2. B｜second\n3. C｜third"
    _summarizer_with_reply(reply).summarize_events(events)
    assert [e.title for e in events] == ["Story 0", "Story 1", "Story 2"]
    assert all("详情待核实" in e.summary for e in events)


def test_title_only_summary_does_not_use_unsupported_llm_details():
    event = SecurityEvent(title="New security camera announced", source="rss:test")
    reply = "0. 发布新安防摄像头｜该产品覆盖全球市场并实现重大收入增长"
    _summarizer_with_reply(reply).summarize_events([event])
    assert event.title == "发布新安防摄像头"
    assert "重大收入增长" not in event.summary
    assert "详情待核实" in event.summary
    assert event.original_title == "New security camera announced"


def test_duplicate_sources_keep_more_complete_article(tmp_path):
    short = SecurityEvent(
        title="Hikvision launches a new security camera for commercial sites",
        source="rss:one", url="https://example.test/article?utm_source=feed", raw="short",
    )
    full = SecurityEvent(
        title=short.title, source="rss:two", url="https://example.test/article",
        raw="Longer article body with concrete product details.",
    )
    store = DedupStore(tmp_path / "history.json")
    assert store.filter([short, full]) == [full]
    store.mark_seen([full])
    assert store.filter([short]) == []


def test_similar_titles_are_deduplicated_across_days(tmp_path):
    """同一事件的不同媒体改写标题，跨天也应判为重复，降低重合度。"""
    store = DedupStore(tmp_path / "history.json")
    first = SecurityEvent(
        title="Hikvision launches new AI surveillance camera for commercial sites",
        source="rss:a", url="https://a.example/1",
    )
    store.mark_seen([first])
    store.save()

    again = DedupStore(tmp_path / "history.json")
    rewritten = SecurityEvent(
        title="Hikvision launches a new AI surveillance camera for commercial sites",
        source="rss:b", url="https://b.example/2",
    )
    unrelated = SecurityEvent(
        title="Dahua unveils perimeter radar for data center security",
        source="rss:c", url="https://c.example/3",
    )
    kept = again.filter([rewritten, unrelated])
    assert [e.title for e in kept] == [unrelated.title]


def test_same_conference_reports_are_merged():
    """同一场会议的多篇报道（标题不同）应合并为一条，保留正文更完整的。"""
    agent = BriefAgent.__new__(BriefAgent)
    short = SecurityEvent(title="Milestone年度开发者峰会汇聚合作伙伴", source="rss:a", raw="短" * 80)
    full = SecurityEvent(title="Milestone峰会探讨AI辅助视频操作员", source="rss:b", raw="长" * 200)
    other = SecurityEvent(title="Hikvision峰会展示新品", source="rss:c", raw="中" * 120)
    for e in (short, full, other):
        e.sector = "summit"
        e.tags = {"region": [], "company": [], "product": [], "event": ["峰会"]}
    merged = agent._dedupe_event_reports([short, full, other])
    assert [e.title for e in merged] == [full.title, other.title]


def test_article_body_extraction():
    """入选条目补抓正文：能取到正文段落、丢弃导航噪音。"""
    from app.utils.article import _extract_main_text

    markup = (
        "<html><body><nav>首页 产品 联系</nav>"
        "<article><p>" + "这是一段足够长的正文内容，用于验证提取逻辑是否有效。" * 3 + "</p></article>"
        "<footer>版权信息</footer></body></html>"
    )
    text = _extract_main_text(markup, 1000)
    assert "这是一段足够长的正文内容" in text
    assert "首页" not in text


def test_article_fetch_skips_google_news_links():
    """Google 新闻跳转链接无法直取正文，应直接跳过（不发请求）。"""
    from app.utils.article import fetch_article_text

    assert fetch_article_text("https://news.google.com/rss/articles/abc") == ""


def test_assessment_drops_credibility_disclaimers():
    """研判里不应出现「可信度低」这类空泛评价。"""
    from app.services.summarizer import _strip_credibility_notes

    text = "今日共 8 条情报，安防峰会方向活跃。部分来源可信度较低，仅供参考。物理安防方向以新品发布为主。"
    cleaned = _strip_credibility_notes(text)
    assert "可信度" not in cleaned
    assert "安防峰会" in cleaned and "物理安防" in cleaned


def test_disasters_are_excluded_from_report():
    """地震等自然灾害不再收录。"""
    from app.services.classifier import Classifier

    classifier = Classifier()
    quake = SecurityEvent(
        title="Magnitude 6.2 earthquake strikes region", source="rss:test", category="disaster"
    )
    assert classifier.is_physical_security(quake) is False


def test_report_footer_uses_department_brand(tmp_path):
    report = ReportService(tmp_path)
    event = SecurityEvent(title="Access control product launch", source="rss:sdmmag.com", summary="详情")
    markdown = report.render_markdown([event], "研判")
    assert "华东安保二部" in markdown
    assert "数据来源" not in markdown
    assert "AI 摘要引擎" not in markdown
    # 来源显示媒体名而非内部采集器标识
    assert "SDM Magazine" in markdown
    assert "rss:sdmmag.com" not in markdown


def test_html_date_has_china_timezone():
    date = _extract_date("发布时间：2026-11-16 09:30", "https://example.test/a")
    assert date.utcoffset() == timedelta(hours=8)
    assert date.astimezone(BEIJING_TZ).hour == 9
    assert _extract_date("no date", "https://example.test/news/202611/a") is None


def test_report_does_not_expose_source_links(tmp_path):
    """安全要求：日报正文不显示原文链接，也不暴露来源域名。"""
    report = ReportService(tmp_path)
    event = SecurityEvent(
        title="Security camera update", source="rss:test",
        url="https://example.test/article?utm_source=feed",
    )
    item = report._markdown_item(event)
    assert "查看原文" not in item
    assert "https://example.test/article" not in item
    poster = report._poster_item_html(event)
    assert "原文" not in poster
    assert "https://example.test/article" not in poster


def test_reliefweb_body_is_used_for_summary_input():
    response = Mock()
    response.json.return_value = {"data": [{
        "id": 123,
        "fields": {
            "title": "Flood update",
            "body": "<p>Water levels rose in the city.</p>",
            "date": {"created": "2026-11-16T09:00:00+00:00"},
        },
    }]}
    with patch("app.collectors.reliefweb.requests.get", return_value=response) as get:
        events = ReliefWebCollector().collect()
    assert "Water levels rose in the city." in events[0].raw
    assert ("fields[include][]", "body") in get.call_args.kwargs["params"]


def test_editorial_selection_prefers_grounded_vertical_news_and_refills():
    agent = BriefAgent.__new__(BriefAgent)
    agent.top_n = 3
    agent.emergency_quota = 0
    agent.max_per_source = 2
    events = [
        SecurityEvent(title="Security camera catches apes playing", source="rss:news.google.com", severity=5),
        SecurityEvent(title="Camera deal: 60% off", source="rss:news.google.com", severity=5),
        SecurityEvent(title="Camera captures a road accident", source="rss:news.google.com", severity=5),
    ]
    for i in range(4):
        events.append(SecurityEvent(
            title=f"Company {i} launches access control system", source=f"rss:securitysales{i}.com",
            raw=f"Company {i} launches access control system. " + "Deployment details and product specifications. " * 5,
            severity=2, url=f"https://securitysales{i}.com/{i}",
        ))
    chosen = agent._select_top(events)
    assert len(chosen) == 3
    assert all("Company" in e.title for e in chosen)


def test_google_aggregator_is_limited_even_without_global_source_cap():
    agent = BriefAgent.__new__(BriefAgent)
    agent.top_n = 5
    agent.emergency_quota = 0
    agent.max_per_source = 0
    events = [SecurityEvent(title=f"Security system launch {i}", source="rss:news.google.com",
                            url=f"https://news.google.com/{i}") for i in range(5)]
    assert len(agent._select_top(events)) == 2


def test_pdf_html_uses_a4_pages_while_poster_keeps_long_canvas(tmp_path):
    report = ReportService(tmp_path)
    event = SecurityEvent(title="Access control launch", source="rss:securitysales.com")
    pdf_html = report.render_poster_html([event], "今日研判", paginated=True)
    poster_html = report.render_poster_html([event], "今日研判")
    assert "@page{size:A4;margin:12mm}" in pdf_html
    assert "id = '__page_size'" not in pdf_html
    assert "id = '__page_size'" in poster_html


def test_concurrent_collectors_keep_order_and_isolate_failures():
    class Collector:
        def __init__(self, name, fails=False):
            self.name = name
            self.fails = fails

        def collect(self):
            if self.fails:
                raise RuntimeError("source unavailable")
            return [SecurityEvent(title=self.name, source=self.name)]

    agent = BriefAgent.__new__(BriefAgent)
    agent.collectors = [Collector("first"), Collector("broken", True), Collector("last")]
    assert [e.title for e in agent.fetch_events()] == ["first", "last"]
