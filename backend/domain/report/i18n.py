"""英文报告用的业务数据译名表（仅演示数据集使用）。

中文版正文里的客户姓名、职业、风险等级、可疑类型都取自中文数据源，
英文版直接引用会出现中英混排。这里做一层轻量译名映射：
命中即译，未命中保留原值并加 * 标注，提示需人工补译。
真实产品应接机构主数据/译名库，而不是代码里的字典。
"""

# 姓氏常译（演示数据集只用到这几个）；未收录的姓氏保留原文
SURNAMES = {
    "刘": "LIU", "张": "ZHANG", "李": "LI", "王": "WANG", "陈": "CHEN",
    "赵": "ZHAO", "孙": "SUN", "周": "ZHOU", "吴": "WU", "郑": "ZHENG",
    "冯": "FENG", "徐": "XU", "胡": "HU", "朱": "ZHU", "高": "GAO",
}

# 完整姓名（未做脱敏的演示角色）与主体名称
NAME_MAP = {
    "陈立": "CHEN Li",
    "张敏": "ZHANG Min",
    "王建国": "WANG Jianguo",
    "XX商贸有限公司": "XX Trading Co., Ltd.",
    "YY建材贸易有限公司": "YY Building Materials Trading Co., Ltd.",
    "ZZ供应链有限公司": "ZZ Supply Chain Co., Ltd.",
}

OCCUPATION_MAP = {
    "医药企业销售岗": "Pharmaceutical sales",
    "退休教师": "Retired teacher",
    "批发零售": "Wholesale and retail",
    "个体工商户（建材零售）": "Sole proprietor (building materials retail)",
    "无固定职业": "No fixed occupation",
    "公司职员": "Corporate employee",
    "自由职业": "Self-employed",
    "教师": "Teacher",
    "跨境电商卖家": "Cross-border e-commerce seller",
    "医药代表": "Pharmaceutical representative",
    "建筑工人（海外）": "Construction worker (overseas)",
    "建材批发": "Building materials wholesale",
    "外贸个体户": "Sole proprietor (foreign trade)",
    "批发零售（供应链）": "Wholesale and retail (supply chain)",
    "待核实": "To be verified",
}

RISK_MAP = {"低": "Low", "中": "Medium", "高": "High"}

# 交易对手（演示数据集内的机构与占位主体）
ENTITY_MAP = {
    "Amazon结算": "Amazon (settlement)",
    "A公司": "Company A", "B公司": "Company B", "C公司": "Company C", "D公司": "Company D",
    "E公司": "Company E", "A建材客户": "Building materials customer A",
    "B装饰公司": "B Decoration Co., Ltd.", "C工程队": "Construction crew C",
    "W水泥厂": "W Cement Plant", "X钢材供应商": "Steel supplier X",
    "Y物流公司": "Y Logistics Co., Ltd.", "XX物流公司": "XX Logistics Co., Ltd.",
    "XX医药公司": "XX Pharmaceutical Co., Ltd.", "XX建材供应商": "XX Building Materials Supplier",
    "XX服装厂": "XX Garment Factory", "XX贸易有限公司": "XX Trading Co., Ltd.",
    "XX信用卡中心": "XX Credit Card Centre", "XX银行房贷": "XX Bank (mortgage)",
    "XX理财公司": "XX Wealth Management Co., Ltd.", "XX大学（境外）": "XX University (overseas)",
    "员工工资户": "Employee payroll account", "验资户": "Capital verification account",
    "社保基金": "Social security fund", "税务局": "Tax authority",
    "某OTC商户": "An OTC merchant", "本人": "Self",
    "东伊运": "Eastern Turkistan Islamic Movement (ETIM)",
}

TYPE_MAP = {
    "官方第1-1类 疑似非法汇兑型地下钱庄":
        "Type 1-1: Suspected illegal foreign exchange / underground banking",
    "官方第6类 疑似集资": "Type 6: Suspected illegal fundraising",
    "官方第1-2类关联 资金快进快出（过账通道特征）":
        "Related to Type 1-2: Rapid in-and-out fund flows (pass-through account)",
    "官方第11类 疑似赌博": "Type 11: Suspected gambling",
    "客户身份不明/证件缺失（CDD 条线 · 非交易型）":
        "Customer identity unverified / identification documents missing (CDD track, non-transactional)",
}


def _strip_role_suffix(name: str) -> str:
    for suffix in ("（个人）", "（对公）", "(individual)", "(corporate)"):
        name = name.replace(suffix, "")
    return name.strip()


def name_en(name: str) -> str:
    """客户名称英译：完整名走映射；脱敏名译成 LIU (name withheld)；机构名走映射。"""
    raw = _strip_role_suffix(name or "")
    if raw in NAME_MAP:
        return NAME_MAP[raw]
    head = raw[:1]
    if raw.endswith("某") or "某" in raw:
        if head in SURNAMES:
            return f"{SURNAMES[head]} (name withheld)"
        return f"{raw} *"
    return f"{raw} *"


def occupation_en(occupation: str) -> str:
    return OCCUPATION_MAP.get((occupation or "").strip(), f"{occupation} *")


def risk_en(level: str) -> str:
    return RISK_MAP.get((level or "").strip(), f"{level} *")


def type_en(type_no: str, type_name: str) -> str:
    """可疑类型英译：完整串命中映射才用；否则留空，避免把中文塞进英文正文。"""
    label = f"{type_no} {type_name}".strip()
    if not label:
        return ""
    return TYPE_MAP.get(label, "")


def _has_cjk(text: str) -> bool:
    return any("\u4e00" <= ch <= "\u9fff" for ch in text or "")


def counterparty_en(name: str) -> str:
    """交易对手英译：机构走映射、脱敏人名按姓氏翻译；无法翻译时给英文占位，不掺中文。"""
    raw = (name or "").strip()
    if not raw:
        return "—"
    if raw in ENTITY_MAP:
        return ENTITY_MAP[raw]
    if raw.startswith("妻子"):
        inner = counterparty_en(raw[2:])
        return f"spouse ({inner})"
    if raw.endswith("某") or raw.endswith("某个") or (len(raw) == 2 and raw.endswith("X")):
        head = raw[:1]
        if head in SURNAMES:
            return f"{SURNAMES[head]} (name withheld)"
    if not _has_cjk(raw):
        return raw
    return "see element 53 (counterparty details)"


def has_untranslated(*values) -> bool:
    """检测译名表未覆盖的取值（用于在报告里提示需人工补译）。"""
    return any(isinstance(v, str) and v.rstrip().endswith("*") and v.strip() != "*" for v in values)
