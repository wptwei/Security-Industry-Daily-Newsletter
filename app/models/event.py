"""安防情报事件数据模型。"""
from __future__ import annotations

import hashlib
from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Optional  # pyright: ignore[reportDeprecated]

# 领域：键 -> 中文标签
CATEGORIES = {
    "geopolitical": "地缘政治冲突",
    "terror": "恐怖袭击",
    "unrest": "骚乱/罢工",
    "disaster": "自然灾害",
    "health": "公共卫生/疫情",
    "cyber": "网络安全",
    "personnel": "海外人身与资产安全",
    "compliance": "合规/监管",
}

# 严重度：1-5 -> 中文标签
SEVERITY_LABELS = {5: "紧急", 4: "高", 3: "中", 2: "低", 1: "提示"}

# 四维标签：物理安防行业情报标注维度
TAG_DIMENSIONS = ("region", "company", "product", "event")

# 行业子类：键 -> 中文标签（参考海报的分类体系）
SECTORS = {
    "physical": "物理安防",
    "hardware": "安防硬件",
    "perimeter": "周界防护",
    "ai": "AI安防",
    "smart": "智能安防",
    "summit": "安防峰会",
    "industry": "行业动态",
    "robot": "安防机器人/无人机",
    "emergency": "突发事件",
}

# 行业子类图标（海报用）
SECTOR_ICONS = {
    "physical": "🏗️",
    "hardware": "🔐",
    "perimeter": "🛡️",
    "ai": "🧠",
    "smart": "📹",
    "summit": "🎪",
    "industry": "📈",
    "robot": "🤖",
    "emergency": "🚨",
}


@dataclass
class SecurityEvent:
    """一条安防情报事件。"""

    title: str
    source: str
    url: str = ""
    category: str = "geopolitical"
    severity: int = 2
    country: str = ""
    region: str = ""
    summary: str = ""            # 中文摘要（LLM 或模板）
    raw: str = ""                # 原文（供 LLM 摘要用）
    published_at: Optional[datetime] = None  # pyright: ignore[reportDeprecated]
    event_id: str = ""           # 源内唯一 ID（去重用）
    tags: dict = None            # 四维标签 {region:[], company:[], product:[], event:[]}  # pyright: ignore[reportAssignmentType, reportMissingTypeArgument]
    sector: str = "physical"     # 行业子类（物理安防/安防硬件/周界防护/AI安防/智能安防/峰会/行业动态/机器人无人机/突发事件）

    def __post_init__(self) -> None:
        if not self.raw:
            self.raw = self.title
        if not self.summary:
            self.summary = self.title
        if self.tags is None:  # pyright: ignore[reportUnknownMemberType, reportUnnecessaryComparison]
            self.tags = {"region": [], "company": [], "product": [], "event": []}

    @property
    def uid(self) -> str:
        """跨天去重唯一键：优先源内 ID，否则 URL 的 md5。"""
        if self.event_id:
            return f"{self.source}:{self.event_id}"
        digest = hashlib.md5((self.url or self.title).encode("utf-8")).hexdigest()[:16]
        return f"{self.source}:{digest}"

    @property
    def category_label(self) -> str:
        return CATEGORIES.get(self.category, self.category)

    @property
    def severity_label(self) -> str:
        return SEVERITY_LABELS.get(self.severity, str(self.severity))

    @property
    def sector_label(self) -> str:
        return SECTORS.get(self.sector, self.sector)

    @property
    def sector_icon(self) -> str:
        return SECTOR_ICONS.get(self.sector, "🔍")

    def tag_label(self) -> str:
        """四维标签的中文展示串，如「地域:美国｜产品:视频监控｜事件:并购」。"""
        names = {
            "region": "地域",
            "company": "企业",
            "product": "产品",
            "event": "事件",
        }
        parts = []
        for dim in TAG_DIMENSIONS:
            vals = self.tags.get(dim) or []  # pyright: ignore[reportUnknownVariableType, reportUnknownMemberType]
            if vals:
                parts.append(f"{names[dim]}:{'、'.join(vals)}")  # pyright: ignore[reportUnknownMemberType, reportUnknownArgumentType]
        return "｜".join(parts)  # pyright: ignore[reportUnknownArgumentType]

    def to_dict(self) -> dict:  # pyright: ignore[reportMissingTypeArgument, reportUnknownParameterType]
        data = asdict(self)
        data["uid"] = self.uid
        data["category_label"] = self.category_label
        data["severity_label"] = self.severity_label
        data["sector_label"] = self.sector_label
        data["tag_label"] = self.tag_label()
        data["published_at"] = self.published_at.isoformat() if self.published_at else None
        return data
