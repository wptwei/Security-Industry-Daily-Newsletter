"""严重度分级：规则打分 1-5（5 最高）。"""
from __future__ import annotations

from app.models.event import SecurityEvent

# 来源已给出权威严重度，不再覆盖
AUTHORITATIVE_SOURCES = {"usgs", "cisa", "nvd"}

SEV5 = (
    "mass casualty", "martial law", "state of emergency", "declared war",
    "major earthquake", "大规模伤亡", "紧急状态", "戒严", "宣战",
)
SEV4 = (
    "killed", "deadly", "deadliest", "escalat", "outbreak", "ransomware",
    "in the wild", "critical vulnerability", "死亡", "升级", "爆发",
    "在野利用", "重大", "击落", "导弹袭击",
)
SEV3 = (
    "injured", "wounded", "protest", "clash", "curfew",
    "受伤", "抗议", "罢工", "冲突", "骚乱", "宵禁",
)

# 有实质信息量的行业动态（厂商合作/产品发布/市场报告/展会/政策标准等）
# 从默认「低」提为「中」，使其进入「要点摘要」档，而非「简讯速览」一行。
INDUSTRY_SIGNAL = (
    "merger", "acquisition", "acquires", "funding", "investment", "ipo",
    "partnership", "collaboration", "launch", "unveil", "exhibition",
    "summit", "conference", "market", "forecast", "standard", "policy",
    "并购", "收购", "融资", "投资", "上市", "合作", "发布", "推出",
    "展会", "峰会", "大会", "安博会", "市场", "报告", "预测", "标准", "政策", "调研",
)


class SeverityRater:
    def rate(self, event: SecurityEvent) -> int:
        if event.source in AUTHORITATIVE_SOURCES:
            return event.severity
        text = f"{event.title} {event.raw}".lower()
        if any(kw in text for kw in SEV5):
            return 5
        if any(kw in text for kw in SEV4):
            return 4
        if any(kw in text for kw in SEV3):
            return 3
        if any(kw in text for kw in INDUSTRY_SIGNAL):
            return 3
        return 2
