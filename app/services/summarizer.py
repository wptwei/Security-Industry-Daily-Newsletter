"""LLM 中文摘要 + 今日研判（OpenAI 兼容接口，可选，失败回退模板）。"""
from __future__ import annotations

import re
from typing import List, Optional

from app.models.event import SecurityEvent
from app.utils.logging import get_logger

logger = get_logger("summarizer")

SUMMARY_SYSTEM = (
    "你是全球物理安防行业资深分析师。请为下列每条情报生成「中文标题 + 提炼式中文摘要」"
    "两部分，而非简单翻译或摘录原文。每条情报已标注严重度（紧急/高/中/低/提示），"
    "请根据严重度调整摘要的侧重点与语气。\n"
    "【标题】一句话点出核心事件，简洁明了、≤20 字，让人一眼抓住重点（如「Axis 推出"
    "一体化车牌识别摄像机套件」「巴基斯坦医院火灾致 14 名婴儿死亡」）。\n"
    "【摘要侧重点 · 按严重度分级】\n"
    "· 紧急/高：突出人员伤亡、财产损失、影响范围与紧迫性，并点明应急应对或行动建议；"
    "语气严肃，结论前置。字数可适当放宽至 120-180 字，交代更充分。\n"
    "· 中：平衡交代事件本身、直接影响与行业意义，控制在 80-120 字。\n"
    "· 低/提示：弱化伤亡与灾难性，侧重产品/技术特点、行业动态、趋势与价值；语气从容客观，"
    "控制在 60-100 字，简洁精炼。\n"
    "【摘要通用结构】\n"
    "① 事实：谁、做了什么；\n"
    "② 机理/影响：该产品/方案/事件如何运作或带来什么具体影响；\n"
    "③ 洞察：对安防行业的意义、趋势或影响（如「这意味着…」「反映出…」「该动向指向…」）。\n"
    "要求：标题与摘要都要精炼、信息密度高；不要罗列无意义细节。"
    "严格按编号逐行输出，格式：`编号. 标题｜摘要`（标题与摘要之间用全角竖线「｜」分隔），"
    "编号必须与输入一致（从 0 开始），每条都须输出、不得遗漏，"
    "不要输出其他内容，不要加引号。"
)
ASSESS_SYSTEM = (
    "你是企业物理安防首席分析师，向管理层汇报当日全球物理安防态势。请基于下方情报，"
    "输出一段简短的中文研判，控制在 2-3 句话内（总字数 ≤80 字）：概括今日最重要的 1-2 个态势要点，"
    "并用一句话点明需管理层关注的方向。语言精炼、直白、无空话。"
    "只输出研判正文本身，不要使用「一、二、三」序号、不要加粗、不要换行、不要小标题。"
)


class Summarizer:
    def __init__(self, enabled: bool, api_base: str, api_key: str, model: str, timeout: int = 60) -> None:
        self.enabled = enabled and bool(api_key and api_key.strip())
        self.api_base = api_base
        self.api_key = api_key
        self.model = model
        self.timeout = timeout
        self._client = None
        if self.enabled:
            try:
                from openai import OpenAI

                self._client = OpenAI(api_key=api_key, base_url=api_base, timeout=timeout)
            except Exception as exc:
                logger.warning("初始化 LLM 客户端失败（%s），将回退模板摘要", exc)
                self._client = None
                self.enabled = False

    def _chat(self, system: str, user: str) -> Optional[str]:
        if not self._client:
            return None
        try:
            resp = self._client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                temperature=0.3,
            )
            return (resp.choices[0].message.content or "").strip()
        except Exception as exc:
            logger.warning("LLM 调用失败（%s），将回退模板摘要", exc)
            return None

    def summarize_events(self, events: List[SecurityEvent]) -> List[SecurityEvent]:
        """批量把事件原文压缩成中文摘要（一次调用），原地更新 summary。

        LLM 未启用或调用失败时，逐条用规则模板生成自包含中文总结，
        确保收件人不点链接也能看懂每条情报要点。
        """
        if not self.enabled or not events:
            for e in events:
                if not e.summary or e.summary == e.title:
                    e.summary = self._template_summary(e)
            return events
        lines = []
        for i, e in enumerate(events):
            lines.append(f"{i}. [{e.severity_label}] {e.title} | {(e.raw or e.title)[:800]}")
        user = "\n".join(lines)
        out = self._chat(SUMMARY_SYSTEM, user)
        if not out:
            for e in events:
                e.summary = self._template_summary(e)
            return events
        mapping = self._parse_numbered(out)
        n = len(events)
        # 按数值排序 LLM 返回的「标题｜摘要」（编号可能 0-based 或 1-based，可能漏编）
        ordered = sorted(
            ((int(k), v) for k, v in mapping.items() if k.isdigit() and v),
            key=lambda kv: kv[0],
        )
        # 若返回数量与事件数一致，则按顺序一一对齐（自动纠正编号偏移/漏编）
        if len(ordered) == n:
            for idx, (_, text) in enumerate(ordered):
                self._apply_title_summary(events[idx], text)
        else:
            # 数量不一致时：精确按编号匹配，未命中者模板兜底
            for i, e in enumerate(events):
                key = str(i)
                if key in mapping and mapping[key]:
                    self._apply_title_summary(e, mapping[key])
                else:
                    e.summary = self._template_summary(e)
        return events

    @staticmethod
    def _apply_title_summary(e: SecurityEvent, text: str) -> None:
        """把 LLM 返回的「标题｜摘要」拆解，分别写入 title 与 summary。"""
        text = (text or "").strip()
        if "｜" in text:
            title, summary = text.split("｜", 1)
            title = title.strip()
            summary = summary.strip()
        elif "|" in text:
            title, summary = text.split("|", 1)
            title = title.strip()
            summary = summary.strip()
        else:
            title, summary = "", text
        # 仅当解析出非空标题时才覆盖（否则保留原英文标题）
        if title:
            e.title = title
        if summary:
            e.summary = summary

    @staticmethod
    def _template_summary(e: SecurityEvent) -> str:
        """规则模板自包含总结：地点 + 事件 + 等级（LLM 不可用时的兜底）。"""
        text = (e.title or "").strip()
        place = (e.country or "").strip()
        # 从标题末尾的逗号/破折号后识别地点（如 "xxx - Country"）
        if not place:
            for sep in (" - ", " — ", ", ", ": "):
                if sep in text:
                    tail = text.split(sep)[-1].strip()
                    if tail and len(tail) <= 20 and not tail.lower().startswith(("http", "www")):
                        place = tail
                        break
        severity_hint = {5: "属紧急事件，需立即关注", 4: "为高等级事件，需重点关注", 3: "为中等事件"}.get(e.severity, "")
        parts = []
        if place:
            parts.append(f"【{place}】")
        parts.append(text)
        if severity_hint:
            parts.append(severity_hint)
        return "，".join(parts) + "。"


    def assess(self, events: List[SecurityEvent]) -> str:
        """生成「今日态势研判」成段分析；未启用 LLM 时用模板。"""
        if self.enabled and events:
            digest = []
            for e in events[:20]:
                digest.append(
                    f"- [{e.severity_label}] {e.category_label} · {e.country or '全球'} · {e.title}"
                )
            out = self._chat(ASSESS_SYSTEM, "\n".join(digest))
            if out:
                return out
        return self._template_assess(events)

    @staticmethod
    def _template_assess(events: List[SecurityEvent]) -> str:
        """纯模板研判（LLM 不可用时的兜底），精简为 2 句。"""
        if not events:
            return "今日未采集到安防情报。"
        high = [e for e in events if e.severity >= 4]
        sectors = {e.sector_label for e in events}
        first = f"今日共 {len(events)} 条物理安防要闻，覆盖 {'、'.join(sorted(sectors))}。"
        if high:
            second = "重点关注：" + "、".join(e.title for e in high[:2]) + "。"
        else:
            second = "今日暂无紧急/高等级事件，整体态势平稳。"
        return first + second

    @staticmethod
    def _parse_numbered(out: str) -> dict:
        mapping: dict = {}
        for line in out.splitlines():
            m = re.match(r"^\s*(\d+)\s*[.、)]\s*(.+)$", line.strip())
            if m:
                mapping[m.group(1)] = m.group(2).strip()
        return mapping
