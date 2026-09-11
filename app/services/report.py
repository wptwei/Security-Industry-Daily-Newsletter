"""报告生成：Markdown / HTML / PDF（海报卡片风）。

PDF 通过「精美海报 HTML + Edge/Chrome 无头打印」生成，而非 reportlab，
可呈现卡片式布局、emoji 图标、彩色分类标签、严重度色块等视觉效果。
"""
from __future__ import annotations

import html
import json
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Dict, List

from app.models.event import SecurityEvent
from app.utils.logging import get_logger

logger = get_logger("report")

# 严重度颜色
SEV_COLORS = {5: "#c0392b", 4: "#e67e22", 3: "#d4a017", 2: "#27ae60", 1: "#95a5a6"}
SEV_BG = {5: "#fdecea", 4: "#fef3e2", 3: "#fdf6e3", 2: "#eafaf1", 1: "#f2f3f4"}

# 行业子类图标与颜色
SECTOR_META = {
    "physical": {"icon": "🏗️", "color": "#2c3e50"},
    "hardware": {"icon": "🔐", "color": "#8e44ad"},
    "perimeter": {"icon": "🛡️", "color": "#16a085"},
    "ai": {"icon": "🧠", "color": "#2980b9"},
    "smart": {"icon": "📹", "color": "#d35400"},
    "summit": {"icon": "🎪", "color": "#e67e22"},
    "industry": {"icon": "📈", "color": "#27ae60"},
    "robot": {"icon": "🤖", "color": "#7f8c8d"},
    "emergency": {"icon": "🚨", "color": "#c0392b"},
}


def _find_browser() -> str:
    """定位可用的 Chromium 内核浏览器（Edge / Chrome / Chromium），用于 HTML 转 PDF。"""
    candidates = [
        # Windows
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        # Linux（GitHub Actions ubuntu runner 等）
        "/usr/bin/google-chrome",
        "/usr/bin/google-chrome-stable",
        "/usr/bin/chromium",
        "/usr/bin/chromium-browser",
        # macOS
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
    ]
    for c in candidates:
        if Path(c).exists():
            return c
    return ""


def _register_embedded_cjk_font() -> str:
    """跨平台注册一个可内嵌的中文字体，返回字体名；找不到则返回空串。

    reportlab 的 UnicodeCIDFont（如 STSong-Light）生成的 PDF 只引用字体名、
    不内嵌字形，在无对应字体的阅读器上会显示乱码。这里改为内嵌 TrueType 中文字体，
    让任何阅读器都能正确显示中文。
    """
    import platform

    from reportlab.pdfbase import pdfmetrics  # pyright: ignore[reportMissingModuleSource]
    from reportlab.pdfbase.ttfonts import TTFont  # pyright: ignore[reportMissingModuleSource]

    system = platform.system()
    if system == "Windows":
        candidates = [
            (r"C:\Windows\Fonts\msyh.ttc", 0),     # 微软雅黑
            (r"C:\Windows\Fonts\simsun.ttc", 0),   # 宋体
            (r"C:\Windows\Fonts\simhei.ttf", 0),   # 黑体
        ]
    else:
        candidates = [
            ("/usr/share/fonts/truetype/wqy/wqy-microhei.ttc", 0),
            ("/usr/share/fonts/truetype/droid/DroidSansFallbackFull.ttf", 0),
            ("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc", 2),
        ]
    for path, subfont in candidates:
        if not Path(path).exists():
            continue
        try:
            pdfmetrics.registerFont(TTFont("CJKEmbed", path, subfontIndex=subfont))
            return "CJKEmbed"
        except Exception:
            continue
    return ""


class ReportService:
    def __init__(self, output_dir: Path, severity_highlight: int = 4) -> None:
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.severity_highlight = severity_highlight

    @staticmethod
    def _date_str() -> str:
        return datetime.now().strftime("%Y-%m-%d")

    @staticmethod
    def _date_cn() -> str:
        now = datetime.now()
        weekdays = ["星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日"]
        return f"{now.year}年{now.month}月{now.day}日 {weekdays[now.weekday()]}"

    @staticmethod
    def _group_by_sector(events: List[SecurityEvent]) -> "Dict[str, List[SecurityEvent]]":
        grouped: Dict[str, List[SecurityEvent]] = {}
        for e in events:
            grouped.setdefault(e.sector, []).append(e)
        return grouped

    # ---------- Markdown ----------
    def render_markdown(self, events: List[SecurityEvent], assess: str) -> str:
        date_str = self._date_str()
        lines = [
            f"# 🔍 安防行业日报 · {date_str}",
            "",
            "## 今日态势研判",
            "",
            assess,
            "",
        ]
        grouped = self._group_by_sector(events)
        for sector, items in grouped.items():
            icon = SECTOR_META.get(sector, {}).get("icon", "🔍")
            label = items[0].sector_label if items else sector
            lines.append(f"## {icon} {label}（{len(items)} 条）")
            lines.append("")
            for e in items:
                lines.append(self._markdown_item(e))
            lines.append("")
        lines.append("## 数据来源")
        lines.append("")
        sources = sorted({e.source for e in events})
        lines.append("、".join(sources))
        return "\n".join(lines)

    @staticmethod
    def _markdown_item(e: SecurityEvent) -> str:
        place = f" · {e.country}" if e.country else ""
        tag = f" `{e.tag_label()}`" if e.tag_label() else ""
        # 标题（简洁中文总结）+ 摘要（详细提炼）
        title = e.title or ""
        summary = e.summary or ""
        if title and title != summary:
            return f"- **[{e.severity_label}] {title}**{place} {tag}\n  {summary}".strip()
        return f"- **[{e.severity_label}]** {summary}{place} {tag}".strip()

    @staticmethod
    def _clean_assess(assess: str) -> str:
        """清理研判文本：去掉 markdown 加粗、小标题、序号、列表符号、多余换行，统一为干净段落。"""
        import re
        text = assess or ""
        # 去 markdown 加粗/斜体/标题标记
        text = re.sub(r"\*\*([^*]+)\*\*", r"\1", text)
        text = re.sub(r"\*([^*]+)\*", r"\1", text)
        text = re.sub(r"^#{1,6}\s*", "", text, flags=re.MULTILINE)
        # 去「一、二、三」「1. 2. 3.」等序号前缀（仅行首）
        text = re.sub(r"^[一二三四五六七八九十]+[、.，]\s*", "", text, flags=re.MULTILINE)
        text = re.sub(r"^\d+[.、)]\s*", "", text, flags=re.MULTILINE)
        # 去列表符号（行首的 - * • · 等）
        text = re.sub(r"^\s*[-*•·]\s*", "", text, flags=re.MULTILINE)
        # 去掉「小标题」行：以常见标题词开头且很短的行（如「今日总体态势」「需重点关注」「行动建议」）
        stop_titles = ("今日总体态势", "总体态势", "需重点关注", "重点关注", "行动建议", "研判结论", "态势研判")
        lines = []
        for line in text.splitlines():
            stripped = line.strip()
            if not stripped:
                continue
            # 若该行是小标题（≤12字且以标题词开头），跳过
            if any(stripped.startswith(t) for t in stop_titles) and len(stripped) <= 12:
                continue
            lines.append(stripped)
        text = "\n".join(lines)
        # 合并多余空行与首尾空白
        text = re.sub(r"\n{2,}", "\n", text)
        return text.strip()

    # ---------- 海报 HTML ----------
    def render_poster_html(self, events: List[SecurityEvent], assess: str) -> str:
        """生成海报卡片风 HTML（供 PDF 转换与邮件展示）。"""
        esc = html.escape
        date_cn = self._date_cn()

        # 顶部统计徽章
        sectors = {e.sector for e in events}
        stats = (
            f'<div class="badge"><span class="badge-num">{len(events)}</span>条精选</div>'
            f'<div class="badge"><span class="badge-num">{len(sectors)}</span>大类别</div>'
            f'<div class="badge">🤖 AI 摘要</div>'
        )

        # 分组卡片
        grouped = self._group_by_sector(events)
        cards = []
        for sector, items in grouped.items():
            meta = SECTOR_META.get(sector, {"icon": "🔍", "color": "#2c3e50"})
            icon = meta["icon"]
            color = meta["color"]
            label = items[0].sector_label if items else sector
            items_html = []
            for e in items:
                items_html.append(self._poster_item_html(e))
            cards.append(
                f'<div class="sector-block" style="--c:{color}">'
                f'<div class="sector-head" style="background:linear-gradient(120deg,{color},rgba(0,0,0,0))">'
                f'<span class="sector-icon" style="background:rgba(255,255,255,.22)">{icon}</span>'
                f'<span class="sector-title">{esc(label)}</span>'
                f'<span class="sector-count">{len(items)}条</span>'
                f'</div>'
                f'<div class="sector-body">{"".join(items_html)}</div>'
                f'</div>'
            )

        # 研判区块（清理 markdown 残留，统一为干净段落）
        assess_html = esc(self._clean_assess(assess)).replace("\n", "<br/>")

        # 打印时动态把 @page 尺寸设为海报内容实际宽高，使 PDF 输出为一张完整长图（不分页）
        fit_script = """<script>
(function () {
  function fit() {
    var page = document.querySelector('.page');
    var w = page ? Math.ceil(page.offsetWidth) : 780;
    var h = Math.ceil(document.documentElement.scrollHeight);
    var st = document.getElementById('__page_size');
    if (!st) { st = document.createElement('style'); st.id = '__page_size'; document.head.appendChild(st); }
    st.textContent = '@page { size: ' + w + 'px ' + h + 'px; margin: 0; }';
  }
  window.addEventListener('load', fit);
  setTimeout(fit, 120);
  setTimeout(fit, 350);
})();
</script>"""

        return f"""<!DOCTYPE html>
<html lang="zh"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>安防行业日报 · {self._date_str()}</title>
<style>
*{{margin:0;padding:0;box-sizing:border-box}}
body{{font-family:-apple-system,"Segoe UI","Microsoft YaHei","PingFang SC",sans-serif;background:#eef1f6;color:#23262b;line-height:1.7;padding:28px 20px;-webkit-print-color-adjust:exact;print-color-adjust:exact}}
.page{{max-width:780px;margin:0 auto}}

/* 头部 */
.header{{position:relative;overflow:hidden;background:linear-gradient(135deg,#1a2b4a 0%,#274b7c 55%,#3a6ea5 100%);color:#fff;border-radius:20px;padding:34px 36px 30px;margin-bottom:22px;box-shadow:0 8px 28px rgba(26,43,74,.28)}}
.header::before{{content:"";position:absolute;right:-60px;top:-60px;width:220px;height:220px;border-radius:50%;background:rgba(255,255,255,.06)}}
.header::after{{content:"";position:absolute;right:30px;bottom:-80px;width:160px;height:160px;border-radius:50%;background:rgba(255,255,255,.05)}}
.header h1{{font-size:30px;font-weight:800;letter-spacing:2px;display:flex;align-items:center;gap:12px;position:relative;z-index:1}}
.header h1 .logo{{font-size:34px;filter:drop-shadow(0 2px 6px rgba(0,0,0,.3))}}
.header .sub{{margin-top:8px;font-size:14px;opacity:.9;position:relative;z-index:1}}
.stats{{display:flex;gap:10px;margin-top:20px;flex-wrap:wrap;position:relative;z-index:1}}
.badge{{display:flex;align-items:center;gap:5px;background:rgba(255,255,255,.14);border:1px solid rgba(255,255,255,.28);border-radius:22px;padding:5px 16px;font-size:13px;backdrop-filter:blur(4px)}}
.badge-num{{font-size:18px;font-weight:800;color:#ffd75e}}

/* 研判区块 */
.assess{{background:linear-gradient(135deg,#fff 0%,#fdf3f3 100%);border-radius:18px;padding:24px 28px;margin-bottom:22px;box-shadow:0 4px 14px rgba(192,57,43,.08);border:1px solid #f5dedb;border-left:6px solid #c0392b}}
.assess h2{{font-size:16px;color:#c0392b;margin-bottom:12px;display:flex;align-items:center;gap:8px;letter-spacing:1px}}
.assess h2::before{{content:"";width:6px;height:18px;border-radius:3px;background:#c0392b}}
.assess .text{{font-size:13.5px;color:#4a4f57;white-space:pre-wrap;line-height:1.8}}

/* 行业子类分组 */
.sector-block{{background:#fff;border-radius:18px;margin-bottom:20px;overflow:hidden;box-shadow:0 3px 16px rgba(30,45,80,.08);border:1px solid #eef0f4}}
.sector-head{{display:flex;align-items:center;gap:12px;padding:16px 24px;color:#fff}}
.sector-icon{{width:38px;height:38px;border-radius:11px;display:flex;align-items:center;justify-content:center;font-size:20px;flex-shrink:0}}
.sector-title{{font-size:17px;font-weight:700;flex:1;letter-spacing:.5px}}
.sector-count{{font-size:12px;font-weight:600;background:rgba(255,255,255,.22);border-radius:14px;padding:3px 14px}}
.sector-body{{padding:6px 18px}}

/* 单条卡片 */
.item{{padding:16px 6px;border-bottom:1px solid #f1f2f5}}
.item:last-child{{border-bottom:none}}
.item-head{{display:flex;align-items:flex-start;gap:10px;margin-bottom:7px}}
.sev{{font-size:11px;font-weight:700;padding:2px 10px;border-radius:5px;white-space:nowrap;flex-shrink:0;margin-top:1px}}
.sev5{{color:#c0392b;background:#fdecea}}
.sev4{{color:#e67e22;background:#fef3e2}}
.sev3{{color:#d4a017;background:#fdf6e3}}
.sev2{{color:#27ae60;background:#eafaf1}}
.sev1{{color:#95a5a6;background:#f2f3f4}}
.item-title{{font-size:15.5px;font-weight:650;color:#1c1f26;line-height:1.5}}
.item-summary{{font-size:13px;color:#565b64;margin:2px 0;line-height:1.75}}
.item-meta{{display:flex;align-items:center;gap:8px;margin-top:8px;flex-wrap:wrap}}
.tag{{font-size:11px;color:#4e5866;background:#eef1f5;border-radius:4px;padding:2px 9px}}
.src{{font-size:11px;color:#a2abb8;margin-left:auto}}

/* 底部 */
.footer{{text-align:center;color:#a2abb8;font-size:11px;margin-top:28px;line-height:1.9}}
.footer .line{{display:inline-block;width:60px;height:2px;background:#d5dbe4;border-radius:2px;margin-bottom:14px}}

/* 打印：去默认页边距、body 内边距归零，让 PDF 铺满海报画布、背景贯通 */
@page{{margin:0}}
@media print{{body{{padding:0}}}}
</style></head><body>
<div class="page">
  <div class="header">
    <h1><span class="logo">🔍</span>安防行业日报</h1>
    <div class="sub">📅 {date_cn} · 物理安防重点 · 精准精选</div>
    <div class="stats">{stats}</div>
  </div>

  <div class="assess">
    <h2>📊 今日态势研判</h2>
    <div class="text">{assess_html}</div>
  </div>

  {"".join(cards)}

  <div class="footer">
    <span class="line"></span><br>
    🌐 数据来源：{"、".join(sorted({e.source for e in events}))}<br>
    🤖 AI 摘要引擎 · 全文已内嵌 · 内部参考 · {datetime.now().year}
  </div>
</div>
{fit_script}
</body></html>"""

    def _poster_item_html(self, e: SecurityEvent) -> str:
        esc = html.escape
        sev = e.severity
        tags = ""
        for t in e.tags.get("product", [])[:3] + e.tags.get("event", [])[:2]:
            tags += f'<span class="tag">{esc(t)}</span>'
        src = f'<span class="src">来源：{esc(e.source)}</span>'
        return (
            f'<div class="item">'
            f'<div class="item-head">'
            f'<span class="sev sev{sev}">[{esc(e.severity_label)}]</span>'
            f'<span class="item-title">{esc(e.title)}</span>'
            f'</div>'
            f'<div class="item-summary">{esc(e.summary)}</div>'
            f'<div class="item-meta">{tags}{src}</div>'
            f'</div>'
        )

    # ---------- 旧版 HTML（邮件正文，保持简洁） ----------
    def render_html(self, events: List[SecurityEvent], assess: str) -> str:
        return self.render_poster_html(events, assess)

    # ---------- PDF（海报卡片风，经浏览器无头打印） ----------
    def render_pdf(self, events: List[SecurityEvent], assess: str) -> bytes:
        poster_html = self.render_poster_html(events, assess)

        # 写临时 HTML（用绝对路径，避免 Edge 相对路径解析问题）
        tmp_html = (self.output_dir / f"_poster_{self._date_str()}.html").resolve()
        tmp_pdf = (self.output_dir / f"_poster_{self._date_str()}.pdf").resolve()
        tmp_html.write_text(poster_html, encoding="utf-8")

        browser = _find_browser()
        if not browser:
            logger.warning("未找到 Edge/Chrome，回退 reportlab 生成 PDF")
            return self._render_pdf_reportlab(events, assess)

        try:
            cmd = [
                browser,
                "--headless",
                "--disable-gpu",
                "--no-sandbox",
                "--disable-dev-shm-usage",
                "--no-pdf-header-footer",
                "--virtual-time-budget=3000",
                "--print-to-pdf=" + str(tmp_pdf),
                "file:///" + str(tmp_html).replace("\\", "/"),
            ]
            subprocess.run(cmd, timeout=60, check=True, capture_output=True)
            if not tmp_pdf.exists():
                raise FileNotFoundError(f"浏览器未生成 PDF：{tmp_pdf}")
            pdf_bytes = tmp_pdf.read_bytes()
            return pdf_bytes
        except Exception as exc:
            logger.warning("浏览器转 PDF 失败（%s），回退 reportlab", exc)
            return self._render_pdf_reportlab(events, assess)
        finally:
            for f in (tmp_html, tmp_pdf):
                try:
                    f.unlink(missing_ok=True)
                except OSError:
                    pass

    def _render_pdf_reportlab(self, events: List[SecurityEvent], assess: str) -> bytes:
        """reportlab 兜底 PDF（简洁版）。"""
        from io import BytesIO
        from xml.sax.saxutils import escape as _xml_escape

        from reportlab.lib import colors  # pyright: ignore[reportMissingModuleSource]
        from reportlab.lib.pagesizes import A4  # pyright: ignore[reportMissingModuleSource]
        from reportlab.lib.styles import ParagraphStyle  # pyright: ignore[reportMissingModuleSource]
        from reportlab.lib.units import mm  # pyright: ignore[reportMissingModuleSource]
        from reportlab.pdfbase import pdfmetrics  # pyright: ignore[reportMissingModuleSource]
        from reportlab.pdfbase.cidfonts import UnicodeCIDFont  # pyright: ignore[reportMissingModuleSource]
        from reportlab.platypus import HRFlowable, Paragraph, SimpleDocTemplate  # pyright: ignore[reportMissingModuleSource]

        font_name = _register_embedded_cjk_font()
        if not font_name:
            pdfmetrics.registerFont(UnicodeCIDFont("STSong-Light"))
            font_name = "STSong-Light"

        title_style = ParagraphStyle("title", fontName=font_name, fontSize=18, leading=24, spaceAfter=8)
        h2_style = ParagraphStyle("h2", fontName=font_name, fontSize=13, leading=18, spaceBefore=12, spaceAfter=5, textColor=colors.HexColor("#c0392b"))
        body_style = ParagraphStyle("body", fontName=font_name, fontSize=10, leading=16)
        item_style = ParagraphStyle("item", fontName=font_name, fontSize=10, leading=16, leftIndent=10, spaceAfter=3)

        def esc(s):
            return _xml_escape(s or "")

        story = [Paragraph(f"安防行业日报 · {self._date_str()}", title_style),
                 HRFlowable(width="100%", thickness=1, color=colors.HexColor("#333333")),
                 Paragraph("今日态势研判", h2_style),
                 Paragraph(esc(assess).replace("\n", "<br/>"), body_style)]

        grouped = self._group_by_sector(events)
        for sector, items in grouped.items():
            meta = SECTOR_META.get(sector, {"icon": "", "color": "#333"})
            label = items[0].sector_label if items else sector
            story.append(Paragraph(f"{meta['icon']} {esc(label)}（{len(items)} 条）", h2_style))
            for e in items:
                sev_color = SEV_COLORS.get(e.severity, "#000")
                story.append(Paragraph(
                    f'• <font color="{sev_color}">[{esc(e.severity_label)}]</font> {esc(e.title)}<br/>{esc(e.summary)}',
                    item_style,
                ))

        buf = BytesIO()
        doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=20 * mm, rightMargin=20 * mm, topMargin=18 * mm, bottomMargin=18 * mm)
        doc.build(story)  # pyright: ignore[reportArgumentType]
        return buf.getvalue()

    # ---------- 写入文件 ----------
    def write_files(self, events: List[SecurityEvent], assess: str, markdown_text: str = None) -> Dict[str, Path]:  # pyright: ignore[reportArgumentType]
        date_str = self._date_str()
        if markdown_text is None:
            markdown_text = self.render_markdown(events, assess)
        html_text = self.render_html(events, assess)
        payload = {
            "date": date_str,
            "count": len(events),
            "assess": assess,
            "items": [e.to_dict() for e in events],
        }
        md_path = self.output_dir / f"daily_brief_{date_str}.md"
        html_path = self.output_dir / f"daily_brief_{date_str}.html"
        json_path = self.output_dir / f"daily_brief_{date_str}.json"
        md_path.write_text(markdown_text, encoding="utf-8")
        html_path.write_text(html_text, encoding="utf-8")
        json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

        pdf_path = None
        try:
            pdf_path = self.output_dir / f"daily_brief_{date_str}.pdf"
            pdf_path.write_bytes(self.render_pdf(events, assess))
        except Exception as exc:
            logger.warning("PDF 生成失败：%s", exc)
            pdf_path = None

        names = [md_path.name, html_path.name, json_path.name]
        if pdf_path is not None:
            names.append(pdf_path.name)
        logger.info("报告已写入 %s", " / ".join(names))
        return {"markdown": md_path, "html": html_path, "json": json_path, "pdf": pdf_path, "date": date_str}  # pyright: ignore[reportReturnType]
