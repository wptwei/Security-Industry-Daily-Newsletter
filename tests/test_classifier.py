"""分类与分级规则的单元测试（不依赖网络）。"""
from app.models.event import SecurityEvent
from app.services.classifier import Classifier
from app.services.severity import SeverityRater
from app.services.tagger import Tagger
from app.services.sector import SectorClassifier
from app.services.sensitive import SensitiveFilter


def _ev(title, source="rss:x", category="geopolitical", raw=""):
    return SecurityEvent(title=title, source=source, category=category, raw=raw or title)


def test_classify_cyber():
    c = Classifier()
    assert c.classify(_ev("Ransomware attack hits hospital network")) == "cyber"
    assert c.classify(_ev("Critical vulnerability found in VPN")) == "cyber"


def test_classify_disaster():
    c = Classifier()
    assert c.classify(_ev("Magnitude 6.2 earthquake strikes region")) == "disaster"


def test_classify_terror():
    c = Classifier()
    assert c.classify(_ev("Suicide bombing kills 10 in market")) == "terror"


def test_classify_unrest():
    c = Classifier()
    assert c.classify(_ev("Massive protests erupt over fuel prices")) == "unrest"


def test_classify_compliance():
    c = Classifier()
    assert c.classify(_ev("New sanctions target tech firms")) == "compliance"


def test_authoritative_source_preserved():
    c = Classifier()
    ev = _ev("M7.1 earthquake", source="usgs", category="disaster")
    assert c.classify(ev) == "disaster"


def test_severity_source_preserved():
    r = SeverityRater()
    ev = _ev("M7.1 earthquake", source="usgs", category="disaster")
    ev.severity = 5
    assert r.rate(ev) == 5


def test_severity_keyword():
    r = SeverityRater()
    assert r.rate(_ev("Mass casualty in major earthquake")) == 5
    assert r.rate(_ev("Two killed in border clash")) == 4
    assert r.rate(_ev("Protest injured several")) == 3
    assert r.rate(_ev("Routine news update")) == 2


def test_is_physical_security():
    c = Classifier()
    # 物理安防领域 + 命中相关性关键词 -> 保留
    assert c.is_physical_security(_ev("Magnitude 6.2 earthquake strikes", category="disaster")) is True
    assert c.is_physical_security(_ev("Hikvision launches surveillance camera", category="personnel")) is True
    assert c.is_physical_security(_ev("Terror attack injures civilians", category="terror")) is True
    # 非物理安防领域 -> 过滤
    for cat in ("cyber", "compliance", "health"):
        assert c.is_physical_security(_ev("Ransomware attack", category=cat)) is False
    # 地缘政治/社会骚乱（非物理安防重点）-> 过滤
    assert c.is_physical_security(_ev("Two killed in border clash", category="geopolitical")) is False
    assert c.is_physical_security(_ev("Anti-immigration riot escalates", category="unrest")) is False
    # 权威信源直接采信（无需关键词）
    assert c.is_physical_security(_ev("M7.1 earthquake", source="usgs", category="disaster")) is True


def test_tagger_dimensions():
    t = Tagger()
    e = _ev("Hikvision launches new access control system in USA")
    t.tag(e)
    assert "美国" in e.tags["region"]
    assert "海康威视" in e.tags["company"]
    assert any("门禁" in p for p in e.tags["product"])
    assert "发布" in e.tags["event"]
    assert "地域" in e.tag_label()


def test_tagger_merge_acquisition():
    t = Tagger()
    e = _ev("Bosch acquires access control firm in Germany")
    t.tag(e)
    assert "德国" in e.tags["region"]
    assert "博世" in e.tags["company"]
    assert "并购" in e.tags["event"]


def test_sector_classify_hardware():
    sc = SectorClassifier()
    e = _ev("Hikvision launches new IP camera with thermal imaging", category="personnel")
    e.category = Classifier().classify(e)
    assert sc.classify(e) in ("hardware", "smart")


def test_sector_classify_summit():
    sc = SectorClassifier()
    e = _ev("GSX conference opens volunteer recruitment", category="personnel")
    assert sc.classify(e) == "summit"


def test_sector_classify_emergency():
    sc = SectorClassifier()
    # 灾害类（非行业来源 + 命中紧急词）-> emergency
    e = _ev("Magnitude 7.0 earthquake strikes coast", category="disaster")
    e.category = Classifier().classify(e)
    assert sc.classify(e) == "emergency"


def test_sector_classify_geopolitical_not_emergency():
    """地缘政治/军事冲突不再是物理安防重点，不判定为突发事件。"""
    sc = SectorClassifier()
    e = _ev("Two killed in border clash between troops", category="geopolitical")
    e.category = Classifier().classify(e)
    assert sc.classify(e) != "emergency"


def test_sector_classify_robot():
    sc = SectorClassifier()
    e = _ev("Army deploys anti-drone robots to border", category="geopolitical")
    assert sc.classify(e) == "robot"


def test_similarity_key():
    from app.agents.brief_agent import BriefAgent
    assert BriefAgent._similarity_key(_ev("M6.5 earthquake Japan")) == "地震"
    assert BriefAgent._similarity_key(_ev("M5.8 earthquake Indonesia")) == "地震"
    assert BriefAgent._similarity_key(_ev("Gang attack near Haiti capital")) == "帮派袭击"
    assert BriefAgent._similarity_key(_ev("Hospital fire kills 14 in Pakistan")) == "火灾"
    # 不同主题 -> 不同 key
    assert BriefAgent._similarity_key(_ev("M6.5 earthquake Japan")) != BriefAgent._similarity_key(_ev("Hospital fire kills 14"))


def test_select_top_similarity_limit():
    """相似事件最多推 2 条（不限制国家）。"""
    from app.agents.brief_agent import BriefAgent
    agent = BriefAgent.__new__(BriefAgent)
    agent.top_n = 8
    agent.emergency_quota = 2

    events = [
        _ev("M7.1 earthquake Japan", source="usgs", category="disaster"),
        _ev("M6.8 earthquake Indonesia", source="usgs", category="disaster"),
        _ev("M6.2 earthquake Tonga", source="usgs", category="disaster"),
        _ev("M5.9 earthquake Taiwan", source="usgs", category="disaster"),
        _ev("M6.0 earthquake Chile", source="usgs", category="disaster"),
        _ev("Gang attack kills 47 in Haiti", source="rss:a", category="personnel"),
        _ev("Gang violence in Mexico", source="rss:b", category="personnel"),
        _ev("Gang shootout in Brazil", source="rss:c", category="personnel"),
    ]
    for e in events:
        e.severity = 4
        e.sector = "emergency"

    result = agent._select_top(events)
    # 突发事件固定上限：最多 emergency_quota=2 条
    assert len(result) <= agent.emergency_quota, f"突发事件超过配额: {len(result)}"
    # 地震类最多 2 条，帮派类最多 2 条
    quakes = [e for e in result if "earthquake" in e.title.lower()]
    gangs = [e for e in result if "gang" in e.title.lower()]
    assert len(quakes) <= 2, f"地震类超过 2 条: {len(quakes)}"
    assert len(gangs) <= 2, f"帮派类超过 2 条: {len(gangs)}"


def test_sensitive_filter_political():
    """国内政治敏感话题应被过滤。"""
    f = SensitiveFilter()
    # 政治人物/政党
    assert f.is_sensitive(_ev("Xi Jinping meets with foreign leaders")) is True
    assert f.is_sensitive(_ev("中共召开重要会议")) is True
    # 敏感地区政治
    assert f.is_sensitive(_ev("Taiwan independence movement grows")) is True
    assert f.is_sensitive(_ev("Uyghur human rights report")) is True
    assert f.is_sensitive(_ev("Tibet independence activists protest")) is True
    # 敏感历史/社会
    assert f.is_sensitive(_ev("Tiananmen anniversary")) is True


def test_sensitive_filter_keeps_industry():
    """不应误伤安防企业/展会/灾害等正常内容。"""
    f = SensitiveFilter()
    # 中国安防企业（应保留）
    assert f.is_sensitive(_ev("Hikvision launches new IP camera")) is False
    assert f.is_sensitive(_ev("Dahua releases access control system")) is False
    # 安防展会（应保留）
    assert f.is_sensitive(_ev("CPSE security expo opens in Shenzhen")) is False
    # 普通中国地区自然灾害（四川/云南等非敏感地区，应保留）
    assert f.is_sensitive(_ev("Magnitude 6.0 earthquake hits Sichuan China")) is False
    # 国外政治（非中国，应保留）
    assert f.is_sensitive(_ev("Haiti gang attack kills 47")) is False
    assert f.is_sensitive(_ev("Colombia president announces immigration policy")) is False


def test_sensitive_filter_region_names():
    """敏感地区政治话题应过滤，但自然灾害应保留（适当放开）。"""
    f = SensitiveFilter()
    # 敏感地区政治（应过滤）
    assert f.is_sensitive(_ev("Taiwan independence movement")) is True
    assert f.is_sensitive(_ev("Tibet independence activists")) is True
    assert f.is_sensitive(_ev("Uyghur human rights report")) is True
    # 敏感地区自然灾害（应保留，非政治话题）
    assert f.is_sensitive(_ev("尼泊尔-西藏边境山洪致157死数百失踪")) is False
    assert f.is_sensitive(_ev("Taiwan earthquake magnitude 6.2")) is False
    assert f.is_sensitive(_ev("Flooding hits Xinjiang region")) is False
    assert f.is_sensitive(_ev("Hong Kong typhoon causes damage")) is False


def test_sensitive_filter_action():
    """filter() 应剔除敏感事件并返回安全事件。"""
    f = SensitiveFilter()
    events = [
        _ev("Hikvision launches camera", source="rss:sec"),
        _ev("Taiwan independence protest", source="rss:news"),
        _ev("Hospital fire kills 14 in Pakistan", source="rss:news"),
        _ev("中共召开重要会议", source="rss:news"),
    ]
    kept, removed = f.filter(events)
    assert removed == 2
    assert len(kept) == 2
    assert all(not f.is_sensitive(e) for e in kept)


def test_sensitive_filter_apple():
    """Apple 公司相关内容一律过滤。"""
    f = SensitiveFilter()
    # Apple 公司新闻（应过滤）
    assert f.is_sensitive(_ev("Apple launches new iPhone")) is True
    assert f.is_sensitive(_ev("苹果公司发布新产品")) is True
    assert f.is_sensitive(_ev("Tim Cook announces Apple Vision")) is True
    assert f.is_sensitive(_ev("Apple Watch sales decline")) is True
    # 不误伤非 Apple 的英文单词
    assert f.is_sensitive(_ev("pineapple farming project")) is False
    # 不误伤正常安防内容
    assert f.is_sensitive(_ev("Hikvision launches surveillance camera")) is False


def test_time_window_filter():
    """时间窗口过滤：只保留 24 小时内的新闻。"""
    from datetime import datetime, timedelta, timezone
    from app.agents.brief_agent import BriefAgent

    agent = BriefAgent.__new__(BriefAgent)
    agent.time_window_hours = 24

    now = datetime.now(timezone.utc)
    events = [
        # 2 小时前（应保留）
        SecurityEvent(title="recent", source="x", published_at=now - timedelta(hours=2)),
        # 48 小时前（应过滤）
        SecurityEvent(title="old", source="x", published_at=now - timedelta(hours=48)),
        # 无时间（保守保留）
        SecurityEvent(title="no_time", source="x", published_at=None),
        # 未来时间（时区偏差，保留）
        SecurityEvent(title="future", source="x", published_at=now + timedelta(hours=1)),
    ]
    kept = agent._filter_recent(events)
    titles = {e.title for e in kept}
    assert "recent" in titles
    assert "old" not in titles
    assert "no_time" in titles
    assert "future" in titles


def test_negative_keyword_filter():
    """负向关键词：网络安全噪音即使被误判为物理安防也应排除。"""
    c = Classifier()
    # 网络安全新闻（含 vulnerability/exploit/malware）应排除
    assert c.is_physical_security(_ev("New vulnerability found in access control system", category="personnel")) is False
    assert c.is_physical_security(_ev("Exploit targets surveillance cameras", category="personnel")) is False
    assert c.is_physical_security(_ev("Malware infects security camera firmware", category="personnel")) is False
    # 物理安防正向（应保留）
    assert c.is_physical_security(_ev("Hikvision launches new access control system", category="personnel")) is True
    assert c.is_physical_security(_ev("Perimeter security upgrade for critical infrastructure", category="personnel")) is True


def test_classifier_extra_keywords():
    """配置注入的额外正/负向关键词应生效。"""
    c = Classifier(
        extra_positive=("实体防护",),
        extra_negative=("渗透测试",),
    )
    assert c.is_physical_security(_ev("实体防护方案发布", category="personnel")) is True
    assert c.is_physical_security(_ev("渗透测试服务", category="personnel")) is False
