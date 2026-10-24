"""基础规则 R001–R008：阈值全部来自 rules.params。"""
from bisect import bisect_left
from collections import defaultdict
from datetime import datetime, timedelta

from .common import (CASH_IN, CASH_TYPES, CROSS_TYPES, TRANSFER_IN, amt, is_in,
                     is_out, parse_dt, parse_open_date, purpose, tx_type)
from .registry import rule
from .sanctions import MOCK_SANCTION_LIST

@rule("R001")
def check_r001(txs, cust, params):
    th = params["cash_threshold"]
    by_day = defaultdict(float)
    for t in txs:
        if tx_type(t) in CASH_TYPES:
            by_day[t["date"]] += amt(t)
    hit_days = {d: a for d, a in by_day.items() if a >= th}
    if hit_days:
        return {"triggered": True,
                "desc": f"单日现金交易达{th/10000:.0f}万元标准：{', '.join(f'{d}={a/10000:.2f}万' for d, a in hit_days.items())}",
                "params_found": hit_days}
    return None


@rule("R002")
def check_r002(txs, cust, params):
    win, min_cnt = params["window_days"], params["min_count"]
    rmin, rmax = params["ratio_min"], params["ratio_max"]
    dispersion_max = params.get("dispersion_max", 1.5)
    span_multiple = params.get("span_window_multiple", 2)
    # 双通道：现金与自然人境内转账分别检测贴线分拆，阈值来自 rules.params
    for label, types, th in [
        ("现金", CASH_IN, params.get("cash_threshold", 50000)),
        ("转账", TRANSFER_IN, params.get("transfer_threshold", 500000)),
    ]:
        sel = [t for t in txs if tx_type(t) in types]
        if len(sel) < min_cnt:
            continue
        dates = sorted({t["date"] for t in sel})
        span = (datetime.strptime(dates[-1], "%Y-%m-%d") - datetime.strptime(dates[0], "%Y-%m-%d")).days
        if span > win * span_multiple:  # 跨度过长不构成"集中分拆"
            continue
        amounts = [amt(t) for t in sel]
        in_band = [a for a in amounts if th * rmin <= a <= th * rmax]
        if len(in_band) < min_cnt:
            continue
        dispersion = max(amounts) / min(amounts) if min(amounts) > 0 else 999
        if dispersion > dispersion_max:  # 金额差异过大，不像刻意贴线
            continue
        return {"triggered": True,
                "desc": f"{label}通道{len(sel)}笔交易处于大额标准{rmin*100:.0f}%–{rmax*100:.0f}%贴线区间"
                        f"（单笔{min(amounts)/10000:.2f}–{max(amounts)/10000:.2f}万，{span}天内合计{sum(amounts)/10000:.1f}万），金额高度趋同",
                "params_found": {"channel": label, "count": len(sel), "min": min(amounts),
                                 "max": max(amounts), "total": sum(amounts), "dispersion": round(dispersion, 2)}}
    return None


@rule("R003")
def check_r003(txs, cust, params):
    days, ratio = params["out_within_days"], params["out_ratio"]
    min_cp, bal_max = params["min_counterparties"], params["balance_ratio_max"]
    ins = [t for t in txs if is_in(t)]
    outs = [t for t in txs if is_out(t)]
    if not ins or not outs:
        return None
    total_in = sum(amt(t) for t in ins)
    if total_in <= 0:
        return None
    # 转出比例 = 发生在"某笔转入后 N 天内"的转出合计 / 转入合计。
    # 每笔转出只按自身金额计一次（不再与转入逐笔配对），同一笔转出不会被多笔转入重复累加；
    # 转出合计以转入合计为上限（全部转出 = 100%）。
    in_dts = sorted(parse_dt(t) for t in ins)
    window = timedelta(days=days)
    quick_out = 0.0
    for o in outs:
        do = parse_dt(o)
        i = bisect_left(in_dts, do - window)
        if i < len(in_dts) and in_dts[i] <= do:
            quick_out += amt(o)
    quick_out = min(quick_out, total_in)
    out_r = quick_out / total_in
    out_cps = {t["counterparty"] for t in outs}
    if out_r >= ratio and len(out_cps) >= min_cp:
        bal_ratio = abs(total_in - quick_out) / total_in if total_in else 1
        return {"triggered": True,
                "desc": f"资金快进快出：转入{total_in/10000:.0f}万后{days}天内转出{quick_out/10000:.0f}万（{out_r*100:.0f}%），"
                        f"涉及{len(out_cps)}个转出对手方，余额占比{bal_ratio*100:.0f}%",
                "params_found": {"total_in": total_in, "quick_out": quick_out, "out_ratio": round(out_r, 2),
                                 "out_counterparties": len(out_cps), "balance_ratio": round(bal_ratio, 2)}}
    return None


@rule("R004")
def check_r004(txs, cust, params):
    ns, ne = params["night_start"], params["night_end"]
    nratio, mdays, mcount = params["night_ratio"], params["min_days"], params["min_count_per_day"]
    night_count, total = 0, len(txs)
    by_day = defaultdict(int)
    for t in txs:
        tm = t.get("time", "12:00")
        hh = int(tm.split(":")[0])
        if hh >= int(ns.split(":")[0]) or hh < int(ne.split(":")[0]):
            night_count += 1
            by_day[t["date"]] += 1
    if total == 0:
        return None
    ratio = night_count / total
    hit_days = sum(1 for v in by_day.values() if v >= mcount)
    if ratio >= nratio and hit_days >= mdays:
        return {"triggered": True,
                "desc": f"夜间（{ns}–次日{ne}）交易占比{ratio*100:.0f}%（{night_count}/{total}笔），"
                        f"{hit_days}天夜间交易≥{mcount}笔，超'频繁'标准",
                "params_found": {"night_ratio": round(ratio, 2), "hit_days": hit_days, "total": total}}
    return None


@rule("R005")
def check_r005(txs, cust, params):
    # 名单匹配只做"名单项 ⊆ 客户名/对手方"的单向包含；客户名称为空或过短时不予匹配
    #（空串是任何字符串的子串，历史上因此把无姓名客户误判为命中名单——身份不明走 R017）。
    name = (cust.get("name") or "").strip()
    if len(name) >= 2:
        for s in MOCK_SANCTION_LIST:
            if s in name:
                return {"triggered": True,
                        "desc": f"客户名称命中制裁/涉恐名单（模拟匹配：{s}），应立即冻结并24小时内复核",
                        "params_found": {"matched": s}}
    # 交易对手方命中
    for t in txs:
        cp = (t.get("counterparty") or "").strip()
        if len(cp) < 2:
            continue
        for s in MOCK_SANCTION_LIST:
            if s in cp:
                return {"triggered": True,
                        "desc": f"交易对手方「{t['counterparty']}」命中制裁/涉恐名单",
                        "params_found": {"matched": s, "counterparty": t["counterparty"]}}
    return None


@rule("R006")
def check_r006(txs, cust, params):
    age_days = params["account_age_days"]
    th_nat, th_corp = params["cross_border_natural"], params["cross_border_corp"]
    open_date = cust.get("open_date", "2000-01")
    od = parse_open_date(open_date)
    if od is None:
        return None  # 开户日期无法解析时不臆测账户年龄
    is_corp = "对公" in cust.get("name", "") or "公司" in cust.get("name", "") or cust.get("type") == "对公"
    th = th_corp if is_corp else th_nat
    cross = [t for t in txs if tx_type(t) in CROSS_TYPES]
    if not cross:
        return None
    first_tx = min(parse_dt(t) for t in cross)
    if (first_tx - od).days > age_days:
        return None
    early_ratio = params.get("early_warning_ratio", 0.8)
    big = [t for t in cross if amt(t) >= th * early_ratio]
    if big:
        total = sum(amt(t) for t in cross)
        return {"triggered": True,
                "desc": f"开户{age_days}天内发生跨境交易{len(cross)}笔（累计{total/10000:.1f}万），"
                        f"单笔最高{max(amt(t) for t in cross)/10000:.1f}万接近申报标准{th/10000:.0f}万",
                "params_found": {"account_age_days": (first_tx - od).days, "cross_count": len(cross),
                                 "max_amount": max(amt(t) for t in cross), "threshold": th}}
    return None


# 对公主体常见字号：用于区分"对手方是机构还是个人"
_CORP_KW = ("公司", "企业", "厂", "店", "中心", "银行", "集团", "商行", "事业部", "合作社", "事务所", "局", "院", "校")


def _looks_corp(name: str) -> bool:
    return any(k in name for k in _CORP_KW)


@rule("R007")
def check_r007(txs, cust, params):
    """对公账户向个人账户高频转出（空壳特征）：客户为对公主体，且对手方为个人特征。"""
    m_trans = params["monthly_transfers"]
    is_corp = ("对公" in cust.get("name", "") or "公司" in cust.get("name", "")
               or cust.get("type") == "对公")
    if not is_corp:
        return None
    by_month = defaultdict(int)
    corp_to_person = 0
    for t in txs:
        if not is_out(t):
            continue
        cp = (t.get("counterparty") or "").strip()
        if not cp or cp in ("本人", "—") or _looks_corp(cp):
            continue  # 对手方是机构/占位符，不构成"对公转个人"
        ym = t["date"][:7]
        by_month[ym] += 1
        corp_to_person += 1
    if corp_to_person == 0:
        return None
    months = [m for m, c in by_month.items() if c >= m_trans]
    if months:
        return {"triggered": True,
                "desc": f"对公账户向个人账户高频转出：{corp_to_person}笔（月均{corp_to_person/max(len(by_month),1):.0f}笔），"
                        f"涉嫌通过个人账户转移公司资金（空壳特征）",
                "params_found": {"corp_to_person": corp_to_person, "months": months}}
    return None


@rule("R008")
def check_r008(txs, cust, params):
    kws = params["keywords"]
    for t in txs:
        text = (t.get("summary") or "") + purpose(t) + (t.get("counterparty") or "")
        for k in kws:
            if k in text:
                return {"triggered": True,
                        "desc": f"交易附言/对手方含虚拟货币关键词「{k}」，涉嫌参与虚拟货币OTC交易",
                        "params_found": {"keyword": k, "tx": t["date"]}}
    # 金额呈固定整数倍特征（限小额：真实 OTC 多为几千至几万的整数单）
    mult = params.get("amount_multiple", 1000)
    lo, hi = params.get("amount_min", 5000), params.get("amount_max", 50000)
    need = params.get("min_count", 5)
    amounts = [amt(t) for t in txs if amt(t) % mult == 0 and lo <= amt(t) <= hi]
    if len(amounts) >= need:
        return {"triggered": True,
                "desc": f"{len(amounts)}笔交易金额为{mult}元整数倍，符合虚拟货币OTC交易金额特征",
                "params_found": {"count": len(amounts), "multiple": mult}}
    return None
