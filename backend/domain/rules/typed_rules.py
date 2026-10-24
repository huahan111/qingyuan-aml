"""类型化规则 R009–R016：目前仅 R009 有可执行实现，其余需外部数据。"""
from .common import amt, is_in, is_out
from .registry import rule

@rule("R009")
def check_r009(txs, cust, params):
    """分散多源小额转入 → 集中转出 → 向多对手方固定比例分散返款"""
    ins = [t for t in txs if is_in(t)]
    outs = [t for t in txs if is_out(t)]
    if len(ins) < params["collect_min_count"]:
        return None
    in_cps = {t["counterparty"] for t in ins}
    if len(in_cps) < params.get("min_in_counterparties", 3):  # 至少 N 个不同转入方才算"分散"
        return None
    # 转入金额趋同（基数倍数关系）；金额含 0 或负数时无法计算倍数，直接不命中
    amounts = [amt(t) for t in ins]
    if min(amounts) <= 0:
        return None
    if max(amounts) / min(amounts) > params.get("amount_spread_max", 3):
        return None
    # 集中转出 + 分散返款（多个不同对手方）
    out_cps = {t["counterparty"] for t in outs}
    concentrated = any(amt(o) >= sum(amounts) * params.get("concentrated_ratio", 0.5)
                       for o in outs)
    dispersed_back = (len(out_cps) >= params.get("min_out_counterparties", 3)
                      and len(outs) >= params.get("min_out_count", 3))
    if concentrated or dispersed_back:
        return {"triggered": True,
                "desc": f"三段式资金结构：{len(in_cps)}个不同对手方分散转入{len(ins)}笔（单笔{min(amounts):,.0f}–{max(amounts):,.0f}元，呈基数倍数），"
                        f"随后{'集中转出' if concentrated else ''}{'并向' + str(len(out_cps)) + '个账户分散转出' if dispersed_back else ''}",
                "params_found": {"in_counterparties": len(in_cps), "in_count": len(ins),
                                 "out_counterparties": len(out_cps),
                                 "concentrated_out": concentrated, "dispersed_back": dispersed_back}}
    return None
