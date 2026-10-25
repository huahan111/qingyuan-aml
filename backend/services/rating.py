"""客户洗钱风险评级：四维透明打分模型（PRD §4.7 口径的演示实现）。

维度与权重：身份背景 25% + 业务渠道 20% + 地域风险 20% + 行为动态 35%。
设计原则：
1. 每一分都可解释——输出逐项加分明细（因素、依据、分值），不给"黑盒分"；
2. 行为动态维度由预警结果动态回写（规则命中数计入），对应 PRD"预警驱动即时升降级"；
3. 与客户存量评级（customer_info.risk_level）对比给出 升级/维持/下调；上调至高风险
   触发 EDD（强化尽调）提示；
4. 诚实边界：地域维度以跨境/外币作为代理指标（演示数据无真实地区字段），生产环境
   应接入高风险地区清单（FATF/监管下发口径）；权重与阈值为演示初值，非监管标准。
"""
import re

CASH_CHANNELS = ("柜面", "ATM", "现金")
CROSS_TYPES = ("跨境", "结汇", "购汇")
IN_TX_TYPES = ("收入", "存入", "转入", "入账")
SENSITIVE_OCC = ("个体工商户", "贸易", "供应链", "投资", "咨询", "珠宝", "艺术品", "贵金属", "虚拟")
CASH_INTENSIVE_OCC = ("餐饮", "零售", "批发", "建材")

LEVELS = ((60, "高"), (35, "中"), (0, "低"))

# 一票升级口径：名单命中（R005）/ 客户身份不明（R017）属监管刚性情形，不受分值影响
OVERRIDE_RULES = ("R005", "R017")
# 正向（降风险）信号：真实经营证据 / 稳定代发
POSITIVE_TAGS = ("真实经营", "合同发票", "齐备", "固定工资", "工资代发", "在职")
STABLE_COUNTERPARTIES = ("税务局", "社保", "工资", "代发")


def _amt(t):
    return t.get("amount_cny") or t.get("amount") or 0


def _is_cash(t):
    ch = str(t.get("channel", ""))
    ty = str(t.get("type", ""))
    return any(k in ch for k in CASH_CHANNELS) or "现金" in ty


def _is_cross(t):
    ty = str(t.get("type", ""))
    return any(k in ty for k in CROSS_TYPES) or str(t.get("currency", "CNY")) != "CNY"


def _is_night(t):
    try:
        hour = int(str(t.get("time", "12:00")).split(":")[0])
    except (ValueError, IndexError):
        return False
    return hour >= 22 or hour < 6


def _is_in_tx(t):
    ty = str(t.get("type", ""))
    return any(k in ty for k in IN_TX_TYPES)


def _level(score):
    for threshold, name in LEVELS:
        if score >= threshold:
            return name
    return "低"


def _score_identity(ci, tags, txs, factors):
    score, base = 10, 10
    corp = "公司" in str(ci.get("name", "")) or "对公" in str(ci.get("name", ""))
    occ = str(ci.get("occupation", ""))
    tag_text = " ".join(tags)
    # 成立年限（对公）/ 职业行业敏感度（个人）
    if corp:
        years = _years_since(str(ci.get("open_date", "")))
        if 0 < years < 2:
            score += 40; factors.append(("对公客户成立不满 2 年", 40))
        elif years < 5:
            score += 20; factors.append(("对公客户成立 2–5 年", 20))
        else:
            score += 5; factors.append(("对公客户经营 5 年以上", 5))
    if any(k in occ for k in SENSITIVE_OCC):
        score += 25; factors.append((f"职业/行业属敏感类别（{occ}）", 25))
    elif any(k in occ for k in CASH_INTENSIVE_OCC):
        score += 15; factors.append((f"职业/行业属现金密集类别（{occ}）", 15))
    elif not corp:
        score += 5; factors.append(("职业背景相对稳定", 5))
    # 客户画像标签（客户信息携带的历史风险信号）
    if any(k in tag_text for k in ("无固定职业", "无固定收入", "自由职业")):
        score += 20; factors.append(("职业稳定性弱（无固定职业/收入）", 20))
    if "行为突变" in tag_text:
        score += 20; factors.append(("历史标签：行为突变", 20))
    if "无社保缴纳记录" in tag_text:
        score += 15; factors.append(("历史标签：无社保缴纳记录", 15))
    if "新开户" in tag_text or "新设公司" in tag_text:
        score += 10; factors.append(("历史标签：新开户/新设主体", 10))
    if "账户更换频繁" in tag_text:
        score += 10; factors.append(("历史标签：账户更换频繁", 10))
    if "不符" in tag_text and "收入" in tag_text:
        score += 20; factors.append(("历史标签：收入与交易规模严重不符", 20))
    if "累犯" in tag_text:
        score += 15; factors.append(("历史标签：累犯型账户", 15))
    # 正向信号：可验证的真实经营证据（用于对冲"新设对公"的基础扣分）
    if any(k in tag_text for k in POSITIVE_TAGS):
        score -= 20; factors.append(("已核实真实经营（合同/发票/代发等证据）", -20))
    cps_text = " ".join(str(t.get("counterparty", "")) for t in txs)
    if any(k in cps_text for k in STABLE_COUNTERPARTIES):
        score -= 10; factors.append(("交易对手含税务/工资/社保等稳定对象", -10))
    return max(min(score, base + 90), base)


def _years_since(ym):
    m = re.match(r"(\d{4})[-/]?(\d{1,2})?", ym.strip())
    if not m:
        return 99.0
    from datetime import date
    y, mo = int(m.group(1)), int(m.group(2) or 1)
    try:
        return (date.today() - date(y, mo, 1)).days / 365.25
    except ValueError:
        return 99.0


def _score_channel(txs, factors):
    score, base = 10, 10
    if not txs:
        return base
    cash_ratio = sum(1 for t in txs if _is_cash(t)) / len(txs)
    if cash_ratio >= 0.5:
        score += 40; factors.append((f"现金类渠道占比 {cash_ratio:.0%}", 40))
    elif cash_ratio >= 0.2:
        score += 25; factors.append((f"现金类渠道占比 {cash_ratio:.0%}", 25))
    elif cash_ratio > 0:
        score += 10; factors.append((f"存在少量现金渠道（{cash_ratio:.0%}）", 10))
    channels = {str(t.get("channel", "")) for t in txs if t.get("channel")}
    if len(channels) >= 3:
        score += 20; factors.append((f"交易渠道分散（{len(channels)} 种）", 20))
    elif len(channels) == 2:
        score += 10; factors.append((f"交易渠道 2 种", 10))
    third_party = sum(1 for t in txs if "第三方" in str(t.get("channel", ""))) / len(txs)
    if third_party >= 0.3:
        score += 15; factors.append((f"第三方支付占比 {third_party:.0%}", 15))
    return min(score, base + 90)


def _score_geo(txs, tags, factors):
    score, base = 10, 10
    if txs:
        cross_ratio = sum(1 for t in txs if _is_cross(t)) / len(txs)
        if cross_ratio >= 0.3:
            score += 45; factors.append((f"跨境/外币交易占比 {cross_ratio:.0%}", 45))
        elif cross_ratio > 0:
            score += 25; factors.append((f"存在跨境/外币交易（{cross_ratio:.0%}）", 25))
    if "跨境" in " ".join(tags):
        score += 10; factors.append(("历史标签：跨境业务", 10))
    return min(score, base + 90)


def _score_behavior(txs, rules_hit, tags, factors):
    score, base = 5, 5
    tag_text = " ".join(tags)
    if txs:
        night = sum(1 for t in txs if _is_night(t)) / len(txs)
        if night >= 0.3:
            score += 25; factors.append((f"夜间交易占比 {night:.0%}", 25))
        elif night >= 0.1:
            score += 12; factors.append((f"夜间交易占比 {night:.0%}", 12))
        if "凌晨操作" in tag_text:
            score += 15; factors.append(("历史标签：凌晨操作", 15))
        cash_ratio = sum(1 for t in txs if _is_cash(t)) / len(txs)
        if cash_ratio >= 0.5:
            score += 20; factors.append((f"现金交易类型占比 {cash_ratio:.0%}", 20))
        elif cash_ratio >= 0.2:
            score += 10; factors.append((f"现金交易类型占比 {cash_ratio:.0%}", 10))
        cps = {str(t.get("counterparty", "")) for t in txs if t.get("counterparty")}
        if cps and len(cps) / len(txs) >= 0.8:
            score += 15; factors.append((f"对手方高度分散（{len(cps)} 个 / {len(txs)} 笔）", 15))
        elif cps and len(cps) / len(txs) >= 0.5:
            score += 8; factors.append((f"对手方较分散（{len(cps)} 个 / {len(txs)} 笔）", 8))
        if "资金归集" in tag_text or "大量个人账户" in tag_text:
            score += 15; factors.append(("历史标签：资金归集/大量个人账户", 15))
        # 快进快出：当日转入与转出规模接近且金额巨大
        day_flow = {}
        for t in txs:
            day = str(t.get("date", ""))
            day_flow.setdefault(day, [0.0, 0.0])
            day_flow[day][0 if _is_in_tx(t) else 1] += _amt(t)
        pass_through = any(
            i >= 200000 and o >= 200000 and 0.8 <= (i / o if o else 0) <= 1.25
            for i, o in day_flow.values())
        if pass_through:
            score += 25; factors.append(("当日资金快进快出（转入即转出、规模相当）", 25))
        round_ratio = sum(1 for t in txs
                          if _amt(t) >= 10000 and _amt(t) % 10000 == 0) / len(txs)
        if round_ratio >= 0.3 or "整数单金额" in tag_text:
            score += 10; factors.append((f"整数金额占比 {round_ratio:.0%}", 10))
        # 虚拟货币/OTC 特征（附言、对手方、标签均可作为信号源）
        sig_text = tag_text + " " + " ".join(str(t.get("summary", "")) for t in txs) \
                   + " " + " ".join(str(t.get("counterparty", "")) for t in txs)
        if any(k in sig_text for k in ("USDT", "虚拟币", "数字货币", "OTC")):
            score += 20; factors.append(("虚拟货币/OTC 交易特征", 20))
    # 对公客户向个人账户密集转出
    name = tag_text
    if "公转私" in tag_text:
        score += 25; factors.append(("历史标签：公转私密集", 25))
    # 预警结果动态回写：规则命中直接计入行为维度（PRD §4.7）
    if rules_hit:
        pts = min(20 * len(rules_hit), 60)
        score += pts
        factors.append((f"本期预警命中 {len(rules_hit)} 条规则（动态回写）", pts))
    return min(score, base + 95)


def rate_case(case):
    """对单条案例计算四维评级。返回分数、明细、复评等级与升降级判断。"""
    ci = case.get("customer_info") or {}
    txs = case.get("transactions") or []
    tags = [str(t) for t in (ci.get("tags") or [])]
    rules_hit = case.get("rules_hit") or []

    f_id, f_ch, f_geo, f_bh = [], [], [], []
    identity = _score_identity(ci, tags, txs, f_id)
    channel = _score_channel(txs, f_ch)
    geo = _score_geo(txs, tags, f_geo)
    behavior = _score_behavior(txs, rules_hit, tags, f_bh)
    total = round(identity * 0.25 + channel * 0.20 + geo * 0.20 + behavior * 0.35, 1)

    # 监管一票升级：名单命中 / 身份不明，不参与分值讨论
    override = [r for r in rules_hit if r in OVERRIDE_RULES]
    if override:
        computed = "高"
        f_bh.append((f"一票升级：命中 {'、'.join(override)}（名单/身份类刚性情形）", 100))
    else:
        computed = _level(total)
    preset = str(ci.get("risk_level") or "—")
    order = {"低": 0, "中": 1, "高": 2}
    change = "维持"
    if preset in order and computed in order:
        if order[computed] > order[preset]:
            change = "升级"
        elif order[computed] < order[preset]:
            change = "下调"
    return {
        "case_id": case.get("case_id"),
        "customer": str(ci.get("name", "")).replace("（个人）", "").replace("（对公）", ""),
        "occupation": ci.get("occupation", "—"),
        "preset_level": preset,
        "computed_level": computed,
        "change": change,
        "edd": change == "升级" and computed == "高",
        "total": total,
        "scores": {"identity": identity, "channel": channel, "geo": geo, "behavior": behavior},
        "weights": {"identity": 0.25, "channel": 0.20, "geo": 0.20, "behavior": 0.35},
        "factors": {"identity": f_id, "channel": f_ch, "geo": f_geo, "behavior": f_bh},
    }
