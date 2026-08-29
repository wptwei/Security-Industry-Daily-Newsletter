"""生成 Word 报告：①自动化流程工作思维 ②与 Claude+K3 的对比报告。

用 python-docx 生成 .docx，含标题、表格、样式。
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml.ns import qn
from docx.shared import Pt, RGBColor, Cm

# 主题色
DARK = RGBColor(0x1A, 0x2B, 0x4A)
BLUE = RGBColor(0x27, 0x4B, 0x7C)
GRAY = RGBColor(0x66, 0x66, 0x66)
RED = RGBColor(0xC0, 0x39, 0x2B)
GREEN = RGBColor(0x27, 0xAE, 0x60)


def _set_cn_font(run, size=None, bold=False, color=None):
    run.font.name = "微软雅黑"
    run._element.rPr.rFonts.set(qn("w:eastAsia"), "微软雅黑")
    if size:
        run.font.size = Pt(size)
    run.font.bold = bold
    if color:
        run.font.color.rgb = color


def _add_heading(doc, text, level=1, color=DARK):
    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(14 if level == 1 else 10)
    p.paragraph_format.space_after = Pt(8)
    run = p.add_run(text)
    _set_cn_font(run, size=20 if level == 1 else 15, bold=True, color=color)
    return p


def _add_body(doc, text, size=11, color=None, indent=False):
    p = doc.add_paragraph()
    p.paragraph_format.space_after = Pt(6)
    if indent:
        p.paragraph_format.left_indent = Cm(0.5)
    run = p.add_run(text)
    _set_cn_font(run, size=size, color=color)
    return p


def _add_title(doc, title, subtitle):
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.paragraph_format.space_after = Pt(4)
    run = p.add_run(title)
    _set_cn_font(run, size=22, bold=True, color=DARK)
    p2 = doc.add_paragraph()
    p2.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p2.paragraph_format.space_after = Pt(16)
    run2 = p2.add_run(subtitle)
    _set_cn_font(run2, size=12, color=GRAY)


def _style_table(doc, table, header_color=BLUE):
    table.style = "Table Grid"
    for row in table.rows:
        for cell in row.cells:
            for para in cell.paragraphs:
                for run in para.runs:
                    _set_cn_font(run, size=10.5)
    # 表头
    for cell in table.rows[0].cells:
        for para in cell.paragraphs:
            for run in para.runs:
                run.font.bold = True
                run.font.color.rgb = RGBColor(0xFF, 0xFF, 0xFF)
        shd = cell._element.get_or_add_tcPr()
        from docx.oxml import OxmlElement
        bg = OxmlElement("w:shd")
        bg.set(qn("w:fill"), "274B7C")
        shd.append(bg)


# ============================================================
# 文档一：自动化流程工作思维
# ============================================================
def build_workflow_doc() -> Document:
    doc = Document()
    now = datetime.now()
    date_cn = f"{now.year}年{now.month}月{now.day}日"

    _add_title(doc, "安防情报自动化流程 · 工作思维", "CodeBuddy + DeepSeek 版 · 物理安防主线")

    _add_heading(doc, "一、核心定位")
    _add_body(doc, "本流程以「物理安防」为部门主线，每个工作日清晨自动从全球公开信源采集安防情报，"
                  "完成「采集 → 过滤 → 分类分级 → 打标 → 去重 → 提炼摘要 → 研判 → 海报生成 → 多渠道推送」"
                  "全链路自动化，最终产出管理层可读、可直接转发的海报级日报。")

    _add_heading(doc, "二、整体架构（8 步流水线）")
    steps = [
        ("① 多源采集", "GDELT / USGS / CISA / 安防垂直媒体 RSS 并行抓取，单源失败自动重试并静默跳过。"),
        ("② 跨天去重", "按 uid 记录最近出现日期，N 天（默认 7）窗口内不重复上报。"),
        ("③ 分类分级", "8 大领域分类 + 5 级严重度（紧急/高/中/低/提示），权威源直接采信。"),
        ("④ 四维打标", "规则关键词识别「地域 / 企业 / 产品 / 事件」四维标签。"),
        ("⑤ 行业子类", "归入 9 大行业子类（物理安防/安防硬件/周界防护/AI安防/智能安防/峰会/动态/机器人无人机/突发事件）。"),
        ("⑥ 精准精选", "行业事件优先 + 突发事件限量（≤1/3）+ 相似事件去重（同主题 ≤2 条）+ USGS 每国家 1 条。"),
        ("⑦ 提炼摘要", "LLM 三层提炼（事实+机理+洞察）+ 规则模板兜底；编号错位自动按序回填。"),
        ("⑧ 海报呈现与推送", "HTML/CSS + Edge 无头打印成海报风 PDF，邮件/企微/钉钉/飞书多渠道推送。"),
    ]
    for t, d in steps:
        _add_body(doc, f"{t}：{d}", indent=True)

    _add_heading(doc, "三、关键算法与策略（9 项）")
    algos = [
        ("多源采集算法", "并发调度 + 异常容错，异步并行抓取，单源失败不影响整体。"),
        ("物理安防聚焦算法", "领域 + 关键词双层过滤，自动排除网络/合规/公共卫生噪声。"),
        ("LLM 提炼式摘要", "三层结构（事实+机理+洞察），远超「翻译+摘录」。"),
        ("相似事件去重", "基于主题词（地震/袭击/火灾/并购等）归类，同主题最多 2 条。"),
        ("权威源采信", "USGS/CISA/NVD/MFA 白名单，分类分级不被规则覆盖。"),
        ("USGS 源头降采样", "按 country 分组取最强，每国家/地区最多 1 条。"),
        ("海报渲染算法", "HTML/CSS + 浏览器无头打印，reportlab 兜底。"),
        ("去重调度算法", "本地 JSON + N 天窗口，跨天不重复。"),
        ("误判纠正算法", "行业源识别避免误判突发事件；LLM 编号错位按序对齐回填。"),
    ]
    for name, desc in algos:
        _add_body(doc, f"· {name}：{desc}", indent=True)

    _add_heading(doc, "四、每日调度节奏")
    sched = [
        ("00:00", "数据源累积"),
        ("07:30", "任务计划程序触发（工作日）"),
        ("07:30+", "并行采集 + 结构化处理"),
        ("08:00", "海报 PDF + HTML 报告生成"),
        ("08:00+", "邮件/企微/钉钉/飞书推送"),
    ]
    table = doc.add_table(rows=len(sched) + 1, cols=2)
    table.rows[0].cells[0].text = "时间"
    table.rows[0].cells[1].text = "动作"
    for i, (t, a) in enumerate(sched, start=1):
        table.rows[i].cells[0].text = t
        table.rows[i].cells[1].text = a
    _style_table(doc, table)

    _add_heading(doc, "五、工作思维核心要点")
    points = [
        "聚焦主线：从「全量信息」收敛到「物理安防」五大方向，精准服务于部门重点。",
        "精准而非堆量：每日 5-15 条，相似事件去重，杜绝无效信息刷屏。",
        "提炼而非摘录：LLM 三层提炼，点明「对行业而言/反映出/这意味着」的洞察结论。",
        "自包含可读：收件人不点链接、不翻墙也能看懂每条情报要点。",
        "容错优先：LLM 不可用回退模板、单源失败静默跳过、编号错位自动纠正，系统永不因单点故障停摆。",
        "即插即用：新增信源改 .env 一行配置，换 LLM 供应商零代码改动。",
    ]
    for p in points:
        _add_body(doc, f"• {p}", indent=True)

    _add_heading(doc, "六、产出物")
    outputs = [
        "daily_brief_YYYY-MM-DD.md —— Markdown 简报",
        "daily_brief_YYYY-MM-DD.html —— 邮件正文（海报同款样式）",
        "daily_brief_YYYY-MM-DD.pdf —— 海报卡片风 PDF",
        "daily_brief_YYYY-MM-DD.json —— 结构化归档",
        "history.json —— 跨天去重历史",
    ]
    for o in outputs:
        _add_body(doc, f"· {o}", indent=True)

    # 页脚
    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(20)
    run = p.add_run(f"—— 文档生成于 {date_cn} · 内部参考 ——")
    _set_cn_font(run, size=9, color=GRAY)
    return doc


# ============================================================
# 文档二：单独对比报告（Claude+K3 vs CodeBuddy+DeepSeek）
# ============================================================
def build_compare_doc() -> Document:
    doc = Document()
    now = datetime.now()
    date_cn = f"{now.year}年{now.month}月{now.day}日"

    _add_title(doc, "安防行业日报 · 方案对比报告", "Claude + K3 版  vs  CodeBuddy + DeepSeek 版")

    _add_heading(doc, "一、对比背景")
    _add_body(doc, "两份安防行业日报分别由不同 AI 技术栈实现：\n"
                  "· 参考方案：Claude + K3（AI 引擎升级：KIMI K3），信源依赖 Google News、SecurityWeek、"
                  "IFSEC Global、Security.World、SIA 等全球 30+ 安防垂直媒体。\n"
                  "· 本方案：CodeBuddy + DeepSeek 4 Pro，信源覆盖 GDELT、USGS、CISA 及安防垂直媒体 RSS。")

    _add_heading(doc, "二、核心差异对比")
    rows = [
        ("对比维度", "Claude + K3 版", "CodeBuddy + DeepSeek 版"),
        ("AI 引擎", "Claude + KIMI K3", "CodeBuddy + DeepSeek 4 Pro"),
        ("信源规模", "30+ 全球安防垂直媒体", "10+ 信源（GDELT/USGS/CISA + 安防 RSS）"),
        ("每日条数", "10 条精选", "5-15 条（可配，默认 8）"),
        ("类别体系", "4 大类别", "9 大行业子类 + 8 大领域 + 5 级严重度"),
        ("标签体系", "双标签（行业子类 + 细分产品）", "四维标签（地域/企业/产品/事件）"),
        ("摘要方式", "事实 + 机理 + 洞察（三层提炼）", "事实 + 机理 + 洞察（三层提炼 + 模板兜底）"),
        ("去重策略", "未明确（可能依赖 LLM 判断）", "规则去重：跨天 + 相似主题 ≤2 + USGS 每国 1 条"),
        ("聚焦能力", "物理安防为重点（7/10 条）", "自动过滤非物理安防类（聚焦 5 大方向）"),
        ("呈现形式", "卡片式日报（PDF）", "海报卡片风 PDF + 邮件 HTML 同款 + Markdown/JSON"),
        ("推送渠道", "未明确", "邮件 + 企业微信/钉钉/飞书（按需）"),
        ("链接处理", "含原文来源（可点击）", "纯文本来源（移除外链，外部可安全转发）"),
        ("容错能力", "依赖单一 LLM", "LLM 失败回退模板 + 单源失败静默跳过"),
    ]
    table = doc.add_table(rows=len(rows), cols=3)
    for i, (a, b, c) in enumerate(rows):
        table.rows[i].cells[0].text = a
        table.rows[i].cells[1].text = b
        table.rows[i].cells[2].text = c
    _style_table(doc, table)

    _add_heading(doc, "三、五大维度功能对比（对标样板）")
    dims = [
        ("覆盖范围", "仅覆盖全球安防垂直媒体（30+）", "通用信源 + 安防垂直媒体，另含 GDELT 全球事件、USGS 地震、CISA 漏洞"),
        ("性能表现", "依赖 Claude + K3 单一 LLM 链路", "本地 8 步流水线 + LLM 三层提炼 + 规则并行，单源/单点失败不影响整体"),
        ("检测准确率", "依赖 LLM 分类与摘要，无权威源采信", "权威源（USGS/CISA）直接采信 + 规则关键词 + 行业子类三层校验"),
        ("多语种", "LLM 翻译成中文", "原文 + LLM 三层提炼中文 + 模板兜底，自包含可读"),
        ("可解释性", "双标签（行业子类 + 产品）", "四维标签 + 9 行业子类 + 严重度色块 + 海报卡片，可回溯"),
    ]
    t2 = doc.add_table(rows=len(dims) + 1, cols=3)
    t2.rows[0].cells[0].text = "维度"
    t2.rows[0].cells[1].text = "Claude + K3 版"
    t2.rows[0].cells[2].text = "CodeBuddy + DeepSeek 版"
    for i, (a, b, c) in enumerate(dims, start=1):
        t2.rows[i].cells[0].text = a
        t2.rows[i].cells[1].text = b
        t2.rows[i].cells[2].text = c
    _style_table(doc, t2)

    _add_heading(doc, "四、本方案（CodeBuddy + DeepSeek）的优势")
    adv = [
        "自动化程度更高：8 步全流水线自动执行，无人值守定时推送。",
        "聚焦更精准：自动过滤非物理安防类噪声，专注部门主线 5 大方向。",
        "去重更智能：跨天去重 + 相似主题 ≤2 + USGS 源头降采样三层防护。",
        "容错更稳健：LLM 不可用回退模板、编号错位自动纠正、单源失败静默跳过。",
        "分发更安全：移除所有外链，纯文本来源展示，发给外部无「链接打不开」问题。",
        "扩展更便捷：新增信源改 .env 一行配置，换 LLM 供应商零代码改动。",
        "呈现更丰富：海报 PDF + 邮件 HTML + Markdown + JSON 四格式同源。",
    ]
    for a in adv:
        _add_body(doc, f"• {a}", indent=True)

    _add_heading(doc, "五、参考方案（Claude + K3）的可借鉴之处")
    borrow = [
        "信源更丰富：30+ 全球安防垂直媒体（SecurityWeek/IFSEC/SIA 等），可补充本方案信源池。",
        "摘要洞察深度：三层提炼写法的「行业意义/趋势判断」表达更自然，可作为 prompt 优化的参照。",
        "类别命名：行业子类 + 细分产品的双标签体系，可与本方案四维标签融合互补。",
    ]
    for b in borrow:
        _add_body(doc, f"• {b}", indent=True)

    _add_heading(doc, "六、结论")
    _add_body(doc, "两份方案殊途同归，均聚焦「物理安防」主线、均采用「三层提炼式摘要」、均以卡片式日报呈现。"
                  "核心差异在于：Claude + K3 版强调信源广度与摘要洞察深度；CodeBuddy + DeepSeek 版强调"
                  "全流程自动化、精准聚焦、智能去重、容错与安全分发。两方案可融合——以本方案的自动化流水线为骨架，"
                  "吸纳参考方案的 30+ 信源池与洞察式 prompt，形成更强的安防情报日报系统。")

    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(20)
    run = p.add_run(f"—— 文档生成于 {date_cn} · 内部参考 ——")
    _set_cn_font(run, size=9, color=GRAY)
    return doc


def build_key_compare_doc() -> Document:
    """精炼的重点对比分析：突出优势与不同。"""
    doc = Document()
    now = datetime.now()
    date_cn = f"{now.year}年{now.month}月{now.day}日"

    _add_title(doc, "安防行业日报 · 重点对比分析", "Claude + K3 版  vs  CodeBuddy + DeepSeek 版")

    _add_heading(doc, "一、一句话结论")
    _add_body(doc, "两者殊途同归——都聚焦「物理安防」、都用「三层提炼式摘要」、都做「卡片式日报」。"
                  "但本质是「编辑思维」与「工程化产品」的差异：\n"
                  "· Claude + K3 版胜在【信源广度】与【摘要洞察深度】；\n"
                  "· CodeBuddy + DeepSeek 版胜在【全流程自动化】【精准聚焦】【智能去重】【容错】【安全分发】。")

    _add_heading(doc, "二、核心差异 Top 5（挑重点）")
    rows = [
        ("维度", "Claude + K3 版", "CodeBuddy + DeepSeek 版", "占优"),
        ("信源规模", "30+ 全球安防垂直媒体", "11 个信源（GDELT/USGS/CISA + 8 RSS）", "K3 版"),
        ("自动化程度", "半自动（人工编排 + Claude 生成）", "全自动 8 步流水线 + 定时无人值守", "本方案"),
        ("精准聚焦", "人工筛选物理安防主题", "规则自动过滤非物理安防 + 相似去重 + 每国 1 条", "本方案"),
        ("容错能力", "单一 LLM 链路，失败即停", "LLM 失败回退模板 + 单源失败静默跳过", "本方案"),
        ("分发安全", "含原文外链", "移除外链，纯文本来源，外部可安全转发", "本方案"),
    ]
    table = doc.add_table(rows=len(rows), cols=4)
    for i, (a, b, c, d) in enumerate(rows):
        table.rows[i].cells[0].text = a
        table.rows[i].cells[1].text = b
        table.rows[i].cells[2].text = c
        table.rows[i].cells[3].text = d
    _style_table(doc, table)

    _add_heading(doc, "三、本方案（CodeBuddy + DeepSeek）独有优势")
    advs = [
        "全流程自动化：采集→过滤→分类→打标→去重→摘要→研判→海报→推送，8 步无人值守定时执行。",
        "智能三层去重：跨天去重 + 相似主题≤2 条 + USGS 每国 1 条，杜绝无效信息刷屏。",
        "四维标签：地域/企业/产品/事件，比「双标签」更细粒度，便于回溯。",
        "权威源采信：USGS/CISA/NVD 分类分级直接采信，不被规则覆盖。",
        "多格式呈现：PDF 海报 + 邮件 HTML + Markdown + JSON 四格式同源。",
        "即插即用：换 LLM 供应商、新增信源，均改 .env 配置零代码改动。",
    ]
    for a in advs:
        _add_body(doc, f"• {a}", indent=True)

    _add_heading(doc, "四、参考方案（Claude + K3）独有优势（可借鉴）")
    borrows = [
        "信源广度：30+ 全球安防垂直媒体，覆盖更全（SecurityWeek/IFSEC/Security.World/SIA 等）。",
        "摘要洞察深度：「预算逻辑从成本中心转向业务赋能」这类行业判断表达更自然。",
        "双标签体系：行业子类 + 细分产品，可与四维标签融合互补。",
    ]
    for b in borrows:
        _add_body(doc, f"• {b}", indent=True)

    _add_heading(doc, "五、融合建议（结论）")
    _add_body(doc, "以 CodeBuddy + DeepSeek 的「自动化流水线」为骨架，吸纳 Claude + K3 的「30+ 信源池」与"
                  "「洞察式 prompt 写法」，即可形成「信源广 + 自动化 + 精准 + 容错」的最优安防情报日报系统。")

    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(20)
    run = p.add_run(f"—— 文档生成于 {date_cn} · 内部参考 ——")
    _set_cn_font(run, size=9, color=GRAY)
    return doc


def build_all(output_dir: Path) -> tuple:
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    w1 = output_dir / "安防自动化流程_工作思维.docx"
    build_workflow_doc().save(str(w1))

    w2 = output_dir / "安防日报_方案对比报告.docx"
    build_compare_doc().save(str(w2))

    w3 = output_dir / "安防日报_重点对比分析.docx"
    build_key_compare_doc().save(str(w3))

    return w1, w2, w3


if __name__ == "__main__":
    import sys
    out = sys.argv[1] if len(sys.argv) > 1 else "output"
    results = build_all(Path(out))
    print("已生成:")
    for r in results:
        print(" ", r)
    print("已生成:")
    print(" ", a)
    print(" ", b)
