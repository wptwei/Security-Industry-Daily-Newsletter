"""事件领域分类：规则关键词打分。"""
from __future__ import annotations

from typing import Dict

from app.models.event import CATEGORIES, SecurityEvent

# 每个领域一组关键词（英文 + 中文，均转小写匹配）
CATEGORY_KEYWORDS: Dict[str, tuple] = {
    "cyber": (
        "cyber", "malware", "ransomware", "breach", "vulnerability", "cve",
        "hack", "phishing", "ddos", "botnet", "zero-day", "漏洞", "勒索软件",
        "数据泄露", "黑客", "网络攻击", "钓鱼",
    ),
    "disaster": (
        "earthquake", "flood", "typhoon", "hurricane", "landslide", "tsunami",
        "wildfire", "volcano", "drought", "cyclone", "地震", "洪水", "台风",
        "飓风", "山体滑坡", "海啸", "野火", "火山", "干旱",
    ),
    "health": (
        "epidemic", "outbreak", "pandemic", "virus", "mpox", "cholera",
        "dengue", "measles", "marburg", "疫情", "病毒", "爆发", "霍乱",
        "登革热", "麻疹", "公共卫生",
    ),
    "terror": (
        "terror", "bombing", "extremist", "suicide bomb", "jihad", "militant attack",
        "恐袭", "恐怖袭击", "爆炸案", "自杀式", "极端分子",
    ),
    "unrest": (
        "protest", "riot", "coup", "unrest", "demonstration",
        "civil disobedience", "骚乱", "罢工", "政变", "抗议", "示威", "暴乱",
    ),
    "personnel": (
        "kidnap", "abduction", "hostage", "robbery", "assault", "evacuation",
        "travel advisory", "consular", "expatriate", "绑架", "劫持", "人质",
        "抢劫", "撤离", "领事提醒", "安全提醒", "海外",
    ),
    "compliance": (
        "sanction", "export control", "tariff", "regulation", "compliance",
        "embargo", "trade restriction", "entity list", "制裁", "出口管制",
        "关税", "监管", "合规", "贸易限制", "实体清单",
    ),
    "geopolitical": (
        "war", "conflict", "missile", "military", "invasion", "border clash",
        "ceasefire", "airstrike", "troops", "artillery", "战争", "冲突",
        "导弹", "军事", "入侵", "边境", "停火", "空袭", "军队", "炮击",
    ),
}

# 匹配优先级：得分相同时靠前优先（越具体越靠前）
PRIORITY = ["cyber", "disaster", "health", "terror", "unrest", "personnel", "compliance", "geopolitical"]

# 来源已明确指定领域，分类时不再覆盖
AUTHORITATIVE_SOURCES = {"usgs", "cisa", "nvd", "mfa"}

# 物理安防聚焦：仅保留这些领域。
# 排除：纯网络 cyber / 合规 compliance / 公共卫生 health；
# 同时剔除地缘政治 geopolitical、社会骚乱 unrest（这两类本质是政治/社会事件，
# 非物理安防重点，避免报告被战争/空袭/抗议/政变等泛安全内容带偏）。
PHYSICAL_SECURITY_CATEGORIES = {
    "terror", "disaster", "personnel",
}

# 物理安防相关性关键词：事件必须命中这些词才视为物理安防相关，
# 用于过滤通用新闻源（BBC/Guardian/Al Jazeera 等）里的娱乐/体育/社会杂闻。
PHYSICAL_KEYWORDS = (
    # 灾害
    "earthquake", "flood", "typhoon", "hurricane", "landslide", "tsunami",
    "wildfire", "volcano", "drought", "cyclone", "storm", "地震", "洪水",
    "台风", "飓风", "山体滑坡", "海啸", "野火", "火山", "干旱", "暴雨", "泥石流",
    # 恐袭/冲突/骚乱
    "terror", "bombing", "extremist", "militant", "war", "conflict",
    "missile", "military", "invasion", "airstrike", "artillery", "ceasefire",
    "protest", "riot", "coup", "unrest", "demonstration", "strike", "curfew",
    "clash", "killed", "deadly", "casualty", "attack", "assault", "siege",
    "gunfire", "shelling", "bombard",
    "恐袭", "恐怖袭击", "爆炸", "战争", "冲突", "导弹", "军事", "入侵",
    "空袭", "炮击", "抗议", "骚乱", "政变", "罢工", "暴乱", "宵禁", "戒严",
    "袭击", "交火", "伤亡", "遇难", "枪击",
    # 人身/资产安全
    "kidnap", "abduction", "hostage", "robbery", "assault", "evacuation",
    "travel advisory", "consular", "expatriate", "security alert",
    "绑架", "劫持", "人质", "抢劫", "撤离", "领事提醒", "安全提醒",
    # 安防行业/产品/企业
    "surveillance", "camera", "cctv", "access control", "door lock",
    "alarm system", "perimeter security", "security system", "video analytics",
    "biometric", "facial recognition", "intrusion detection", "body camera",
    "security guard", "security firm", "security company", "security industry",
    "physical security", "perimeter", "critical infrastructure",
    "视频监控", "监控", "摄像头", "门禁", "报警", "安防", "人脸识别",
    "生物识别", "周界", "入侵检测", "入侵探测", "实体防护", "物防技防",
    "保安", "防盗", "关键基础设施",
)

# 负向关键词：命中即视为纯网络安全噪音，即使领域误判为物理安防也排除
NEGATIVE_KEYWORDS = (
    "cyber security", "cybersecurity", "vulnerability", "exploit", "malware",
    "ransomware", "cve", "zero-day", "phishing", "漏洞", "病毒", "渗透",
    "网络攻击", "勒索软件", "黑客",
)


class Classifier:
    def __init__(self, extra_positive: tuple = (), extra_negative: tuple = ()) -> None:
        """可注入额外正/负向关键词（来自配置 FILTER_POSITIVE / FILTER_NEGATIVE）。"""
        self.positive_keywords = PHYSICAL_KEYWORDS + tuple(extra_positive)
        self.negative_keywords = NEGATIVE_KEYWORDS + tuple(extra_negative)

    def classify(self, event: SecurityEvent) -> str:
        if event.source in AUTHORITATIVE_SOURCES and event.category in CATEGORIES:
            return event.category
        text = f"{event.title} {event.raw} {event.summary}".lower()
        scores: Dict[str, int] = {}
        for cat, keywords in CATEGORY_KEYWORDS.items():
            hit = sum(1 for kw in keywords if kw in text)
            if hit:
                scores[cat] = hit
        if not scores:
            # 回退：RSS 采集器预设的领域，或默认地缘
            return event.category if event.category in CATEGORIES else "geopolitical"
        return max(scores.items(), key=lambda kv: (kv[1], -PRIORITY.index(kv[0])))[0]

    def is_physical_security(self, event: SecurityEvent) -> bool:
        """判断事件是否属于物理安防重点。

        规则：
        1. 领域必须属于物理安防五类（排除 cyber/compliance/health）。
        2. 权威信源（usgs/cisa/nvd/mfa）直接采信。
        3. 负向优先：命中网络安全关键词（vulnerability/exploit/malware 等）即排除，
           防止网络安全新闻被误判为物理安防。
        4. 内容必须命中物理安防相关性关键词，过滤娱乐/体育/社会杂闻。
        """
        if event.category not in PHYSICAL_SECURITY_CATEGORIES:
            return False
        # 权威信源（usgs/cisa/nvd/mfa）直接采信，不再做关键词过滤
        if event.source in AUTHORITATIVE_SOURCES:
            return True
        text = f"{event.title} {event.raw} {event.summary}".lower()
        # 负向优先：网络安全噪音直接排除
        if any(kw in text for kw in self.negative_keywords):
            return False
        return any(kw in text for kw in self.positive_keywords)
