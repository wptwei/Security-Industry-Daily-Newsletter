"""中文安防门户 HTML 采集器。

中安网 CPS / 千家网 / 安防知识网等门户没有 RSS，新闻列表是服务端渲染的 HTML。
本采集器按站点规则解析列表页拿到文章链接，再抓取文章页提取标题、正文与发布日期。

只依赖 requests + 正则，与项目其他采集器保持一致；单个站点或单篇文章失败不影响整体。
"""
from __future__ import annotations

import html as _html
import re
from datetime import datetime
from typing import Callable, Dict, List, Optional

import requests

from app.collectors.base import BaseCollector
from app.models.event import SecurityEvent
from app.utils.logging import get_logger

logger = get_logger("html")

_DEFAULT_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)

# 日期：2026-11-05 / 2026/11/05 / 2026年11月05日
_DATE_RE = re.compile(r"(20\d{2})[-/年](\d{1,2})[-/月](\d{1,2})")
# 标题与站名分隔符（按站点顺序尝试）
_TITLE_SEPS = ("_", "-", "｜", "|")


def _collapse(s: str) -> str:
    """去标签/脚本/样式/实体，压缩空白为纯文本。"""
    if not s:
        return ""
    s = re.sub(r"<script.*?</script>", " ", s, flags=re.S | re.I)
    s = re.sub(r"<style.*?</style>", " ", s, flags=re.S | re.I)
    s = re.sub(r"<[^>]+>", " ", s)
    s = _html.unescape(s)
    s = re.sub(r"\s+", " ", s)
    return s.strip()


def _div_content(html_text: str, class_name: str) -> str:
    """提取第一个 class=class_name 的 <div> 内部文本，正确处理嵌套 div。"""
    pattern = re.compile(
        r'<div[^>]*class=["\'][^"\']*\b' + re.escape(class_name) + r'\b[^"\']*["\'][^>]*>',
        re.I,
    )
    m = pattern.search(html_text)
    if not m:
        return ""
    tag_re = re.compile(r"<(/?div)\b[^>]*>", re.I)
    depth = 1
    pos = m.end()
    while depth > 0:
        tm = tag_re.search(html_text, pos)
        if not tm:
            break
        if tm.group(1).lower() == "div":
            depth += 1
        else:
            depth -= 1
        if depth == 0:
            return _collapse(html_text[m.end():tm.start()])
        pos = tm.end()
    return _collapse(html_text[m.end():])


def _extract_title(html_text: str) -> str:
    m = re.search(r"<title[^>]*>(.*?)</title>", html_text, re.S | re.I)
    if not m:
        return ""
    title = _collapse(m.group(1))
    # 去掉「- 站点名」「_站点名_栏目」等后缀
    for sep in _TITLE_SEPS:
        if sep in title:
            first = title.split(sep, 1)[0].strip()
            if len(first) >= 6:
                return first
    return title


def _extract_date(html_text: str, url: str) -> Optional[datetime]:
    # 只在正文容器之前的头部区域找，避免底部「相关文章」的日期干扰
    head = html_text
    for marker in ("NewsContent", "newsContent"):
        i = html_text.find(marker)
        if i > 0:
            head = html_text[:i]
            break
    # 优先带时分的日期（如 <span class="time">2026-11-10 12:15</span>），
    # 否则「Nov 13 12:15」会被当成「Nov 13 00:00」，在时间窗边界被误杀。
    m = re.search(r"(20\d{2})[-/年](\d{1,2})[-/月](\d{1,2})日?\s*(\d{1,2}):(\d{2})", head)
    if m:
        try:
            return datetime(int(m.group(1)), int(m.group(2)), int(m.group(3)), int(m.group(4)), int(m.group(5)))
        except ValueError:
            pass
    # 回退：仅日期
    m = re.search(r"(?:发布时间|时间|日期|time)[^0-9]{0,24}" + _DATE_RE.pattern, head)
    if not m:
        m = _DATE_RE.search(head)
    if m:
        try:
            return datetime(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        except ValueError:
            pass
    # 回退：从 URL 的 /YYYYMM/ 取月份
    mu = re.search(r"/(20\d{2})(\d{2})/", url)
    if mu:
        try:
            return datetime(int(mu.group(1)), int(mu.group(2)), 1)
        except ValueError:
            pass
    return None


# ---- 站点解析规则 ----
# 每个站点：名称 / 领域 / 列表页 / 列表页里的文章链接正则 / 正文 class / 是否需要抓文章页正文
_SITE_PARSERS: Dict[str, dict] = {
    "21csp": {
        "name": "html:21csp",
        "category": "personnel",
        "list_urls": ["http://xh.21csp.com.cn/C58/index.html"],
        "link_re": re.compile(r'href=["\'](http://xh\.21csp\.com\.cn/c5[89]/\d{6}/\d+\.html)["\']', re.I),
        "body_class": "NewsContent",
    },
    "afzhan": {
        "name": "html:afzhan",
        "category": "personnel",
        "list_urls": [
            "https://www.afzhan.com/news/t12/list.html",    # 市场分析（智能安防行业走向）
            "https://www.afzhan.com/news/t10/list.html",    # 时事聚焦（安全生产/政策）
        ],
        "link_re": re.compile(r'href=["\'](https://www\.afzhan\.com/news/detail/\d+\.html)["\']', re.I),
        "body_class": "newsContent",
    },
    "asmag": {
        "name": "html:asmag",
        "category": "personnel",
        "list_urls": ["https://www.asmag.com.cn/"],  # 首页含最新资讯（列表页置顶旧文较多）
        "link_re": re.compile(r'href=["\'](https://www\.asmag\.com\.cn/news/\d{6}/\d+\.html)["\']', re.I),
        "body_class": "article",
        "url_date_re": re.compile(r"/news/(\d{6})/"),
    },
}


def _fetch(url: str, timeout: int) -> Optional[str]:
    """GET 并按 apparent_encoding 解码，失败返回 None。"""
    try:
        resp = requests.get(url, timeout=timeout, headers={"User-Agent": _DEFAULT_UA})
        resp.raise_for_status()
        if not resp.text:
            return None
        resp.encoding = resp.apparent_encoding
        return resp.text
    except Exception as exc:
        logger.warning("HTML 抓取失败 %s：%s", url, exc)
        return None


class HtmlNewsCollector(BaseCollector):
    """按站点规则抓取一个中文门户的最新新闻。"""

    def __init__(self, site_key: str, limit: int = 10, timeout: int = 20) -> None:
        parser = _SITE_PARSERS[site_key]
        self.site_key = site_key
        self.name = parser["name"]
        self.category = parser["category"]
        self.list_urls = parser["list_urls"]
        self.link_re = parser["link_re"]
        self.body_class = parser["body_class"]
        self.url_date_re = parser.get("url_date_re")
        self.limit = limit
        self.timeout = timeout

    def collect(self) -> List[SecurityEvent]:
        # 1) 列表页提取去重后的文章链接（保持出现顺序）
        links: List[str] = []
        seen = set()
        for list_url in self.list_urls:
            text = _fetch(list_url, self.timeout)
            if not text:
                continue
            for link in self.link_re.findall(text):
                if link not in seen:
                    seen.add(link)
                    links.append(link)

        # 若 URL 里带日期（如 /news/202611/），按日期倒序，优先抓最新文章
        if self.url_date_re is not None:
            def _date_key(link: str) -> str:
                m = self.url_date_re.search(link)
                return m.group(1) if m else "0"
            links.sort(key=_date_key, reverse=True)

        # 2) 逐篇抓文章页，提取标题/正文/日期
        events: List[SecurityEvent] = []
        for url in links[: self.limit]:
            text = _fetch(url, self.timeout)
            if not text:
                continue
            title = _extract_title(text) or url
            body = _div_content(text, self.body_class)
            published = _extract_date(text, url)
            events.append(
                SecurityEvent(
                    title=title,
                    source=self.name,
                    url=url,
                    category=self.category,
                    raw=body or title,
                    published_at=published,
                    event_id=url,
                )
            )
        logger.info("HTML 采集器 %s 采集到 %d 条", self.name, len(events))
        return events


def build_html_collectors(site_keys: List[str], limit: int, timeout: int) -> List[HtmlNewsCollector]:
    """根据配置的站点 key 列表构造采集器；未知 key 自动跳过。"""
    collectors: List[HtmlNewsCollector] = []
    for key in site_keys:
        if key not in _SITE_PARSERS:
            logger.warning("未知 HTML 站点：%s（可用：%s）", key, "、".join(_SITE_PARSERS))
            continue
        collectors.append(HtmlNewsCollector(key, limit=limit, timeout=timeout))
    return collectors
