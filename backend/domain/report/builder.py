"""可疑交易报告（STR）生成器。

依据人民银行令〔2016〕第 3 号附件《金融机构大额交易和可疑交易报告要素内容》
银行业口径 62 项要素，从案例数据 + 规则命中 + AI 诊断生成初稿。
要素定义来自 data/str_elements.json（见 domain/report/elements.py），本文件只负责取值与组织正文。

来源标注：
  system     —— 系统从客户信息/交易流水/规则结论直接带出
  ai         —— 仅第 21、22 项判断性内容由 AI 生成
  manual     —— 案例未采集、必须由专岗补充（留空，格式核对会拦截）
  synthetic  —— 演示预填：按案例编号确定性生成的合成脱敏值
  na         —— 本笔不适用

所有证件号、账号均为按案例编号确定性生成的合成脱敏值，不指向任何真实主体。

地域口径：机构编码 313100000001010（31=上海）、网点代码、行政区划、交易地点
统一取上海，不再一处一编。
"""
import hashlib
from datetime import date, datetime
from itertools import count

from ..rules.common import amt, is_in, purpose
from .deadline import add_workdays, holiday_count
from .elements import STR_ELEMS, STR_PART
from .text import build_text

_REPORT_SEQ = count(1)

IN_KW = ("收入", "存入", "转入", "入账")

# 演示机构所在地（与第 1 项报告机构编码 31=上海 保持一致）
DEMO_CITY = "上海"
DEMO_ADMIN_CODE = "310104"
DEMO_BRANCH_CODE = "SH0101"


def _is_in(t):
    return is_in(t)


def _digits(seed, n=4):
    h = hashlib.md5(seed.encode("utf-8")).hexdigest()
    return str(int(h, 16))[-n:].rjust(n, "0")


def _masked_id(seed, corp):
    return ("91" if corp else "6321") + "**********" + _digits(seed + "-id")


def _masked_account(seed, corp):
    return ("1010" if corp else "6222") + "**********" + _digits(seed + "-acct")


def _fmt(n):
    return f"{n:,.0f}"


def build_report(case, diagnosis, rule_hits, conn, report_date=None, diagnosis_origin="server"):
    # diagnosis_origin：第 21/22 项文本的实际来源——"server"（服务端 AI Provider 产出）
    # 或 "client"（调用方提交，可能含人工修订）。写入 meta 以便事后审计区分，
    # 避免"任何调用方文本都被标成 ai 产出"的证据语义混淆。
    ci = case["customer_info"]
    txs = case["transactions"]
    cid = case["case_id"]
    name = ci.get("name", "")
    corp = "公司" in name or "对公" in name
    open_date = ci.get("open_date", "—")
    today = (report_date or date.today()).strftime("%Y%m%d")

    ins = [t for t in txs if _is_in(t)]
    outs = [t for t in txs if not _is_in(t)]
    in_total = sum(amt(t) for t in ins)
    out_total = sum(amt(t) for t in outs)
    dates = sorted(t["date"] for t in txs) if txs else ["—"]
    start, end = dates[0], dates[-1]

    cp_count = {}
    for t in txs:
        cp = t.get("counterparty", "").strip()
        if cp and cp not in ("—", "本人"):
            cp_count[cp] = cp_count.get(cp, 0) + 1
    top_cp = max(cp_count, key=cp_count.get) if cp_count else "—"

    channels = []
    for t in txs:
        ch = t.get("channel", "").strip()
        if ch and ch not in channels:
            channels.append(ch)
    non_counter = [c for c in channels if c in ("网银", "手机银行", "ATM", "网上银行")]
    cross = any("跨境" in t["type"] for t in txs)

    points = diagnosis.get("analysis_points") or []
    numbered = "；".join(f"{'①②③④⑤⑥⑦⑧'[i] if i < 8 else str(i + 1)} {p}"
                        for i, p in enumerate(points)) or "—（AI 分析要点为空）"
    conclusion = diagnosis.get("conclusion", "人工复核")
    type_no = diagnosis.get("official_type_no") or case.get("official_type_no") or "—"
    type_name = diagnosis.get("official_type_name") or case.get("official_type_name") or "—"
    risk = ci.get("risk_level", "—")
    occupation = ci.get("occupation", "—")

    rules = []
    for rid in case.get("rules_hit", []):
        r = conn.execute(
            "SELECT rule_id, name, crime_code, crime_name FROM rules WHERE rule_id=?", (rid,)
        ).fetchone()
        if r:
            rules.append(dict(r))
    hit_ids = [h["rule_id"] for h in rule_hits] or [r["rule_id"] for r in rules]
    hit_names = [h["rule_name"] for h in rule_hits] or [r["name"] for r in rules]
    crime = next((r for r in rules if r.get("crime_code")), None)
    if not crime:
        for h in rule_hits:
            if h.get("crime_code"):
                crime = h
                break

    trig = "；".join(f"{rid} {nm}" for rid, nm in zip(hit_ids, hit_names)) or "—（未命中监测规则）"
    crime_text = (f"{crime.get('crime_code', '')} {crime.get('crime_name', '')}".strip()
                  if crime else "")

    account_type = "对公基本存款账户" if corp else "个人银行结算账户（Ⅰ 类户）"
    cp_corp = "公司" in top_cp or "贸易" in top_cp
    city, admin = DEMO_CITY, DEMO_ADMIN_CODE
    # 客户明确未提供证件（如拒不出示身份证件，11 号令第四十一条（一））：
    # 证件类型/号码如实留空由专岗处理，不拿合成值冒充"已采集"
    id_missing = ("id_no" in ci and not str(ci.get("id_no") or "").strip())
    id_type_val = "" if id_missing else ("统一社会信用代码" if corp else "居民身份证")
    id_no_val = "" if id_missing else (_masked_id(cid, corp) + "（合成）")
    id_source = "manual" if id_missing else ("system" if id_type_val else "manual")
    values = {
        1: ("313100000001010", "system"),
        2: (f"{DEMO_BRANCH_CODE} · 清源演示{DEMO_CITY}分行营业部", "system"),
        3: (f"{'对公基本存款账户' if corp else '个人银行结算账户'}业务关系"
            f"（{open_date} 开户，存续至今）", "system"),
        4: (name, "system"),
        5: (id_type_val, id_source),
        6: (id_no_val, "manual" if id_missing else "synthetic"),
        7: ("C" + open_date.replace("-", "") + _digits(cid, 4), "synthetic"),
        8: (occupation, "system"),
        9: (f"138****{_digits(cid + '-tel')}；{city}市××路××号（合成）", "synthetic"),
        16: ("中国", "system"),
        17: ("01 非特别紧急", "system"),
        18: ("1（初次报告）", "system"),
        19: ("01 报告中国反洗钱监测分析中心", "system"),
        20: ("01 模型筛选", "system"),
        21: (f"{start} 至 {end}，共 {len(txs)} 笔交易，累计转入/存入 {_fmt(in_total)} 元、"
             f"转出/支取 {_fmt(out_total)} 元，主要交易对手为 {top_cp}，"
             f"渠道涉及 {'、'.join(channels) or '—'}。"
             + (f"{points[0]}" if points else ""), "ai"),
        22: (numbered, "ai"),
        23: (crime_text or "—（未命中规则，无需报送）", "system" if crime else "na"),
        24: ("", "manual"),  # 可疑交易特征代码：官方代码集未接入，留空由专岗补充，不做兜底填充
        25: (name, "system"),
        26: (id_type_val, id_source),
        27: (id_no_val, "manual" if id_missing else "synthetic"),
        28: (account_type, "system"),
        29: (open_date, "system"),
        30: ("—（未销户）", "na"),
        31: (_masked_account(cid, corp) + "（合成）", "synthetic"),
        32: ("—（对公账户不适用）" if corp else "借记卡", "na" if corp else "system"),
        33: ("—（对公账户不适用）" if corp else _masked_account(cid, corp) + "（合成）",
             "na" if corp else "synthetic"),
        34: ("—（无代办人）", "na"), 35: ("—（无代办人）", "na"),
        36: ("—（无代办人）", "na"), 37: ("—（无代办人）", "na"),
        38: (f"{start} 至 {end}（共 {len(txs)} 笔）", "system"),
        39: (f"{city}市（演示）", "synthetic"),
        40: ("BUS" + today + _digits(cid, 4), "system"),
        41: ("01 交易流水号", "system"),
        42: ("TR" + today + _digits(cid + "tr", 6), "system"),
        43: ("、".join(channels) or "—", "system"),
        44: ("跨境收支（分类代码 121010，演示预填）" if cross else "—（非涉外收支）",
             "synthetic" if cross else "na"),
        45: (f"收（转入/存入 {len(ins)} 笔）/ 付（转出/支取 {len(outs)} 笔）", "system"),
        46: ("；".join(sorted({purpose(t) for t in txs if purpose(t)}))
             or "；".join(sorted({t["summary"] for t in txs if t.get("summary")}))
             or "客户未提供资金用途说明（演示预填）",
             "system" if any(purpose(t) or t.get("summary") for t in txs) else "synthetic"),
        47: ("人民币 CNY", "system"),
        # 交易金额 = 报告期内转入/存入与转出/支取的累计合计（双向流水合计，非净额头寸）；
        # 同一笔资金的流入与流出分别计量，口径见报告要素说明
        48: (f"{in_total + out_total:.2f}", "system"),
        49: (f"清源演示银行{city}分行营业部（合成）", "synthetic"),
        50: ("01 人民银行金融机构代码", "synthetic"),
        51: (f"B0032{admin}0{_digits(cid + '-bank')}", "synthetic"),
        52: (admin, "synthetic"),
        53: (top_cp, "system" if top_cp != "—" else "synthetic"),
        54: ("统一社会信用代码" if cp_corp else "居民身份证", "synthetic"),
        55: (_masked_id(cid + "-cp", cp_corp) + "（合成）", "synthetic"),
        56: ("对公基本存款账户" if cp_corp else "个人银行结算账户", "synthetic"),
        57: (_masked_account(cid + "-cp", cp_corp) + "（合成）", "synthetic"),
        58: ("、".join(non_counter) if non_counter else "—（仅柜面交易）",
             "system" if non_counter else "na"),
        59: ("—（演示案例无设备代码）", "na"),
        60: ("—（非银行与支付机构间交易）", "na"),
        61: (f"脱敏合成演示案例；规则引擎命中 {'、'.join(hit_ids) or '无'}；"
             f"AI 诊断结论「{conclusion}」；本报告 62 项要素中第 21、22 项由 AI 生成，须专岗复核。",
             "system"),
        62: ("—", "na"),
    }

    if corp:
        legal = f"{name[:1]}某（合成）"
        for n in (10, 13):
            values[n] = (legal, "synthetic")
        for n in (11, 14):
            values[n] = ("居民身份证", "synthetic")
        for n in (12, 15):
            values[n] = (_masked_id(cid + "-legal", False) + "（合成）", "synthetic")
    else:
        for n in (10, 11, 12, 13, 14, 15):
            values[n] = ("—（个人账户不适用）", "na")

    elements = []
    counts = {"system": 0, "synthetic": 0, "ai": 0, "manual": 0, "na": 0}
    for no, part, elem_name in STR_ELEMS:
        value, source = values.get(no, ("—（待人工补充）", "manual"))
        counts[source] += 1
        elements.append({"no": no, "part": part, "part_name": STR_PART[part],
                         "name": elem_name, "value": value, "source": source})

    cn, en = build_text({
        "name": name, "age": ci.get("age", "—"), "occupation": occupation,
        "open_date": open_date, "risk": risk, "start": start, "end": end,
        "tx_count": len(txs), "in_total": in_total, "out_total": out_total,
        "top_cp": top_cp, "channel_text": "、".join(channels) or "—",
        "numbered": numbered, "trig": trig, "conclusion": conclusion,
        "type_no": type_no, "type_name": type_name, "hit_ids": hit_ids,
    })

    now = datetime.now()
    found = date.today()
    n_holidays = holiday_count()
    deadline_note = ("发现之日起 5 个工作日内（跳过周末"
                     + (f"与 {n_holidays} 个法定节假日/调休工作日， holidays.json 已配置）"
                        if n_holidays else "；未配置法定节假日——请补 backend/data/holidays.json）"))
    return {
        "case_id": cid,
        "title": case["title"],
        "report_no": (f"STR-{now.strftime('%Y%m%d')}-{cid}-{now.strftime('%H%M%S')}"
                      f"{now.microsecond//1000:03d}{next(_REPORT_SEQ):04d}"),
        "generated_at": now.strftime("%Y-%m-%d %H:%M:%S"),
        "found_date": found.isoformat(),
        "filing_deadline": add_workdays(found, 5).isoformat(),
        "deadline_note": deadline_note,
        "parts": [{"part": p, "name": STR_PART[p]} for p in (1, 2, 3, 4)],
        "elements": elements,
        "counts": counts,
        "total": len(elements),
        "cn": cn,
        "en": en,
        "meta": {"customer": name, "rules": hit_ids, "conclusion": conclusion,
                 "official_type_no": type_no, "official_type_name": type_name,
                 "diagnosis_origin": diagnosis_origin},
    }
