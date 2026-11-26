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
    "https://securityjournaluk.com/feed/|personnel",
    "https://internationalsecurityjournal.com/feed/|personnel",
    "https://securitylinkindia.com/feed/|personnel",
    "https://revistasegurancaeletronica.com.br/feed/|personnel",
    "https://www.send2press.com/wire/technology-news/security-tech-news/feed/|personnel",
    "https://security.world/feed/|personnel",
    "https://www.securitymagazine.com/rss/articles|personnel",
    "https://www.sdmmag.com/rss/articles|personnel",
    "https://www.securityinfowatch.com/__rss/website-scheduled-content.xml?input=%7B%22sectionAlias%22%3A%22home%22%7D|personnel",
    "https://www.securitysales.com/feed/atom/|personnel",
    "https://australiansecuritymagazine.com.au/feed/|personnel",
    "https://tma.us/feed/|personnel",
    "https://benchmarkmagazine.com/feed/|personnel",
    "https://www.asiapacificsecuritymagazine.com/feed/|personnel",
    "https://www.securitysolutions.com.au/feed/|personnel",
    "https://news.google.com/rss/search?q=%22physical+security%22&hl=en-US&gl=US&ceid=US:en|personnel",
    "https://news.google.com/rss/search?q=%22access+control%22+security&hl=en-US&gl=US&ceid=US:en|personnel",
    "https://news.google.com/rss/search?q=%22video+surveillance%22&hl=en-US&gl=US&ceid=US:en|personnel",
    "https://news.google.com/rss/search?q=%22security+camera%22&hl=en-US&gl=US&ceid=US:en|personnel",
    "https://news.google.com/rss/search?q=%22perimeter+security%22&hl=en-US&gl=US&ceid=US:en|personnel",
    "https://news.google.com/rss/search?q=site%3Asourcesecurity.com&hl=en-US&gl=US&ceid=US:en|personnel",
    "https://news.google.com/rss/search?q=site%3Asecuritymiddleeast.com&hl=en-US&gl=US&ceid=US:en|personnel",
    "https://news.google.com/rss/search?q=site%3Aifsecglobal.com&hl=en-US&gl=US&ceid=US:en|personnel",
    "https://news.google.com/rss/search?q=site%3Asecurityindustry.org&hl=en-US&gl=US&ceid=US:en|personnel",
    "https://news.google.com/rss/search?q=site%3Aasisonline.org&hl=en-US&gl=US&ceid=US:en|personnel",
    "https://news.google.com/rss/search?q=%E5%AE%89%E9%98%B2&hl=zh-CN&gl=CN&ceid=CN:zh-Hans|personnel",
    "https://news.google.com/rss/search?q=%E6%B5%B7%E5%BA%B7%E5%A8%81%E8%A7%86&hl=zh-CN&gl=CN&ceid=CN:zh-Hans|personnel",
    "https://news.google.com/rss/search?q=%E5%A4%A7%E5%8D%8E%E8%82%A1%E4%BB%BD&hl=zh-CN&gl=CN&ceid=CN:zh-Hans|personnel",
    "https://news.google.com/rss/search?q=%E5%AE%87%E8%A7%86&hl=zh-CN&gl=CN&ceid=CN:zh-Hans|personnel",
    "https://news.google.com/rss/search?q=%E5%AE%89%E9%98%B2+OR+%E8%A7%86%E9%A2%91%E7%9B%91%E6%8E%A7+OR+%E9%97%A8%E7%A6%81+OR+%E4%BA%BA%E8%84%B8%E8%AF%86%E5%88%AB&hl=zh-CN&gl=CN&ceid=CN:zh-Hans|personnel",
    "https://news.google.com/rss/search?q=%E5%AE%89%E9%98%B2&hl=zh-TW&gl=TW&ceid=TW:zh-Hant|personnel",
    "https://news.google.com/rss/search?q=%28%E5%A4%A9%E5%9C%B0%E4%BC%9F%E4%B8%9A%20OR%20%E7%86%B5%E5%9F%BA%E7%A7%91%E6%8A%80%20OR%20%E6%97%B7%E8%A7%86%E7%A7%91%E6%8A%80%20OR%20%E5%95%86%E6%B1%A4%E7%A7%91%E6%8A%80%20OR%20%E4%BD%B3%E9%83%BD%E7%A7%91%E6%8A%80%20OR%20%E6%8D%B7%E9%A1%BA%E7%A7%91%E6%8A%80%29%20when%3A7d&hl=zh-CN&gl=CN&ceid=CN:zh-Hans|personnel",
    "https://news.google.com/rss/search?q=%28%E5%AE%89%E9%98%B2%20OR%20%E8%A7%86%E9%A2%91%E7%9B%91%E6%8E%A7%29%20%28%E4%B8%9C%E5%8D%97%E4%BA%9A%20OR%20%E4%B8%AD%E4%B8%9C%20OR%20%E5%8D%B0%E5%BA%A6%20OR%20%E6%8B%89%E7%BE%8E%29%20when%3A7d&hl=zh-CN&gl=CN&ceid=CN:zh-Hans|personnel",
    "https://news.google.com/rss/search?q=%28%E5%AE%89%E5%8D%9A%E4%BC%9A%20OR%20%E5%AE%89%E9%98%B2%E5%B1%95%20OR%20%E5%AE%89%E9%98%B2%E5%B3%B0%E4%BC%9A%29%20when%3A7d&hl=zh-CN&gl=CN&ceid=CN:zh-Hans|personnel",
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
        self.rss_limit = _get_int("RSS_LIMIT", 30)

        # MFA 外交部提醒（可选，需自行提供 RSS）
        self.mfa_feed = _get_str("MFA_FEED", "")

        # HTML 采集（中文安防门户，无 RSS，服务端渲染；见 app/collectors/html.py）
        # 21csp=中国安防行业网（协会） afzhan=安防展览网/智慧城市网 asmag=安防知识网
        self.html_sites = _get_list("HTML_SITES", "21csp,afzhan,asmag")
        self.html_limit = _get_int("HTML_LIMIT", 10)

        # ---- 处理 ----
        self.top_n = _get_int("TOP_N", 15)
        # 突发事件（袭击/灾害等）不进入日报：0 = 不收录
        self.emergency_quota = _get_int("EMERGENCY_QUOTA", 0)
        self.dedup_days = _get_int("DEDUP_DAYS", 7)
        # 标题相似度阈值：同一事件的不同媒体改写报道也会被判为重合，压低跨天重复率
        self.title_similarity = _get_float("TITLE_SIMILARITY", 0.78)
        self.severity_highlight = _get_int("SEVERITY_HIGHLIGHT", 4)
        # 单来源配额：同一 source 名最多入选 N 条，避免 Google 新闻等聚合源霸屏。
        # 0 = 不限制。默认 6 以保留多源多样性。
        self.max_per_source = _get_int("MAX_PER_SOURCE", 6)
        # 时间窗：只保留最近 N 小时内的新闻。默认 72h 以覆盖周末——
        # 工作日 08:30 运行时，24h 窗口会漏掉上周五发布的行业新闻。
        # 跨天去重仍按 DEDUP_DAYS 生效，不会重复上报。
        self.time_window_hours = _get_int("TIME_WINDOW_HOURS", 72)

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
        self.serverchan_key = _get_str("SERVERCHAN_KEY", "")  # Server酱 个人微信推送
        self.smtp_host = _get_str("SMTP_HOST", "")
        self.smtp_port = _get_int("SMTP_PORT", 465)
        self.smtp_user = _get_str("SMTP_USER", "")
        self.smtp_pass = _get_str("SMTP_PASS", "")
        self.smtp_from = _get_str("SMTP_FROM", "")  # 默认取 SMTP_USER
        self.email_to = _get_list("EMAIL_TO", "")
        self.email_cc = _get_str("EMAIL_CC", "")  # 抄送（可含「姓名 <邮箱>」格式，逗号分隔）

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
