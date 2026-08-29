"""国内政治敏感话题过滤器 + 指定公司过滤。

核心目标：
1. 避免对外汇报中出现涉及「中国国内政治」的敏感话题（政治人物/政党、
   分裂言论、人权意识形态、外交军事政治等）。
2. 指定公司（Apple）相关内容一律不出现。

策略：命中以下任一关键词即判定为敏感，直接剔除。
"""
from __future__ import annotations

import re

from app.models.event import SecurityEvent

# 指定公司过滤：Apple 相关（英文用词边界，中文子串）
APPLE_CN = ("苹果", "苹果公司", "库克", "蒂姆库克", "iphone", "ipad", "macbook",
            "苹果手表", "airpods")
APPLE_EN = ("apple", "apple watch", "airpods", "imac", "macbook", "tim cook",
            "apple inc", "apple's", "iphone", "ipad", "ios", "macos", "app store")

# 强过滤：中国政治人物 / 政党 / 政府（政治语境）
SENSITIVE_POLITICAL = (
    # 中文
    "习近平", "国家主席", "总书记", "政治局", "中央委员", "国务院总理",
    "李克强", "王毅", "中共中央", "中共", "共产党", "共产党政权",
    "一党制", "社会主义制度", "意识形态", "政治体制",
    # 英文
    "xi jinping", "chinese president", "general secretary", "politburo",
    "state council", "communist party of china", "ccp", "chinese communist",
    "one-party", "authoritarian regime", "communist regime",
)

# 强过滤：敏感地区政治话题
SENSITIVE_REGIONS = (
    # 台湾
    "台独", "台湾独立", "蔡英文", "赖清德", "taiwan independence", "taiwanese independence",
    "taiwan president", "tsai ing-wen",
    # 香港
    "港独", "香港独立", "反修例", "占中", "hong kong independence",
    "hong kong protests", "hong kong democracy",
    # 新疆
    "疆独", "东突", "维吾尔人权", "新疆人权", "再教育营", "xinjiang camps",
    "uyghur", "uyghurs", "xinjiang re-education", "east turkestan",
    # 西藏
    "藏独", "西藏独立", "达赖", "dalai lama", "tibet independence",
    "free tibet", "tibetan independence",
)

# 强过滤：敏感历史/社会话题
SENSITIVE_TOPICS = (
    "六四", "天安门事件", "法轮功", "tiananmen", "tiananmen square",
    "falun gong", "june fourth",
)

# 中过滤：中国内政/意识形态/人权/审查
SENSITIVE_DOMESTIC = (
    "中国人权", "人权报告", "审查制度", "言论自由", "新闻自由",
    "宗教迫害", "民族压迫", "镇压", "human rights in china",
    "china censorship", "chinese censorship", "freedom of speech",
    "religious persecution", "political prisoner",
)

# 中过滤：中国外交/军事政治（政治语境）
SENSITIVE_FOREIGN = (
    "中美关系", "中美贸易战", "中美对抗", "台海军演", "对台军售",
    "解放军", "人民解放军", "南海争端", "南海仲裁",
    "china-us relations", "us-china tensions", "south china sea dispute",
    "pla military", "people's liberation army", "taiwan strait",
    "chinese military", "chinese foreign ministry",
)

# 全部敏感关键词（小写匹配）
ALL_SENSITIVE = tuple(
    (SENSITIVE_POLITICAL + SENSITIVE_REGIONS
     + SENSITIVE_TOPICS + SENSITIVE_DOMESTIC + SENSITIVE_FOREIGN)
)


class SensitiveFilter:
    """国内政治敏感话题 + 指定公司过滤器。"""

    def is_sensitive(self, event: SecurityEvent) -> bool:
        """判断事件是否涉及政治敏感话题或指定公司（Apple）。"""
        text = f"{event.title} {event.raw} {event.summary}".lower()
        # 政治敏感（子串匹配）
        if any(kw in text for kw in ALL_SENSITIVE):
            return True
        # Apple 相关（中文子串，英文词边界）
        return self._match_apple(text)

    @staticmethod
    def _match_apple(text: str) -> bool:
        """匹配 Apple 公司相关内容：中文子串、英文词边界。"""
        for kw in APPLE_CN:
            if kw in text:
                return True
        for kw in APPLE_EN:
            if re.search(rf"(?<![a-z0-9]){re.escape(kw)}(?![a-z0-9])", text):
                return True
        return False

    def filter(self, events):
        """过滤掉敏感事件，返回安全事件列表。"""
        kept = []
        removed = 0
        for e in events:
            if self.is_sensitive(e):
                removed += 1
                continue
            kept.append(e)
        return kept, removed
