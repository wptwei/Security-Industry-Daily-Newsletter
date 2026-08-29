"""应用配置：从 .env 读取，全部带合理缺省值，开箱即用。

所有公开数据源（GDELT / ReliefWeb / USGS / CISA / RSS）均无需 API key；
LLM 走任意 OpenAI 兼容接口（DeepSeek / Kimi / Qwen / 中转），换供应商只改 .env。
"""
from __future__ import annotations

import os
import re
from pathlib import Path
from typing import List, Tuple

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

# 默认 RSS 信源：`URL|领域`，可自行增删
DEFAULT_RSS_FEEDS = (
    "http://feeds.bbci.co.uk/news/world/rss.xml|geopolitical,"
    "https://www.aljazeera.com/xml/rss/all.xml|geopolitical,"
    "https://www.theguardian.com/world/rss|geopolitical,"
    "https://thehackernews.com/feeds/posts/default|cyber,"
    "https://krebsonsecurity.com/feed/|cyber,"
    "https://www.bleepingcomputer.com/feed/|cyber"
)


def _clean(raw):
    """去掉内联注释，避免「# 注释」被当成值的一部分。

    python-dotenv 会把 `KEY=   # 注释` 解析成值 `# 注释`（前导空格被剥掉），
    因此除了去尾部注释，还要把「值以 # 开头」整体视为空。
    """
    if raw is None:
        return None
    raw = raw.strip()
    if raw.startswith("#"):
        return ""
    return re.sub(r"\s+#.*$", "", raw).strip()


def _get_str(name: str, default: str = "") -> str:
    raw = _clean(os.getenv(name))
    return raw if raw else default


def _get_int(name: str, default: int) -> int:
    raw = _clean(os.getenv(name))
    if raw is None or raw == "":
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _get_float(name: str, default: float) -> float:
    raw = _clean(os.getenv(name))
    if raw is None or raw == "":
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def _get_bool(name: str, default: bool) -> bool:
    raw = _clean(os.getenv(name))
    if raw is None or raw == "":
        return default
    return raw.lower() in ("1", "true", "yes", "on")


def _get_list(name: str, default: str) -> List[str]:
    raw = _clean(os.getenv(name, default))
    return [item.strip() for item in raw.split(",") if item.strip()]


def _parse_rss_feeds(raw: str) -> List[Tuple[str, str]]:
    """解析 `URL|category,URL|category` 为 [(url, category)]。"""
    feeds: List[Tuple[str, str]] = []
    for item in raw.split(","):
        item = item.strip()
        if not item:
            continue
        parts = item.split("|")
        url = parts[0].strip()
        category = parts[1].strip() if len(parts) > 1 and parts[1].strip() else "geopolitical"
        if url:
            feeds.append((url, category))
    return feeds


class Config:
    def __init__(self) -> None:
        # ---- LLM（OpenAI 兼容）----
        self.enable_llm = _get_bool("ENABLE_LLM", True)
        self.llm_api_base = _get_str("LLM_API_BASE", "https://api.deepseek.com")
        self.llm_api_key = _get_str("LLM_API_KEY", "")
        self.llm_model = _get_str("LLM_MODEL", "deepseek-chat")
        self.llm_timeout = _get_int("LLM_TIMEOUT", 60)

        # ---- 采集开关 ----
        self.enable_gdelt = _get_bool("ENABLE_GDELT", True)
        self.enable_reliefweb = _get_bool("ENABLE_RELIEFWEB", False)  # 需先注册 ReliefWeb appname
        self.enable_usgs = _get_bool("ENABLE_USGS", True)
        self.enable_cisa = _get_bool("ENABLE_CISA", True)
        self.enable_nvd = _get_bool("ENABLE_NVD", False)
        self.enable_mfa = _get_bool("ENABLE_MFA", False)

        # GDELT
        self.gdelt_query = _get_str(
            "GDELT_QUERY",
            "conflict OR terrorism OR earthquake OR epidemic OR cyberattack OR coup",
        )
        self.gdelt_timespan = _get_str("GDELT_TIMESPAN", "1d")
        self.gdelt_limit = _get_int("GDELT_LIMIT", 30)

        # ReliefWeb
        self.reliefweb_limit = _get_int("RELIEFWEB_LIMIT", 20)
        self.reliefweb_appname = _get_str("RELIEFWEB_APPNAME", "security-intel-agent")

        # USGS 地震
        self.usgs_min_mag = _get_float("USGS_MIN_MAG", 4.5)
        self.usgs_limit = _get_int("USGS_LIMIT", 20)

        # CISA 已知被利用漏洞
        self.cisa_limit = _get_int("CISA_LIMIT", 10)

        # NVD（可选，限流）
        self.nvd_limit = _get_int("NVD_LIMIT", 10)
        self.nvd_api_key = _get_str("NVD_API_KEY", "")

        # RSS（通用）
        self.rss_feeds = _parse_rss_feeds(
            _clean(os.getenv("RSS_FEEDS", DEFAULT_RSS_FEEDS)) or DEFAULT_RSS_FEEDS
        )
        self.rss_limit = _get_int("RSS_LIMIT", 15)

        # MFA 外交部提醒（可选，需自行提供 RSS）
        self.mfa_feed = _get_str("MFA_FEED", "")

        # ---- 处理 ----
        self.top_n = _get_int("TOP_N", 8)
        self.emergency_quota = _get_int("EMERGENCY_QUOTA", 2)
        self.dedup_days = _get_int("DEDUP_DAYS", 7)
        self.severity_highlight = _get_int("SEVERITY_HIGHLIGHT", 4)

        # 采集过滤关键词（正向保留物理安防 / 负向排除网络安全噪音）
        self.filter_positive = _get_list(
            "FILTER_POSITIVE",
            "physical security,access control,perimeter,surveillance,intrusion detection,"
            "critical infrastructure,周界,门禁,视频监控,实体防护,物防技防,入侵探测",
        )
        self.filter_negative = _get_list(
            "FILTER_NEGATIVE",
            "cyber security,vulnerability,exploit,malware,漏洞,病毒,渗透,网络攻击",
        )
        self.history_file = Path(
            _get_str("HISTORY_FILE", str(BASE_DIR / "output" / "history.json"))
        )

        # ---- 推送 ----
        self.wecom_webhook = _get_str("WECOM_WEBHOOK", "")
        self.dingtalk_webhook = _get_str("DINGTALK_WEBHOOK", "")
        self.dingtalk_secret = _get_str("DINGTALK_SECRET", "")
        self.feishu_webhook = _get_str("FEISHU_WEBHOOK", "")
        self.smtp_host = _get_str("SMTP_HOST", "")
        self.smtp_port = _get_int("SMTP_PORT", 465)
        self.smtp_user = _get_str("SMTP_USER", "")
        self.smtp_pass = _get_str("SMTP_PASS", "")
        self.smtp_from = _get_str("SMTP_FROM", "")  # 默认取 SMTP_USER
        self.email_to = _get_list("EMAIL_TO", "")

        # ---- 网络代理（可选）----
        # 国内 IP 访问境外源（BBC/Guardian/Al Jazeera 等）时可配代理；邮件（SMTP）
        # 不走代理，本地采集无需代理。留空则不走代理。
        self.proxy_http = _get_str("PROXY_HTTP", "")
        self.proxy_https = _get_str("PROXY_HTTPS", "")
        if self.proxy_https:
            os.environ["HTTPS_PROXY"] = self.proxy_https
            os.environ["https_proxy"] = self.proxy_https
        if self.proxy_http:
            os.environ["HTTP_PROXY"] = self.proxy_http
            os.environ["http_proxy"] = self.proxy_http

        # ---- 输出与调度 ----
        self.output_dir = Path(_get_str("OUTPUT_DIR", str(BASE_DIR / "output")))
        self.schedule_time = _get_str("SCHEDULE_TIME", "07:30")
        self.log_level = _get_str("LOG_LEVEL", "INFO")
        self.user_agent = _get_str(
            "USER_AGENT",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        )
        self.http_timeout = _get_int("HTTP_TIMEOUT", 20)
