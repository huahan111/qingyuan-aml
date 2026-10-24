"""规则执行入口：按注册表执行，回填规则元数据。"""
from . import base_rules, cdd_rules, typed_rules  # noqa: F401  导入即注册
from .common import load_rules
from .registry import RULE_FUNCS


def run_engine(txs, cust, conn):
    """跑全部基础规则，返回命中列表"""
    rules = load_rules(conn)
    hits = []
    for rid, meta in rules.items():
        fn = RULE_FUNCS.get(rid)
        if not fn:
            continue
        result = fn(txs, cust, meta["params"])
        if result and result.get("triggered"):
            row = conn.execute(
                "SELECT name, official_type_no, official_type_name, crime_code, crime_name, penalty_ref, legal_desc FROM rules WHERE rule_id=?",
                (rid,)).fetchone()
            hits.append({
                "rule_id": rid, "rule_name": row[0],
                "official_type_no": row[1], "official_type_name": row[2],
                "crime_code": row[3], "crime_name": row[4],
                "penalty_ref": row[5], "legal_desc": row[6],
                "trigger_desc": result["desc"],
                "params_found": result["params_found"],
            })
    return hits
