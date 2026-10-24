"""案例库与规则库联动：合并、反哺、覆盖与有效性统计。"""
import json
import os
import re
from datetime import datetime

from case_store import load_dataset
from domain.rules import RULE_FUNCS
from infra import case_repo

_TYPES_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "data", "official_types.json")

# 覆盖矩阵"无法归类"出口行的编号（official_types.json 中 no="—"）
EXIT_NO = "—"


def _type_code(value):
    m = re.search(r"第([0-9]+(?:-[0-9]+)?)类", value or "")
    return m.group(1) if m else ""


def _conclusion(case):
    return case.get("final_conclusion") or case.get("expected_conclusion") or "人工复核"


def merge_cases(conn):
    """演示案例 + 已定性案例库；同一来源案例以已定性条目替换。"""
    demo = {c["case_id"]: c for c in load_dataset()["cases"]}
    for entry in case_repo.list_library(conn):
        src = entry.get("source_case_id") or ""
        if src in demo:
            demo.pop(src)
        demo[entry["case_id"]] = entry
    return list(demo.values())


def promote_submission(conn, submission_id):
    """把已报送报告沉淀为已定性案例；缺少原始交易数据时跳过。"""
    from services.submissions import get as get_submission
    sub = get_submission(conn, submission_id)
    report = sub.get("report") or {}
    meta = report.get("meta") or {}
    source_case_id = sub["case_id"]
    original = None
    for case in load_dataset()["cases"]:
        if case["case_id"] == source_case_id:
            original = case
            break
    if not original or not original.get("transactions"):
        return {"promoted": False, "reason": "缺少原始交易数据，未入库"}

    conclusion = meta.get("conclusion") or "人工复核"
    category = {"拦截": "intercept", "放行": "pass"}.get(conclusion, "grey")
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    case = {
        "case_id": "LIB-" + sub["report_no"],
        "title": sub.get("case_title") or original["title"],
        "category": category,
        "customer_info": original["customer_info"],
        "transactions": original["transactions"],
        "expected_conclusion": conclusion,
        "rules_hit": meta.get("rules") or original.get("rules_hit") or [],
        "official_type_no": meta.get("official_type_no") or original.get("official_type_no", ""),
        "official_type_name": meta.get("official_type_name") or original.get("official_type_name", ""),
        "trace_chain": original.get("trace_chain") or [],
        "grey_zone": original.get("grey_zone") or {},
        "source": "submission",
        "source_case_id": source_case_id,
        "final_conclusion": conclusion,
        "report_no": sub["report_no"],
        "receipt_no": sub["receipt_no"],
        "created_at": now,
        "updated_at": now,
    }
    case_repo.upsert(conn, case)
    conn.commit()
    return {"promoted": True, "library_case_id": case["case_id"], "conclusion": conclusion}


def record_disposition(conn, case, conclusion, reason="", operator=""):
    """人工确认结论沉淀为案例库条目；放行结论即负样本。"""
    if conclusion not in ("放行", "拦截", "人工复核"):
        raise ValueError("conclusion 必须是 放行 / 拦截 / 人工复核")
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    category = {"放行": "pass", "拦截": "intercept"}.get(conclusion, "grey")
    entry = {
        "case_id": "DIS-" + case["case_id"],
        "title": case["title"] + (f"（人工确认{conclusion}）" if conclusion else ""),
        "category": category,
        "customer_info": case.get("customer_info") or {},
        "transactions": case.get("transactions") or [],
        "expected_conclusion": conclusion,
        "rules_hit": case.get("rules_hit") or [],
        "official_type_no": case.get("official_type_no", ""),
        "official_type_name": case.get("official_type_name", ""),
        "trace_chain": case.get("trace_chain") or [],
        "grey_zone": case.get("grey_zone") or {},
        "source": "disposition",
        "source_case_id": case["case_id"],
        "final_conclusion": conclusion,
        "report_no": "",
        "receipt_no": "",
        "audit": {"type": "人工确认", "reason": reason, "operator": operator, "at": now},
        "created_at": now,
        "updated_at": now,
    }
    case_repo.upsert(conn, entry)
    conn.commit()
    return {"library_case_id": entry["case_id"], "conclusion": conclusion,
            "source": "disposition"}


def backfill(conn):
    rows = conn.execute("SELECT id FROM submissions ORDER BY id").fetchall()
    promoted, skipped = 0, 0
    for row in rows:
        result = promote_submission(conn, row[0])
        if result.get("promoted"):
            promoted += 1
        else:
            skipped += 1
    return {"submissions": len(rows), "promoted": promoted, "skipped": skipped}


def coverage(conn):
    with open(_TYPES_PATH, encoding="utf-8") as f:
        types = json.load(f)["types"]
    cases = merge_cases(conn)
    counts = {}
    for case in cases:
        code = _type_code(case.get("official_type_no", ""))
        if code:
            counts[code] = counts.get(code, 0) + 1
        else:
            # 没有官方类型编号的案例（非交易型/未定型）计入"无法归类"出口
            counts[EXIT_NO] = counts.get(EXIT_NO, 0) + 1
    rows = []
    for t in types:
        rule_ids = [r for r in (t.get("rule") or "").split(" / ") if r.startswith("R")]
        rows.append({**t,
                     "case_count": counts.get(t["no"], 0),
                     "executable": any(r in RULE_FUNCS for r in rule_ids),
                     "rules": rule_ids})
    return {"count": len(rows), "types": rows,
            "total_cases": len(cases), "library_cases": len(case_repo.list_library(conn))}


def effectiveness(conn):
    cases = merge_cases(conn)
    rules = conn.execute("SELECT rule_id, name FROM rules ORDER BY rule_id").fetchall()
    rows = []
    for rule_id, name in rules:
        if rule_id not in RULE_FUNCS:
            continue
        hit_cases = [c for c in cases if rule_id in (c.get("rules_hit") or [])]
        confirmed = sum(1 for c in hit_cases if _conclusion(c) == "拦截")
        excluded = sum(1 for c in hit_cases if _conclusion(c) == "放行")
        review = sum(1 for c in hit_cases if _conclusion(c) == "人工复核")
        rows.append({
            "rule_id": rule_id, "rule_name": name,
            "hit_cases": len(hit_cases),
            "confirmed": confirmed, "excluded": excluded, "review": review,
            "confirm_rate": round(confirmed / len(hit_cases) * 100, 1) if hit_cases else 0.0,
            "case_ids": [c["case_id"] for c in hit_cases],
        })
    return {"count": len(rows), "rules": rows,
            "note": "演示样本量小，确认率仅用于观察规则与案例的对应关系，不代表生产精确率。"}


def library_summary(conn):
    entries = case_repo.list_library(conn)
    sources = {}
    for e in entries:
        sources[e.get("source", "manual")] = sources.get(e.get("source", "manual"), 0) + 1
    return {"count": len(entries), "sources": sources, "entries": entries}
