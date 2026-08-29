"""四维标签打标：地域 / 企业 / 产品 / 事件。

针对物理安防行业情报，从事件标题与原文中识别四类标签：
- 地域：国家/地区（覆盖全球各区域安防市场动态）
- 企业：安防行业重点企业及产业链企业
- 产品：视频监控、门禁、报警等细分产品
- 事件：政策、技术、市场、并购、展会等事件类型

全部为规则关键词匹配，不依赖网络与 LLM，稳定可控。
"""
from __future__ import annotations

import re
from typing import List

from app.models.event import SecurityEvent

# ---- 地域标签（国家/地区名，中英文）----
REGION_KEYWORDS: List[tuple] = [
    # (匹配关键词, 标准化标签)
    ("united states", "美国"), ("usa", "美国"), ("u.s.", "美国"), ("america", "美国"),
    ("united kingdom", "英国"), ("uk", "英国"), ("britain", "英国"),
    ("china", "中国"), ("chinese", "中国"),
    ("japan", "日本"), ("japanese", "日本"),
    ("south korea", "韩国"), ("korea", "韩国"),
    ("germany", "德国"), ("german", "德国"),
    ("france", "法国"), ("french", "法国"),
    ("india", "印度"), ("indian", "印度"),
    ("australia", "澳大利亚"), ("australian", "澳大利亚"),
    ("canada", "加拿大"), ("canadian", "加拿大"),
    ("brazil", "巴西"), ("brazilian", "巴西"),
    ("mexico", "墨西哥"),
    ("russia", "俄罗斯"), ("russian", "俄罗斯"),
    ("italy", "意大利"), ("italian", "意大利"),
    ("spain", "西班牙"), ("spanish", "西班牙"),
    ("saudi arabia", "沙特"), ("saudi", "沙特"),
    ("uae", "阿联酋"), ("dubai", "阿联酋"), ("united arab emirates", "阿联酋"),
    ("singapore", "新加坡"),
    ("turkey", "土耳其"), ("türkiye", "土耳其"),
    ("indonesia", "印度尼西亚"), ("indonesian", "印度尼西亚"),
    ("vietnam", "越南"), ("vietnamese", "越南"),
    ("thailand", "泰国"),
    ("philippines", "菲律宾"),
    ("malaysia", "马来西亚"),
    ("israel", "以色列"), ("israeli", "以色列"),
    ("africa", "非洲"), ("african", "非洲"),
    ("europe", "欧洲"), ("european", "欧洲"),
    ("asia", "亚洲"), ("asian", "亚洲"),
    ("middle east", "中东"),
    ("latin america", "拉美"),
    # 中文地名
    ("中国", "中国"), ("美国", "美国"), ("英国", "英国"), ("德国", "德国"),
    ("法国", "法国"), ("日本", "日本"), ("韩国", "韩国"), ("印度", "印度"),
    ("澳大利亚", "澳大利亚"), ("巴西", "巴西"), ("加拿大", "加拿大"),
    ("俄罗斯", "俄罗斯"), ("中东", "中东"), ("欧洲", "欧洲"), ("非洲", "非洲"),
]

# ---- 企业标签（安防行业重点企业及产业链企业）----
COMPANY_KEYWORDS: List[tuple] = [
    # 视频监控
    ("hikvision", "海康威视"), ("dahua", "大华股份"),
    ("axis communications", "Axis"), ("axis", "Axis"),
    ("bosch", "博世"), ("bosch security", "博世安防"),
    ("hanwha vision", "韩华视界"), ("hanwha", "韩华"),
    ("motorola solutions", "摩托罗拉系统"), ("avigilon", "Avigilon"),
    ("vivotek", "晶睿"), ("geovision", "奇偶"),
    ("uniview", "宇视"),
    # 门禁/安防集成
    ("assa abloy", "亚萨合莱"), ("allegion", "安朗杰"),
    ("dormakaba", "多玛凯拔"), ("honeywell", "霍尼韦尔"),
    ("johnson controls", "江森自控"), ("tyco", "泰科"),
    ("samsung techwin", "三星泰科"),
    # 报警
    ("adt", "ADT"), ("verisure", "Verisure"), ("securitas", "Securitas"),
    ("brinks", "Brinks"), ("stanley security", "Stanley Security"),
    # 其他/平台
    ("flir", "FLIR"), ("teledyne", "Teledyne"), ("nec corporation", "NEC"),
    ("carrier", "开利"), ("schneider electric", "施耐德电气"),
    ("safran", "赛峰"), ("idemia", "Idemia"),
    ("genetec", "Genetec"), ("milestone systems", "Milestone"),
    # 印度/东南亚安防企业（补充）
    ("cp plus", "CP PLUS"), ("zicom", "Zicom"),
    ("cp-plus", "CP PLUS"),
    # 中文企业
    ("海康威视", "海康威视"), ("大华", "大华股份"), ("宇视", "宇视"),
    ("华为", "华为"), ("中兴", "中兴"), ("博世", "博世"),
    ("霍尼韦尔", "霍尼韦尔"), ("亚萨合莱", "亚萨合莱"),
    ("海能达", "海能达"), ("天地伟业", "天地伟业"), ("大立科技", "大立科技"),
]

# ---- 产品标签（细分产品）----
PRODUCT_KEYWORDS: List[tuple] = [
    ("video surveillance", "视频监控"), ("cctv", "视频监控"), ("ip camera", "网络摄像机"),
    ("surveillance camera", "监控摄像机"), ("security camera", "监控摄像机"),
    ("nvr", "NVR"), ("dvr", "DVR"),
    ("access control", "门禁"), ("access control system", "门禁系统"),
    ("door access", "门禁"), ("smart lock", "智能门锁"), ("biometric", "生物识别"),
    ("facial recognition", "人脸识别"), ("fingerprint", "指纹识别"),
    ("intrusion detection", "入侵报警"), ("alarm system", "报警系统"),
    ("burglar alarm", "防盗报警"), ("perimeter security", "周界防范"),
    ("body camera", "执法记录仪"), ("body-worn camera", "执法记录仪"),
    ("thermal camera", "热成像"), ("thermal imaging", "热成像"),
    ("lidar", "激光雷达"), ("radar", "雷达"),
    ("drone", "无人机"), ("uav", "无人机"),
    ("video analytics", "视频分析"), ("ai camera", "AI摄像机"),
    ("intercom", "对讲"), ("turnstile", "闸机"),
    ("fire detection", "消防探测"), ("fire alarm", "消防报警"),
    ("barrier", "道闸"), ("license plate recognition", "车牌识别"), ("anpr", "车牌识别"),
    # 中文产品
    ("视频监控", "视频监控"), ("监控摄像", "监控摄像机"), ("摄像头", "监控摄像机"),
    ("门禁", "门禁"), ("报警", "报警系统"), ("人脸识别", "人脸识别"),
    ("生物识别", "生物识别"), ("智能门锁", "智能门锁"), ("对讲", "对讲"),
    ("热成像", "热成像"), ("无人机", "无人机"), ("周界", "周界防范"),
]

# ---- 事件标签（事件类型）----
EVENT_KEYWORDS: List[tuple] = [
    ("merger", "并购"), ("acquisition", "并购"), ("acquires", "并购"), ("acquire", "并购"),
    ("m&a", "并购"), ("takeover", "并购"),
    ("funding", "融资"), ("investment", "投资"), ("invests", "投资"),
    ("ipo", "上市"), ("listing", "上市"),
    ("partnership", "合作"), ("collaboration", "合作"),
    ("launch", "发布"), ("release", "发布"), ("unveil", "发布"), ("introduce", "发布"),
    ("patent", "专利"), ("innovation", "创新"),
    ("regulation", "政策/监管"), ("regulatory", "政策/监管"), ("policy", "政策/监管"),
    ("standard", "标准"), ("compliance", "合规"),
    ("government", "政府"), ("ban", "禁令"), ("sanction", "制裁"),
    ("market", "市场"), ("market share", "市场份额"), ("growth", "增长"),
    ("forecast", "预测"), ("report", "报告"), ("survey", "调研"),
    ("exhibition", "展会"), ("trade show", "展会"), ("summit", "峰会"), ("conference", "会议"),
    ("isc west", "ISC West展会"), ("gsx", "GSX展会"), ("ifsec", "IFSEC展会"),
    ("intersec", "Intersec展会"), ("expoprotection", "Expoprotection展会"),
    ("sicur", "SICUR展会"), ("cpse", "安博会"),
    ("data breach", "数据泄露"), ("cyberattack", "网络攻击"),
    # 中文事件
    ("并购", "并购"), ("收购", "并购"), ("融资", "融资"), ("投资", "投资"),
    ("上市", "上市"), ("合作", "合作"), ("发布", "发布"), ("推出", "发布"),
    ("专利", "专利"), ("政策", "政策/监管"), ("监管", "政策/监管"),
    ("标准", "标准"), ("市场", "市场"), ("增长", "增长"),
    ("展会", "展会"), ("峰会", "峰会"), ("安博会", "安博会"),
]


class Tagger:
    """为 SecurityEvent 打上四维标签。"""

    def tag(self, event: SecurityEvent) -> SecurityEvent:
        text = f"{event.title} {event.raw}".lower()
        event.tags = {
            "region": self._match(text, REGION_KEYWORDS),
            "company": self._match(text, COMPANY_KEYWORDS),
            "product": self._match(text, PRODUCT_KEYWORDS),
            "event": self._match(text, EVENT_KEYWORDS),
        }
        return event

    @staticmethod
    def _match(text: str, keywords: List[tuple]) -> List[str]:
        """返回命中的标准化标签，去重且保持出现顺序，最多 4 个。

        英文关键词用词边界精确匹配，并允许常见词形变化（复数/第三人称/
        过去式/进行时，如 launches -> launch、acquires -> acquire）；
        中文关键词直接子串匹配。避免短英文词误命中其他单词的子串。
        """
        found: List[str] = []
        for kw, label in keywords:
            if kw.isascii():
                # 英文：前缀匹配 + 可选常见后缀，前面必须是词边界
                stem = re.escape(kw)
                hit = re.search(rf"(?<![a-z0-9]){stem}(?:es|ed|ing|s)?(?![a-z0-9])", text)
            else:
                # 中文：直接子串匹配
                hit = kw in text
            if hit:
                if label not in found:
                    found.append(label)
                if len(found) >= 4:
                    break
        return found
