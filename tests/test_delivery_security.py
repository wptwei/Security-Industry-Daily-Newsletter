"""Security checks for delivery and generated report content."""

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, Mock, patch

from app.agents.brief_agent import BriefAgent
from app.models.event import SecurityEvent
from app.services.classifier import Classifier
from app.services.pusher import Pusher
from app.services.sector import SectorClassifier
from app.services.sensitive import SensitiveFilter
from app.services.severity import SeverityRater
from app.services.tagger import Tagger


def test_webhook_business_error_is_failure():
    response = Mock()
    response.json.return_value = {"errcode": 40001, "errmsg": "invalid token"}
    with patch("app.services.pusher.requests.post", return_value=response):
        assert Pusher(None)._post_json("https://example.test/hook?token=fake", {}) is False


def test_webhook_exception_does_not_log_token():
    secret = "FAKE_TEST_SECRET"
    with patch("app.services.pusher.requests.post", side_effect=RuntimeError(secret)):
        with patch("app.services.pusher.logger.error") as log:
            assert Pusher(None)._post_json(f"https://example.test/hook?token={secret}", {}) is False
    assert secret not in str(log.call_args)


def test_smtp_refuses_plaintext_authentication():
    cfg = SimpleNamespace(
        smtp_host="smtp.example.test", smtp_port=25, smtp_user="user",
        smtp_pass="fake-password", smtp_from="user@example.test",
        email_to=["recipient@example.test"],
    )
    connection = MagicMock()
    connection.__enter__.return_value = connection
    connection.has_extn.return_value = False
    with patch("smtplib.SMTP", return_value=connection):
        assert Pusher(cfg)._send_email("brief", "<p>brief</p>", "2026-11-16") == "失败"
    connection.login.assert_not_called()
    connection.sendmail.assert_not_called()


def _agent(push_result, generated_title="安防摄像头新品发布"):
    event = SecurityEvent(
        title="安防摄像头新品发布", source="rss:source", category="personnel",
        published_at=datetime.now(timezone.utc),
    )
    collector = Mock(name="collector")
    collector.name = "rss:source"
    collector.collect.return_value = [event]
    dedup = Mock()
    dedup.filter.side_effect = lambda events: events
    summarizer = Mock()

    def summarize(events):
        events[0].title = generated_title
        return events

    summarizer.summarize_events.side_effect = summarize
    summarizer.assess.return_value = "态势平稳"
    report = Mock()
    report.render_markdown.return_value = "brief"
    report.write_files.return_value = {"date": "2026-11-16", "pdf": None}
    report.render_email_html.return_value = "<p>brief</p>"
    report.render_poster_image.return_value = b""
    pusher = Mock()
    pusher.push.return_value = push_result
    agent = BriefAgent(
        collectors=[collector], classifier=Classifier(), rater=SeverityRater(),
        dedup=dedup, summarizer=summarizer, report=report, pusher=pusher,
        tagger=Tagger(), sector_classifier=SectorClassifier(),
        sensitive_filter=SensitiveFilter(),
    )
    return agent, dedup, report, pusher


def test_failed_delivery_does_not_mark_event_seen():
    agent, dedup, _, _ = _agent({"wecom": "失败", "email": "跳过（未配置）"})
    assert len(agent.run_daily()) == 1
    dedup.mark_seen.assert_not_called()
    dedup.save.assert_not_called()


def test_generated_title_is_filtered_before_report():
    agent, dedup, report, pusher = _agent(
        {"email": "成功"}, generated_title="苹果公司推出摄像头"
    )
    assert agent.run_daily() == []
    report.write_files.assert_not_called()
    pusher.push.assert_not_called()
    dedup.mark_seen.assert_not_called()


def test_generated_assessment_uses_fallback_when_filtered():
    agent, _, report, _ = _agent({"email": "成功"})
    agent.summarizer.assess.return_value = "苹果公司需要重点关注"
    agent.summarizer._template_assess.return_value = "今日态势平稳"
    agent.run_daily()
    agent.summarizer._template_assess.assert_called_once()
    assert report.write_files.call_args.args[1] == "今日态势平稳"
