"""新交易接入：规则筛选 → 案例召回 → 建议路径。

规则未命中不等于合规放行，只表示未触发已知模式；仍需轻量筛查或抽样复核。

输入契约（_normalize 负责把外部输入收敛成引擎可消费的结构，收敛不了就 422）：
- date        接受 YYYY-MM-DD / YYYY/M/D 等写法，统一归一化为 ISO
- amount      接受数字或纯数字字符串，统一转 float；必须 > 0（0/负数/非数字 → 422）
- counterparty 缺失时补占位符"—"，不让下游规则因缺列崩溃
- purpose/type/summary 三个字段分治：交易类型 / 用途 / 客户附言，不混用
- currency    3 位字母代码（CNY/USD/EUR）；外币必须给 amount_cny（折人民币）
- 单次最多接入 MAX_TRANSACTIONS 笔，防止超大请求把单进程服务拖住
"""
import re
import uuid

from domain.rules import run_engine
from domain.rules.common import parse_date, parse_open_date
from services.similar_cases import similar_for_case

MAX_TRANSACTIONS = 500
MAX_TEXT_LEN = 200


class IntakeValidationError(ValueError):
    pass


def _normalize(payload):
    ci = payload.get("customer_info")
    txs = payload.get("transactions")
    if not isinstance(ci, dict) or not ci:
        raise IntakeValidationError("customer_info 不能为空")
    if not isinstance(txs, list) or not txs:
        raise IntakeValidationError("transactions 不能为空")
    if len(txs) > MAX_TRANSACTIONS:
        raise IntakeValidationError(f"单次最多接入 {MAX_TRANSACTIONS} 笔交易（收到 {len(txs)} 笔）")

    for index, tx in enumerate(txs):
        if not isinstance(tx, dict):
            raise IntakeValidationError(f"第 {index + 1} 笔交易不是对象")
        for key in ("date", "type", "amount"):
            if key not in tx:
                raise IntakeValidationError(f"第 {index + 1} 笔交易缺少 {key}")
        if not isinstance(tx["type"], str) or not tx["type"].strip():
            raise IntakeValidationError(f"第 {index + 1} 笔交易 type 不能为空")

        iso = parse_date(tx["date"])
        if not iso:
            raise IntakeValidationError(
                f"第 {index + 1} 笔交易日期格式应为 YYYY-MM-DD（收到：{tx['date']}）")
        tx["date"] = iso

        amount = tx["amount"]
        if isinstance(amount, bool):
            raise IntakeValidationError(f"第 {index + 1} 笔交易金额不是数字")
        try:
            amount = float(amount)
        except (TypeError, ValueError):
            raise IntakeValidationError(f"第 {index + 1} 笔交易金额不是数字（收到：{tx['amount']}）")
        if amount != amount or amount in (float("inf"), float("-inf")):
            raise IntakeValidationError(f"第 {index + 1} 笔交易金额不是有限数字")
        if amount <= 0:
            raise IntakeValidationError(f"第 {index + 1} 笔交易金额必须大于 0")
        tx["amount"] = amount

        # 对手方缺失 → 占位符；附言/渠道/用途截断，防止超长文本
        cp = tx.get("counterparty")
        tx["counterparty"] = (cp.strip()[:MAX_TEXT_LEN] if isinstance(cp, str) else "—") or "—"
        for key in ("summary", "channel", "time", "purpose", "type"):
            if key in tx and isinstance(tx[key], str):
                tx[key] = tx[key][:MAX_TEXT_LEN]
        # 用途与附言是不同字段：用途=交易摘要/业务用途，附言=客户备注；缺省都为空
        tx.setdefault("purpose", "")
        # 币种与折人民币金额：外币交易应显式给 amount_cny；只给 amount 时视为人民币
        cur = tx.get("currency") or "CNY"
        if not isinstance(cur, str) or not re.fullmatch(r"[A-Za-z]{3}", cur.strip()):
            raise IntakeValidationError(f"第 {index + 1} 笔交易币种应为 3 位字母代码（如 CNY/USD/EUR）")
        cur = cur.strip().upper()
        tx["currency"] = cur
        cny = tx.get("amount_cny")
        if cny in (None, ""):
            tx["amount_cny"] = tx["amount"]
        else:
            try:
                cny_val = float(cny)
            except (TypeError, ValueError):
                raise IntakeValidationError(f"第 {index + 1} 笔交易折人民币金额不是数字")
            if cny_val <= 0:
                raise IntakeValidationError(f"第 {index + 1} 笔交易折人民币金额必须大于 0")
            tx["amount_cny"] = cny_val
        if cur != "CNY" and tx["amount_cny"] == tx["amount"]:
            raise IntakeValidationError(
                f"第 {index + 1} 笔交易为 {cur}，必须提供 amount_cny（折人民币金额）")
        tm = tx.get("time")
        if tm:
            if not isinstance(tm, str):
                raise IntakeValidationError(
                    f"第 {index + 1} 笔交易时间格式应为 HH:MM（收到：{tm}）")
            try:
                hh, mm = tm.strip().split(":")
                if not (0 <= int(hh) <= 23 and 0 <= int(mm) <= 59):
                    raise ValueError
                tx["time"] = f"{int(hh):02d}:{int(mm):02d}"
            except ValueError:
                raise IntakeValidationError(
                    f"第 {index + 1} 笔交易时间格式应为 HH:MM（收到：{tm}）")

    if "open_date" in ci and ci["open_date"]:
        raw = str(ci["open_date"]).strip()
        od = parse_open_date(raw)
        if not od:
            raise IntakeValidationError(
                f"customer_info.open_date 格式应为 YYYY-MM 或 YYYY-MM-DD（收到：{ci['open_date']}）")
        # 保留原始精度：月份写法归一为 YYYY-MM，完整日期归一为 YYYY-MM-DD
        ci["open_date"] = od.strftime("%Y-%m") if len(raw) <= 7 else od.strftime("%Y-%m-%d")

    return {
        "case_id": payload.get("case_id") or ("NEW-" + uuid.uuid4().hex[:8].upper()),
        "title": payload.get("title") or "新交易研判",
        "category": "grey",
        "expected_conclusion": "待研判",
        "customer_info": ci,
        "transactions": txs,
        "rules_hit": [],
        "trace_chain": [],
        "grey_zone": {},
    }


def _route(rule_hits, similar):
    if any(h["rule_id"] == "R005" for h in rule_hits):
        return {"decision": "拦截", "path": "名单拦截",
                "reason": "命中制裁/涉恐名单，立即冻结，不经 AI 诊断",
                "next_step": "24 小时内人工核验主体唯一性"}

    if any(h["rule_id"] == "R017" for h in rule_hits):
        return {"decision": "拦截", "path": "身份不明拒办",
                "reason": "客户身份不明/证件缺失：不得为其提供服务或与其交易"
                          "（反洗钱法第28条、11号令第8条），不属于制裁名单命中",
                "next_step": "前台拒办拒交易；按 11 号令第四十一条（一）作为 CDD 条线可疑行为报送"}

    top = (similar.get("results") or [None])[0]
    if rule_hits:
        if top and top["band"] == "高度相似":
            return {"decision": "人工复核", "path": "规则命中 + 案例高度相似",
                    "reason": f"命中 {len(rule_hits)} 条规则；与历史案例 {top['case_id']} "
                              f"相似度 {top['score_percent']}%，属同类已定性案例",
                    "next_step": "转人工复核；确认后按人工结论决定是否报送"}
        if top and top["band"] == "参考相似":
            return {"decision": "人工复核", "path": "规则命中 + 案例参考",
                    "reason": f"命中 {len(rule_hits)} 条规则；历史案例 {top['case_id']} "
                              f"相似度 {top['score_percent']}%，可作参考但不足以直接定性",
                    "next_step": "把相似案例作为证据，交 AI 二次研判后转人工确认"}
        return {"decision": "人工复核", "path": "规则命中",
                "reason": f"命中 {len(rule_hits)} 条规则，历史案例不足以支撑直接定性",
                "next_step": "交 AI 独立研判，再转人工确认"}

    return {"decision": "放行候选", "path": "规则未命中",
            "reason": "未触发已知监测模式，仅代表规则未命中，不等于合规放行",
            "next_step": "轻量筛查或抽样复核后再放行，并保留未命中记录"}


def screen_new_case(payload, conn):
    case = _normalize(payload)
    rule_hits = run_engine(case["transactions"], case["customer_info"], conn)
    similar = similar_for_case(case, conn)
    return {
        "case_id": case["case_id"],
        "title": case["title"],
        "rule_hits": rule_hits,
        "similar_cases": similar,
        "route": _route(rule_hits, similar),
    }
