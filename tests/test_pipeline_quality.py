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


def test_html_date_has_china_timezone():
    date = _extract_date("发布时间：2026-11-16 09:30", "https://example.test/a")
    assert date.utcoffset() == timedelta(hours=8)
    assert date.astimezone(BEIJING_TZ).hour == 9
    assert _extract_date("no date", "https://example.test/news/202611/a") is None


def test_report_includes_safe_source_link(tmp_path):
    report = ReportService(tmp_path)
    event = SecurityEvent(
        title="Security camera update", source="rss:test",
        url="https://example.test/article?utm_source=feed",
    )
    item = report._markdown_item(event)
    assert "查看原文" in item
    assert "https://example.test/article" in item
    event.url = "javascript:alert(1)"
    assert "查看原文" not in report._markdown_item(event)


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
