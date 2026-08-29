"""入口。

用法：
    python -m app.main             # 立即运行一次并输出简报
    python -m app.main --schedule  # 进入工作日定时模式
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

# 让 `python app/main.py` 与 `python -m app.main` 都能定位到 app 包
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# 统一控制台编码为 UTF-8，避免 Windows 下中文乱码
for _stream in (sys.stdout, sys.stderr):
    if _stream and hasattr(_stream, "reconfigure"):
        try:
            _stream.reconfigure(encoding="utf-8")
        except Exception:
            pass

from app.agents.brief_agent import BriefAgent
from app.collectors.cisa import CISACollector
from app.collectors.gdelt import GDELTCollector
from app.collectors.mfa import MFACollector
from app.collectors.nvd import NVDCollector
from app.collectors.reliefweb import ReliefWebCollector
from app.collectors.rss import RSSCollector
from app.collectors.usgs import USGSCollector
from app.config import Config
from app.services.classifier import Classifier
from app.services.dedup import DedupStore
from app.services.pusher import Pusher
from app.services.report import ReportService
from app.services.scheduler import Scheduler
from app.services.severity import SeverityRater
from app.services.summarizer import Summarizer
from app.services.tagger import Tagger
from app.services.sector import SectorClassifier
from app.services.sensitive import SensitiveFilter
from app.utils.logging import get_logger


def build_agent(config: Config) -> BriefAgent:
    collectors = []
    if config.enable_gdelt:
        collectors.append(
            GDELTCollector(config.gdelt_query, config.gdelt_timespan, config.gdelt_limit, config.http_timeout)
        )
    if config.enable_reliefweb:
        collectors.append(ReliefWebCollector(config.reliefweb_appname, config.reliefweb_limit, config.http_timeout))
    if config.enable_usgs:
        collectors.append(USGSCollector(config.usgs_min_mag, config.usgs_limit, config.http_timeout))
    if config.enable_cisa:
        collectors.append(CISACollector(config.cisa_limit, config.http_timeout))
    if config.enable_nvd:
        collectors.append(
            NVDCollector(config.nvd_limit, config.nvd_api_key, config.user_agent, config.http_timeout)
        )
    for feed_url, category in config.rss_feeds:
        collectors.append(
            RSSCollector(feed_url, category, config.rss_limit, config.user_agent, config.http_timeout)
        )
    if config.enable_mfa:
        collectors.append(MFACollector(config.mfa_feed, config.rss_limit, config.user_agent))

    return BriefAgent(
        collectors=collectors,
        classifier=Classifier(
            extra_positive=tuple(config.filter_positive),
            extra_negative=tuple(config.filter_negative),
        ),
        rater=SeverityRater(),
        dedup=DedupStore(config.history_file, days=config.dedup_days),
        summarizer=Summarizer(
            config.enable_llm, config.llm_api_base, config.llm_api_key, config.llm_model, config.llm_timeout
        ),
        report=ReportService(config.output_dir, config.severity_highlight),
        pusher=Pusher(config),
        tagger=Tagger(),
        sector_classifier=SectorClassifier(),
        sensitive_filter=SensitiveFilter(),
        top_n=config.top_n,
        severity_highlight=config.severity_highlight,
        emergency_quota=config.emergency_quota,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="全球安防咨询情报自动化系统")
    parser.add_argument("--once", action="store_true", help="立即运行一次后退出（默认）")
    parser.add_argument("--schedule", action="store_true", help="进入工作日定时模式")
    args = parser.parse_args()

    config = Config()
    get_logger("app", config.log_level)

    agent = build_agent(config)

    if args.schedule:
        Scheduler(agent, schedule_time=config.schedule_time).start()
    else:
        agent.run_daily()


if __name__ == "__main__":
    main()
