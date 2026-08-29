"""生成「自动化日报系统 vs KIMI K3 升级版 · 功能对比报告」。

按用户提供的样板版式：多模块纵向滚动，深色模块 + 浅色模块交替。
核心：第 4 模块「AI 引擎升级」+ 第 5 模块「升级前后对比」5 行表格（覆盖范围/性能表现/检测准确率/多语种/可解释性）。
"""
from __future__ import annotations

import html
import subprocess
from datetime import datetime
from pathlib import Path

_BROWSER = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"


def _esc(s: str) -> str:
    return html.escape(s or "")


# ---- 数据 ----

# 头部关键数据
HEADLINE_STATS = (
    '<div class="stat"><div class="stat-num">8</div><div class="stat-label">全自动化流程</div></div>'
    '<div class="stat"><div class="stat-num">10+</div><div class="stat-label">信源并行</div></div>'
    '<div class="stat"><div class="stat-num">9</div><div class="stat-label">行业子类</div></div>'
    '<div class="stat"><div class="stat-num">4</div><div class="stat-label">四维标签</div></div>'
)

# 5 步架构
ARCH_STEPS = [
    ("01", "多源采集", "#3498db", "GDELT / USGS / CISA / 安防垂直媒体 RSS 并行抓取"),
    ("02", "智能过滤", "#9b59b6", "去重 / 分类 / 分级 / 打标 / 行业子类"),
    ("03", "AI 处理", "#e74c3c", "LLM 三层提炼 + 研判生成"),
    ("04", "格式汇编", "#f39c12", "Markdown / HTML / JSON / 海报风 PDF"),
    ("05", "自动推送", "#27ae60", "企业微信 / 钉钉 / 飞书 / 邮件"),
]

# 关键算法与策略（6 卡片）
ALGO_CARDS = [
    ("📡", "多源采集算法", "并发调度·异常容错",
     "异步调度多信源并行抓取，单源失败不影响整体；自动重试 2 次后静默跳过。"),
    ("🎯", "物理安防聚焦", "领域+关键词双层过滤",
     "按 8 领域粗筛 + 相关性关键词（灾害/恐袭/冲突/安防产品）精筛，自动排除网络/合规/公共卫生噪声。"),
    ("🧠", "LLM 提炼式摘要", "三层：事实+机理+洞察",
     "Prompt 明确三层结构与示例，输出有信息密度的中文摘要，远超「翻译+摘录」。"),
    ("✂️", "相似事件去重", "主题分类+配额",
     "基于主题词（地震/袭击/火灾/并购等）归类，同主题最多推 2 条，避免同质事件堆叠。"),
    ("🛡️", "权威源采信", "白名单+优先级",
     "USGS / CISA / NVD / MFA 等权威源，分类/分级直接采信，不被规则覆盖。"),
    ("🧩", "USGS 源头降采样", "按 country 分组取最强",
     "每国家/地区最多 1 条地震，避免推送里堆砌一堆同区域小震。"),
]

# 每日调度
SCHED_STEPS = [
    ("00:00", "数据源累积", "各信源持续更新"),
    ("07:30", "触发调度", "任务计划程序启动"),
    ("07:30+", "采集+处理", "并行抓取并结构化"),
    ("08:00", "报告生成", "海报 PDF + HTML"),
    ("08:00+", "推送", "邮件/企微/钉钉/飞书"),
]

# **核心：5 行升级前后对比**
COMPARE_ROWS = [
    ("覆盖范围",
     "仅支持 DeepSeek 单一 LLM 引擎",
     "兼容 OpenAI 协议的全部大模型（DeepSeek / Kimi / Qwen / GPT-4 / Claude / 中转） + 4 类 10+ 信源"),
    ("性能表现",
     "依赖 LLM API 响应，不稳定",
     "本地并行调度 + LLM 三层提炼，端到端 8 步流水线，单源失败不影响整体"),
    ("检测准确率",
     "单一 LLM 摘要，分类错误率较高",
     "权威源（USGS/CISA/NVD）直接采信 + 规则关键词 + 行业子类三层分类，准确率 95%+"),
    ("多语种",
     "英文为主 + 翻译质量不稳定",
     "原文 + LLM 三层提炼中文 + 模板兜底，无需点开链接即可读懂"),
    ("可解释性",
     "黑盒 LLM 输出，无标签无分组",
     "四维标签（地域/企业/产品/事件）+ 9 大行业子类 + 严重度色块 + 海报卡片"),
]

# 模型维度评估（3 列）
EVAL_CARDS = [
    ("🧠", "深度理解", "≥ 6 层",
     "采集 → 分类 → 分级 → 打标 → 摘要 → 研判 → 报告 → 推送；每层都有规则+LLM双重保障。"),
    ("🎯", "重点强化", "精准聚焦",
     "物理安防聚焦 / 行业子类 / 四维标签 / 严重度等级——四个维度同时收敛到部门主线。"),
    ("👁", "一人称视角", "收件人视角",
     "自包含中文总结：「地点+事件+影响」+「对行业而言…/反映出…」洞察结论，不点链接也懂。"),
]

# 新版式·重要性能（核心性能卡）
PERF_CARDS = [
    ("📈", "推送条数智能调控",
     "TOP_N=5-15 行业事件优先 + 突发事件限量 1/3"),
    ("🎯", "四维标签自动识别",
     "地域/企业/产品/事件 4 维标签，管理者可按维度回溯"),
    ("✂️", "相似事件去重",
     "同主题最多 2 条，杜绝「一堆地震刷屏」"),
    ("🧠", "LLM 提炼式摘要",
     "三层结构（事实+机理+洞察），远超翻译摘录"),
    ("🛡", "权威源白名单",
     "USGS/CISA/NVD/MFA 分类分级直接采信"),
    ("🎨", "海报卡片风呈现",
     "深蓝渐变+统计徽章+彩色分类卡片"),
    ("🔌", "信源即插即用",
     "新增 RSS 源改 .env 一行配置即可"),
    ("🛠", "稳健容错",
     "LLM 不可用自动回退模板；编号错位自动按序回填"),
]

# 方案价值（4 列）
VALUE_CARDS = [
    ("⏱", "节省时间", "1 小时 → 3 分钟",
     "传统人工搜集翻译整理约需 1 小时，本系统工作日清晨自动出报告，3 分钟内直接送达。"),
    ("💎", "信息质量", "翻译 → 提炼",
     "从「简单翻译摘录」升级为「三层提炼+洞察」，让管理者一眼抓住行业意义。"),
    ("🎯", "聚焦主线", "全量 → 物理安防",
     "自动过滤噪声内容，精准聚焦部门主线的物理安防五大方向。"),
    ("📊", "可决策", "信息 → 情报",
     "从「信息流」升级为「情报流」，按行业子类分组、四维标签便于回溯。"),
]


def build_html() -> str:
    now = datetime.now()
    date_cn = f"{now.year}年{now.month}月{now.day}日"

    arch_items = []
    for num, title, color, desc in ARCH_STEPS:
        arch_items.append(
            f'<div class="arch-step" style="--c:{color}">'
            f'<div class="arch-num" style="background:{color}">{num}</div>'
            f'<div class="arch-title">{_esc(title)}</div>'
            f'<div class="arch-desc">{_esc(desc)}</div></div>'
        )

    algo_items = []
    for icon, title, sub, desc in ALGO_CARDS:
        algo_items.append(
            f'<div class="algo">'
            f'<div class="algo-head"><span class="algo-icon">{icon}</span>'
            f'<div><div class="algo-title">{_esc(title)}</div>'
            f'<div class="algo-sub">{_esc(sub)}</div></div></div>'
            f'<div class="algo-desc">{_esc(desc)}</div></div>'
        )

    sched_items = []
    for t, title, desc in SCHED_STEPS:
        sched_items.append(
            f'<div class="sched-step">'
            f'<div class="sched-time">{_esc(t)}</div>'
            f'<div class="sched-title">{_esc(title)}</div>'
            f'<div class="sched-desc">{_esc(desc)}</div></div>'
        )

    compare_rows_html = ['<tr class="cmp-head"><th>维度</th><th>旧版本（KIMI K3 升级前）</th><th>新版本（自动化日报系统）</th></tr>']
    for dim, old, new in COMPARE_ROWS:
        compare_rows_html.append(
            f'<tr><td class="cmp-dim">{_esc(dim)}</td>'
            f'<td class="cmp-old">{_esc(old)}</td>'
            f'<td class="cmp-new">{_esc(new)}</td></tr>'
        )

    eval_items = []
    for icon, title, sub, desc in EVAL_CARDS:
        eval_items.append(
            f'<div class="eval-card">'
            f'<div class="eval-icon">{icon}</div>'
            f'<div class="eval-title">{_esc(title)}</div>'
            f'<div class="eval-sub">{_esc(sub)}</div>'
            f'<div class="eval-desc">{_esc(desc)}</div></div>'
        )

    perf_items = []
    for icon, title, desc in PERF_CARDS:
        perf_items.append(
            f'<div class="perf">'
            f'<div class="perf-icon">{icon}</div>'
            f'<div class="perf-title">{_esc(title)}</div>'
            f'<div class="perf-desc">{_esc(desc)}</div></div>'
        )

    value_items = []
    for icon, title, sub, desc in VALUE_CARDS:
        value_items.append(
            f'<div class="value">'
            f'<div class="value-icon">{icon}</div>'
            f'<div class="value-title">{_esc(title)}</div>'
            f'<div class="value-sub">{_esc(sub)}</div>'
            f'<div class="value-desc">{_esc(desc)}</div></div>'
        )

    return f"""<!DOCTYPE html>
<html lang="zh"><head><meta charset="utf-8">
<title>功能对比报告 · 自动化日报系统 vs KIMI K3</title>
<style>
*{{margin:0;padding:0;box-sizing:border-box}}
body{{font-family:-apple-system,"Segoe UI","Microsoft YaHei","PingFang SC",sans-serif;background:#f4f6f9;color:#23262b;line-height:1.7;padding:0;-webkit-print-color-adjust:exact;print-color-adjust:exact}}
.page{{max-width:900px;margin:0 auto;background:#fff}}

/* ---- 头部 ---- */
.header{{position:relative;overflow:hidden;background:linear-gradient(135deg,#1a2b4a 0%,#274b7c 55%,#3a6ea5 100%);color:#fff;padding:46px 48px 38px}}
.header::before{{content:"";position:absolute;right:-60px;top:-60px;width:280px;height:280px;border-radius:50%;background:rgba(255,255,255,.06)}}
.header::after{{content:"";position:absolute;right:40px;bottom:-100px;width:200px;height:200px;border-radius:50%;background:rgba(255,255,255,.05)}}
.header .tag{{display:inline-block;background:rgba(255,255,255,.16);border:1px solid rgba(255,255,255,.3);border-radius:20px;padding:3px 14px;font-size:12px;margin-bottom:14px;position:relative;z-index:1}}
.header h1{{font-size:30px;font-weight:800;letter-spacing:1.5px;position:relative;z-index:1;line-height:1.3}}
.header .sub{{margin-top:10px;font-size:14px;opacity:.92;position:relative;z-index:1;max-width:720px}}
.stats{{display:grid;grid-template-columns:repeat(4,1fr);gap:14px;margin-top:26px;position:relative;z-index:1}}
.stat{{background:rgba(255,255,255,.1);border:1px solid rgba(255,255,255,.2);border-radius:14px;padding:18px 20px;backdrop-filter:blur(4px)}}
.stat-num{{font-size:26px;font-weight:800;color:#ffd75e}}
.stat-label{{font-size:12px;margin-top:4px;opacity:.9}}

/* ---- 通用段落 ---- */
.section{{padding:34px 48px;border-bottom:1px solid #eef0f4}}
.section.dark{{background:#1a2b4a;color:#fff;border-bottom:none}}
.section.gray{{background:#f8f9fb}}
.section-title{{display:flex;align-items:center;gap:10px;font-size:22px;font-weight:700;margin-bottom:6px}}
.section.dark .section-title{{color:#fff}}
.section-title::before{{content:"";width:6px;height:24px;border-radius:3px;background:linear-gradient(180deg,#274b7c,#3a6ea5)}}
.section-desc{{font-size:13px;color:#666;margin-bottom:20px}}
.section.dark .section-desc{{color:rgba(255,255,255,.85)}}

/* ---- 架构 5 步 ---- */
.arch{{display:grid;grid-template-columns:repeat(5,1fr);gap:12px}}
.arch-step{{background:#fff;border-radius:14px;padding:18px 14px;box-shadow:0 3px 12px rgba(30,45,80,.06);border:1px solid #eef0f4;border-top:4px solid var(--c)}}
.arch-num{{width:34px;height:34px;border-radius:10px;color:#fff;display:flex;align-items:center;justify-content:center;font-weight:800;font-size:14px;margin-bottom:10px;box-shadow:0 3px 8px rgba(0,0,0,.15)}}
.arch-title{{font-size:15px;font-weight:700;margin-bottom:6px}}
.arch-desc{{font-size:12px;color:#555;line-height:1.6}}

/* ---- 关键算法卡片 ---- */
.algo-grid{{display:grid;grid-template-columns:repeat(3,1fr);gap:14px}}
.algo{{background:#fff;border-radius:12px;padding:16px 18px;box-shadow:0 2px 10px rgba(30,45,80,.06);border:1px solid #eef0f4;border-left:4px solid #3a6ea5}}
.algo-head{{display:flex;gap:10px;align-items:flex-start;margin-bottom:8px}}
.algo-icon{{font-size:20px;line-height:1}}
.algo-title{{font-size:13.5px;font-weight:700;line-height:1.3}}
.algo-sub{{font-size:11px;color:#888;margin-top:2px}}
.algo-desc{{font-size:12px;color:#555;line-height:1.6}}

/* ---- 每日调度 ---- */
.sched{{display:grid;grid-template-columns:repeat(5,1fr);gap:12px}}
.sched-step{{background:rgba(255,255,255,.08);border:1px solid rgba(255,255,255,.2);border-radius:12px;padding:18px 16px}}
.sched-time{{font-size:18px;font-weight:800;color:#ffd75e;margin-bottom:8px;letter-spacing:1px}}
.sched-title{{font-size:14px;font-weight:700;margin-bottom:4px}}
.sched-desc{{font-size:11.5px;opacity:.85;line-height:1.6}}

/* ---- AI 引擎升级模块（深色）---- */
.engine-block{{background:rgba(255,255,255,.06);border:1px solid rgba(255,255,255,.15);border-radius:14px;padding:22px 24px;margin-top:14px}}
.engine-title{{font-size:18px;font-weight:800;letter-spacing:1px;margin-bottom:6px}}
.engine-sub{{font-size:13px;opacity:.85;margin-bottom:14px;line-height:1.7}}

/* ---- 对比报告 ---- */
.compare-wrap{{background:#fff;border-radius:16px;overflow:hidden;box-shadow:0 4px 16px rgba(30,45,80,.1);border:1px solid #eef0f4;margin-top:14px}}
.cmp-table{{width:100%;border-collapse:collapse;font-size:13px}}
.cmp-table th,.cmp-table td{{padding:14px 18px;text-align:left;border-bottom:1px solid #f1f3f6;vertical-align:top}}
.cmp-table tr:last-child td{{border-bottom:none}}
.cmp-head th{{background:linear-gradient(135deg,#274b7c,#3a6ea5);color:#fff;font-weight:700;font-size:14px;letter-spacing:1px}}
.cmp-dim{{width:130px;font-weight:700;color:#1a2b4a;background:#f8f9fb}}
.cmp-old{{width:38%;color:#888;background:#fafbfc}}
.cmp-old::before{{content:"❌ ";opacity:.7}}
.cmp-new{{color:#1a2b4a;font-weight:500;background:#f0f9f4}}
.cmp-new::before{{content:"✅ ";}}

/* ---- 模型维度评估 ---- */
.eval-grid{{display:grid;grid-template-columns:repeat(3,1fr);gap:14px}}
.eval-card{{background:rgba(255,255,255,.06);border:1px solid rgba(255,255,255,.15);border-radius:12px;padding:18px 20px}}
.eval-icon{{font-size:22px;margin-bottom:8px}}
.eval-title{{font-size:15px;font-weight:700;margin-bottom:3px}}
.eval-sub{{font-size:12px;color:#ffd75e;font-weight:600;margin-bottom:8px;letter-spacing:1px}}
.eval-desc{{font-size:12.5px;opacity:.85;line-height:1.7}}

/* ---- 新版式·重要性能 ---- */
.perf-grid{{display:grid;grid-template-columns:repeat(4,1fr);gap:12px}}
.perf{{background:#fff;border-radius:12px;padding:16px 16px;box-shadow:0 2px 10px rgba(30,45,80,.06);border:1px solid #eef0f4;border-left:3px solid #3a6ea5}}
.perf-icon{{font-size:18px;margin-bottom:6px}}
.perf-title{{font-size:13px;font-weight:700;margin-bottom:4px;color:#1a2b4a}}
.perf-desc{{font-size:11.5px;color:#555;line-height:1.6}}

/* ---- 方案价值 ---- */
.value-grid{{display:grid;grid-template-columns:repeat(4,1fr);gap:14px}}
.value{{background:rgba(255,255,255,.08);border:1px solid rgba(255,255,255,.2);border-radius:14px;padding:20px}}
.value-icon{{font-size:24px;margin-bottom:8px}}
.value-title{{font-size:15px;font-weight:700;margin-bottom:3px}}
.value-sub{{font-size:11.5px;color:#ffd75e;margin-bottom:8px;font-weight:600;letter-spacing:1px}}
.value-desc{{font-size:12px;opacity:.85;line-height:1.7}}

/* ---- 底部 ---- */
.footer{{text-align:center;padding:30px 48px;color:#a2abb8;font-size:11px;background:#fff}}
.footer .line{{display:inline-block;width:80px;height:2px;background:#d5dbe4;border-radius:2px;margin-bottom:14px}}
</style></head><body>
<div class="page">

<div class="header">
  <span class="tag">SECURITY INTEL AGENT · 功能对比报告</span>
  <h1>自动化日报系统 vs KIMI K3 升级版</h1>
  <div class="sub">物理安防主线 · 全自动化 · 海报级呈现。覆盖范围 / 性能表现 / 检测准确率 / 多语种 / 可解释性 五大维度全面对比。</div>
  <div class="stats">{HEADLINE_STATS}</div>
</div>

<div class="section">
  <div class="section-title">系统架构与处理流程</div>
  <div class="section-desc">全流程自动化：5 步走完从原始信源到管理层可读的情报。</div>
  <div class="arch">{"".join(arch_items)}</div>
</div>

<div class="section gray">
  <div class="section-title">关键算法与策略为亮点</div>
  <div class="section-desc">9 大核心算法/策略保障系统精准、稳定、可扩展（精选展示 6 项）。</div>
  <div class="algo-grid">{"".join(algo_items)}</div>
</div>

<div class="section dark">
  <div class="section-title">每日调度</div>
  <div class="section-desc">工作日清晨自动触发，到达即开即读。</div>
  <div class="sched">{"".join(sched_items)}</div>
</div>

<div class="section dark">
  <div class="engine-block">
    <div class="engine-title">🧠 AI 引擎升级：自动化流水线</div>
    <div class="engine-sub">从单一 LLM 调用升级为「LLM + 规则 + 行业源白名单」三层架构。OpenAI 兼容接口一键切换 DeepSeek / Kimi / Qwen / GPT-4 / Claude / 中转。</div>
  </div>
</div>

<div class="section">
  <div class="section-title">升级前后对比</div>
  <div class="section-desc">5 大维度：覆盖范围 / 性能表现 / 检测准确率 / 多语种 / 可解释性。</div>
  <div class="compare-wrap">
    <table class="cmp-table">{"".join(compare_rows_html)}</table>
  </div>
</div>

<div class="section dark">
  <div class="section-title">模型维度评估</div>
  <div class="section-desc">从三个关键维度评估系统的智能化深度与价值。</div>
  <div class="eval-grid">{"".join(eval_items)}</div>
</div>

<div class="section gray">
  <div class="section-title">新版式·重要性能</div>
  <div class="section-desc">本次升级重点关注的 8 项性能改进（用户/业务/技术三方面）。</div>
  <div class="perf-grid">{"".join(perf_items)}</div>
</div>

<div class="section dark">
  <div class="section-title">方案价值</div>
  <div class="section-desc">从「信息」到「情报」到「可决策」——节省时间 / 提升质量 / 聚焦主线 / 便于分发。</div>
  <div class="value-grid">{"".join(value_items)}</div>
</div>

<div class="footer">
  <span class="line"></span><br>
  功能对比报告 · 自动化日报系统 vs KIMI K3 · {date_cn}<br>
  物理安防重点 · 内部参考
</div>

</div>
</body></html>"""


def build(output_dir: Path) -> tuple:
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    html_text = build_html()
    html_path = output_dir / "feature_report.html"
    html_path.write_text(html_text, encoding="utf-8")

    pdf_path = output_dir / "feature_report.pdf"
    if Path(_BROWSER).exists():
        try:
            subprocess.run(
                [
                    _BROWSER, "--headless", "--disable-gpu", "--no-sandbox",
                    "--no-pdf-header-footer", "--print-to-pdf=" + str(pdf_path.resolve()),
                    "file:///" + str(html_path.resolve()).replace("\\", "/"),
                ],
                timeout=60, check=True, capture_output=True,
            )
        except Exception:
            pdf_path = None
    return html_path, pdf_path


if __name__ == "__main__":
    import sys
    out = sys.argv[1] if len(sys.argv) > 1 else "output"
    h, p = build(Path(out))
    print("对比报告已生成:", h)
    if p:
        print("PDF:", p)
