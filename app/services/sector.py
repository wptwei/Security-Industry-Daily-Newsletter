"""行业子类识别：将事件归入物理安防行业子类。

参考海报的分类体系：
- 物理安防 physical
- 安防硬件 hardware
- 周界防护 perimeter
- AI 安防 ai
- 智能安防 smart
- 安防峰会 summit
- 行业动态 industry
- 安防机器人/无人机 robot
- 突发事件 emergency（非行业性的地缘冲突/恐袭/灾害等）

规则关键词匹配，不依赖网络与 LLM。
"""
from __future__ import annotations

import re
from typing import List, Tuple

from app.models.event import SecurityEvent

# 每个子类一组关键词（英文 + 中文，均小写匹配）
SECTOR_KEYWORDS: List[Tuple[str, tuple]] = [
    ("robot", (
        "drone", "uav", "robot", "robotics", "unmanned", "无人机", "机器人",
        "反无人机",
    )),
    ("ai", (
        "ai ", "artificial intelligence", "machine learning", "video analytics",
        "deep learning", "computer vision", "人工智能", "视频分析", "机器学习",
        "计算机视觉", "智能分析",
    )),
    ("summit", (
        "isc west", "gsx", "ifsec", "intersec", "expoprotection", "sicur",
        "cpse", "exhibition", "trade show", "summit", "conference", "asial",
        "esx", "psatec", "展会", "峰会", "大会", "安博会", "研讨会",
    )),
    ("perimeter", (
        "perimeter", "fence", "barrier", "turnstile", "gate", "border security",
        "intrusion detection", "radar", "周界", "围栏", "道闸", "闸机", "边界",
        "入侵检测", "边境安防", "雷达",
    )),
    ("hardware", (
        "camera", "cctv", "nvr", "dvr", "sensor", "lock", "intercom",
        "fingerprint", "thermal", "lidar", "alarm panel", "door controller",
        "视频监控", "摄像头", "摄像机", "门锁", "对讲", "指纹", "热成像",
        "传感器", "报警主机", "门禁控制器", "读卡器",
    )),
    ("smart", (
        "smart", "intelligent", "integrated", "platform", "iot", "cloud",
        "access control", "facial recognition", "biometric", "智能", "集成",
        "平台", "物联网", "门禁", "人脸识别", "生物识别", "访客管理",
    )),
    ("industry", (
        "market", "merger", "acquisition", "funding", "investment", "report",
        "survey", "forecast", "partnership", "collaboration", "regulation",
        "standard", "policy", "市场", "并购", "收购", "融资", "投资", "报告",
        "调研", "预测", "合作", "监管", "标准", "政策", "行业",
    )),
    # physical 作为兜底子类，关键词更宽泛
    ("physical", (
        "security", "physical security", "guard", "surveillance", "protection",
        "safety", "安防", "安保", "保安", "防护", "安全",
    )),
]

# 突发事件关键词：非行业内容（地缘冲突/恐袭/灾害等）
EMERGENCY_KEYWORDS = (
    "war", "conflict", "missile", "military", "invasion", "airstrike",
    "terror", "bombing", "extremist", "attack", "kidnap", "hostage",
    "earthquake", "flood", "typhoon", "hurricane", "wildfire", "tsunami",
    "protest", "riot", "coup", "unrest", "evacuation", "clash", "killed",
    "troops", "artillery", "ceasefire", "casualty", "gunfire", "shelling",
    "战争", "冲突", "导弹", "军事", "入侵", "空袭", "恐袭", "恐怖袭击",
    "爆炸", "袭击", "绑架", "劫持", "地震", "洪水", "台风", "飓风",
    "野火", "海啸", "抗议", "骚乱", "政变", "撤离", "交火", "伤亡",
    "遇难", "枪击", "炮击", "军队",
)

# 优先级：越具体越靠前，兜底的 physical 放最后
PRIORITY = ["emergency", "robot", "ai", "summit", "perimeter", "hardware", "smart", "industry", "physical"]

# 行业垂直媒体来源：这些源的文章是行业新闻，即使命中通用紧急词也不判突发事件
INDUSTRY_SOURCES = (
    "securityjournal", "securitylink", "send2press", "revistaseguranca",
    "internationalsecurityjournal", "securityinfowatch", "sdmmag",
    "securitytoday", "ifsecglobal", "securitymagazine", "asmag",
)


class SectorClassifier:
    """识别事件的行业子类。"""

    def classify(self, event: SecurityEvent) -> str:
        text = f"{event.title} {event.raw} {event.summary}".lower()

        # 行业垂直媒体来源：直接走行业子类匹配，不判突发事件
        from_industry_source = any(s in event.source for s in INDUSTRY_SOURCES)

        # 突发事件判定：仅对非行业来源、且命中紧急关键词的事件。
        # 聚焦物理安防：只对 terror（恐袭）/ disaster（灾害）/ personnel（人身安全）判定，
        # geopolitical（地缘政治）与 unrest（社会骚乱）不属于物理安防重点，不在此判定。
        if not from_industry_source and event.category in (
            "terror", "disaster", "personnel",
        ):
            if any(kw in text for kw in EMERGENCY_KEYWORDS):
                return "emergency"

        scores = {}
        for sector, keywords in SECTOR_KEYWORDS:
            hit = 0
            for kw in keywords:
                if kw.endswith(" ") or kw.endswith("ai"):  # 短词/带空格词用词边界
                    if re.search(rf"(?<![a-z0-9]){re.escape(kw.strip())}(?![a-z0-9])", text):
                        hit += 1
                elif kw in text:
                    hit += 1
            if hit:
                scores[sector] = hit
        if not scores:
            return "physical"
        return max(scores.items(), key=lambda kv: (kv[1], -PRIORITY.index(kv[0])))[0]
