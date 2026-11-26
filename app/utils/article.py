"""文章正文抓取：为只有标题的入选条目补齐原文内容。

仅对已入选的少量条目调用（最多 TOP_N 条），不做全量抓取。
Google 新闻等跳转链接无法直接取正文，直接跳过。
"""
from __future__ import annotations

import html
import re

import requests

from app.utils.logging import get_logger

logger = get_logger("article")

_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)

# 这些域名无法直接取到正文（跳转/聚合页）
_SKIP_HOSTS = ("news.google.com", "news.url.google.com", "googleusercontent.com")


def _extract_main_text(markup: str, max_chars: int) -> str:
    """从 HTML 中提取正文段落文本。"""
    text = re.sub(r"<script.*?</script>", " ", markup, flags=re.S | re.I)
    text = re.sub(r"<style.*?</style>", " ", text, flags=re.S | re.I)
    text = re.sub(r"<nav.*?</nav>", " ", text, flags=re.S | re.I)
    text = re.sub(r"<footer.*?</footer>", " ", text, flags=re.S | re.I)
    text = re.sub(r"<header.*?</header>", " ", text, flags=re.S | re.I)

    # 优先取 <article> 区块，否则退回全文
    article = re.search(r"<article[^>]*>.*?</article>", text, flags=re.S | re.I)
    scope = article.group(0) if article else text

    paragraphs = []
    for raw in re.findall(r"<p[^>]*>(.*?)</p>", scope, flags=re.S | re.I):
        plain = html.unescape(re.sub(r"<[^>]+>", " ", raw))
        plain = re.sub(r"\s+", " ", plain).strip()
        if len(plain) >= 40:
            paragraphs.append(plain)

    body = " ".join(paragraphs)
    # 去掉重复出现的导航式短句
    body = re.sub(r"\s{2,}", " ", body)
    return body[:max_chars]


def fetch_article_text(url: str, timeout: int = 12, max_chars: int = 4000) -> str:
    """抓取文章正文；失败或不可抓取时返回空串。"""
    if not url or any(host in url for host in _SKIP_HOSTS):
        return ""
    try:
        resp = requests.get(url, timeout=timeout, headers={"User-Agent": _UA})
        resp.raise_for_status()
        content_type = (resp.headers.get("content-type") or "").lower()
        if "html" not in content_type:
            return ""
        if not resp.encoding or resp.encoding.lower() == "iso-8859-1":
            resp.encoding = resp.apparent_encoding or "utf-8"
        return _extract_main_text(resp.text, max_chars)
    except Exception as exc:
        logger.info("正文抓取失败 %s：%s", url[:70], exc)
        return ""
