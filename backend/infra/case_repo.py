"""已定性案例库数据访问（cases 表，仅非演示来源）。"""
import json

_JSON_FIELDS = ("customer_info", "transactions", "rules_hit", "trace_chain",
                "grey_zone", "audit_json")
_DEFAULTS = {"customer_info": {}, "transactions": [], "rules_hit": [],
             "trace_chain": [], "grey_zone": {}, "audit_json": {}}


def _to_case(row):
    out = dict(row)
    for key in _JSON_FIELDS:
        raw = out.get(key)
        try:
            out[key] = json.loads(raw) if raw else _DEFAULTS[key]
        except (TypeError, ValueError):
            out[key] = _DEFAULTS[key]
    out["audit"] = out.pop("audit_json")
    out.setdefault("source", "manual")
    out.setdefault("final_conclusion", out.get("expected_conclusion", ""))
    return out


def list_library(conn):
    rows = conn.execute(
        "SELECT * FROM cases WHERE source IN ('submission','disposition','manual','import') "
        "ORDER BY updated_at DESC, case_id"
    ).fetchall()
    return [_to_case(r) for r in rows]


def get_library(conn, case_id):
    row = conn.execute("SELECT * FROM cases WHERE case_id=?", (case_id,)).fetchone()
    return _to_case(row) if row else None


def upsert(conn, case):
    payload = (
        case["case_id"], case["title"], case["category"],
        json.dumps(case["customer_info"], ensure_ascii=False),
        json.dumps(case["transactions"], ensure_ascii=False),
        case["expected_conclusion"],
        json.dumps(case.get("rules_hit") or [], ensure_ascii=False),
        case.get("official_type_no", ""), case.get("official_type_name", ""),
        json.dumps(case.get("trace_chain") or [], ensure_ascii=False),
        json.dumps(case.get("grey_zone") or {}, ensure_ascii=False),
        case.get("source", "manual"), case.get("source_case_id", ""),
        case.get("final_conclusion", ""), case.get("report_no", ""),
        case.get("receipt_no", ""), json.dumps(case.get("audit") or {}, ensure_ascii=False),
        case.get("created_at", ""), case.get("updated_at", ""),
    )
    exists = conn.execute("SELECT case_id FROM cases WHERE case_id=?",
                          (case["case_id"],)).fetchone()
    if exists:
        conn.execute("""
            UPDATE cases SET title=?, category=?, customer_info=?, transactions=?,
                expected_conclusion=?, rules_hit=?, official_type_no=?, official_type_name=?,
                trace_chain=?, grey_zone=?, source=?, source_case_id=?, final_conclusion=?,
                report_no=?, receipt_no=?, audit_json=?, updated_at=?
            WHERE case_id=?
        """, (
            case["title"], case["category"], payload[3], payload[4],
            case["expected_conclusion"], payload[6],
            case.get("official_type_no", ""), case.get("official_type_name", ""),
            payload[9], payload[10], case.get("source", "manual"),
            case.get("source_case_id", ""), case.get("final_conclusion", ""),
            case.get("report_no", ""), case.get("receipt_no", ""),
            payload[16], case.get("updated_at", ""), case["case_id"],
        ))
    else:
        conn.execute("""
            INSERT INTO cases
            (case_id, title, category, customer_info, transactions, expected_conclusion,
             rules_hit, official_type_no, official_type_name, trace_chain, grey_zone,
             source, source_case_id, final_conclusion, report_no, receipt_no,
             audit_json, created_at, updated_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """, payload)
    return case["case_id"]
