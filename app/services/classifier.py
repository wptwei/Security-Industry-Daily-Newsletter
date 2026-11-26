"""事件领域分类：规则关键词打分。"""
from __future__ import annotations

import re
from typing import Dict

from app.models.event import CATEGORIES, SecurityEvent
from app.services.sector import INDUSTRY_SOURCES

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

# 行业日报聚焦：只保留安防行业/人身资产安全类情报。
# 排除：
#   cyber（网络安全）、compliance（合规监管）、health（公共卫生）；
#   disaster（自然灾害：地震/洪水/台风等）；
#   terror（恐怖袭击/爆炸/枪击等暴力事件——管理层不需要事件通报，只要行业动态）；
#   geopolitical（地缘冲突）、unrest（骚乱/抗议）。
PHYSICAL_SECURITY_CATEGORIES = {
    "personnel",
}

# 暴力事件关键词：袭击/枪击/爆炸/绑架/伤亡等一律不进入行业日报
# 英文按词边界匹配（避免 deadbolt / deadline 这类产品词误伤）
VIOLENCE_TERMS_EN = (
    "attack", "assault", "bomb", "bombing", "explosion", "shooting", "gunfire",
    "gunmen", "stabbed", "stabbing", "kidnap", "abduction", "hostage", "massacre",
    "killed", "dead", "deaths", "injured", "wounded", "casualties", "terror",
    "terrorist",
)
VIOLENCE_TERMS_CN = (
    "袭击", "爆炸", "枪击", "绑架", "劫持", "人质", "遇难", "死亡", "受伤",
    "恐袭", "恐怖袭击", "伤亡", "交火", "空袭",
)
_VIOLENCE_RE = re.compile(
    r"(?<![a-z])(" + "|".join(re.escape(t) for t in VIOLENCE_TERMS_EN) + r")(?:s|es|ed|ing)?(?![a-z])"
)


def _has_violence(text: str) -> bool:
    if any(term in text for term in VIOLENCE_TERMS_CN):
        return True
    return bool(_VIOLENCE_RE.search(text))

# 垂直媒体文章常在正文顺带讨论网络、法规和商业背景。
# 选题以标题为准，避免正文中的旁支词语覆盖物理安防主主题。
VERTICAL_TITLE_TERMS = (
    "physical security", "security system", "security infrastructure", "surveillance",
    "camera", "cctv", "video", "access control", "critical communication", "install",
    "alarm", "screening", "monitoring", "patrol", "police", "fire detection",
    "guard", "perimeter", "door", "biometric", "identity", "summit", "award",
    "intrusion", "theft", "tma honors", "安防", "安保", "监控", "门禁", "安检", "报警",
    "周界", "无人机", "警务", "摄像", "生物识别", "消防", "奖项",
)
VERTICAL_OFFTOPIC_TERMS = (
    "cyber", "ransomware", "malware", "api key", "multi-factor authentication",
    "scam", "online storefront", "data centre", "data center", "网络安全", "勒索软件",
    "数据泄露", "黑客", "网络攻击", "诈骗", "数据中心",
)
VERTICAL_HARD_CYBER_TERMS = (
    "vulnerability", "exploit", "ransomware", "malware", "breach", "phishing",
    "cve-", "hackers", "api key", "漏洞", "恶意软件", "勒索软件", "数据泄露", "网络攻击",
)
VERTICAL_PHYSICAL_OVERRIDE = (
    "police summit", "video security", "physical security", "access control",
    "surveillance", "camera", "screening", "alarm", "perimeter",
    "警务峰会", "视频安防", "物理安防", "门禁", "监控", "安检", "报警", "周界",
)


def _source_haystack(event: SecurityEvent) -> str:
    """源标识 + 原始媒体名（Google 新闻聚合时 origin 为真实媒体）。"""
    return f"{event.source} {event.origin}".lower()


def _vertical_physical_title(event: SecurityEvent) -> bool:
    if not any(host in _source_haystack(event) for host in INDUSTRY_SOURCES):
        return False
    title = event.original_title.lower()
    if any(term in title for term in VERTICAL_HARD_CYBER_TERMS):
        return False
    if not any(term in title for term in VERTICAL_TITLE_TERMS):
        return False
    return (not any(term in title for term in VERTICAL_OFFTOPIC_TERMS)
            or any(term in title for term in VERTICAL_PHYSICAL_OVERRIDE))

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

# 繁体中文（港台）关键词补充：gl=TW/HK 源返回繁体，简体关键词命中不了，
# 这里补常用繁体变体，避免繁体物理安防新闻被误过滤 / 繁体网络噪音漏过。
TRADITIONAL_POSITIVE = (
    # 災害
    "颱風", "颶風", "海嘯", "山崩", "土石流", "乾旱", "豪雨", "山體滑坡",
    # 恐襲/衝突/騷亂
    "恐襲", "恐怖襲擊", "戰爭", "衝突", "導彈", "軍事", "空襲", "炮擊",
    "抗議", "騷亂", "政變", "罷工", "暴亂", "襲擊", "傷亡", "遇難", "槍擊",
    # 人身/資產安全
    "綁架", "人質", "搶劫", "撤離", "領事提醒",
    # 安防行業/產品/企業
    "監控", "攝影機", "攝像頭", "門禁", "報警", "視頻監控",
    "人臉識別", "人臉辨識", "生物識別", "生物辨識", "入侵偵測", "入侵檢測",
    "實體防護", "關鍵基礎設施", "保全", "防盜",
)

TRADITIONAL_NEGATIVE = (
    "資安", "網路安全", "駭客", "網路攻擊", "勒索軟體", "資料外洩",
    "網路釣魚", "惡意程式",
)


class Classifier:
    def __init__(self, extra_positive: tuple = (), extra_negative: tuple = ()) -> None:
        """可注入额外正/负向关键词（来自配置 FILTER_POSITIVE / FILTER_NEGATIVE）。"""
        self.positive_keywords = PHYSICAL_KEYWORDS + TRADITIONAL_POSITIVE + tuple(extra_positive)
        self.negative_keywords = NEGATIVE_KEYWORDS + TRADITIONAL_NEGATIVE + tuple(extra_negative)

    def classify(self, event: SecurityEvent) -> str:
        if event.source in AUTHORITATIVE_SOURCES and event.category in CATEGORIES:
            return event.category
        if _vertical_physical_title(event):
            return "personnel"
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
        """判断事件是否属于安防行业日报收录范围。

        规则：
        1. 垂直行业媒体：以标题是否属于行业主题为准。
        2. 其他来源：领域必须是 personnel（排除 cyber/compliance/health/
           disaster/terror/geopolitical/unrest）。
        3. 暴力事件（袭击/枪击/爆炸/绑架/伤亡等）一律排除——日报只做行业动态，
           不做事件通报。
        4. 负向优先：命中网络安全关键词即排除。
        5. 内容必须命中物理安防相关性关键词，过滤娱乐/体育/社会杂闻。
        """
        if any(host in _source_haystack(event) for host in INDUSTRY_SOURCES):
            # 行业媒体只看标题是否属于暴力事件，正文偶发提及不影响
            if _has_violence(event.original_title.lower()):
                return False
            return _vertical_physical_title(event)
        if event.category not in PHYSICAL_SECURITY_CATEGORIES:
            return False
        text = f"{event.title} {event.raw} {event.summary}".lower()
        # 暴力事件不收录（即使被误分类为 personnel）
        if _has_violence(text):
            return False
        # 权威信源（usgs/cisa/nvd/mfa）直接采信，不再做关键词过滤
        if event.source in AUTHORITATIVE_SOURCES:
            return True
        # 负向优先：网络安全噪音直接排除
        if any(kw in text for kw in self.negative_keywords):
            return False
        return any(kw in text for kw in self.positive_keywords)
