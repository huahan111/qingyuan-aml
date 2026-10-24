"""上报台账服务：写入、查询与详情解析。不依赖 FastAPI。"""
import json
import re
import sqlite3
from datetime import datetime


class SubmissionValidationError(ValueError):
    pass


class SubmissionConflictError(ValueError):
    pass


class SubmissionNotFoundError(ValueError):
    pass


REQUIRED = ("report_no", "receipt_no", "case_id", "submitted_at")

# 三级授权签字：写入台账必须带齐三级，且每级有姓名+工号。
# 只靠前端状态机把关不够——直接 POST /api/submissions 曾能造出"签字齐全"的台账记录。
AUDIT_ROLES = ("operator", "reviewer", "approver")
AUDIT_ROLE_NAMES = {"operator": "经办", "reviewer": "复核", "approver": "审批"}


# 标识符白名单：报告编号/回执号/案例号是"编号"，不是自由文本。
# 这些值会被写进台账、再拼成 LIB- 案例号在前端渲染，放开字符集等于开放存储型 XSS 入口。
_SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:\-]{0,79}$")


def _validate_ids(payload):
    for key in ("report_no", "receipt_no", "case_id"):
        value = str(payload.get(key) or "")
        if not _SAFE_ID.match(value):
            raise SubmissionValidationError(
                f"{key} 只允许字母、数字与 . _ : -（须以字母或数字开头，最长 80 字符）")
    meta = (payload.get("report") or {}).get("meta") or {}
    if "conclusion" in meta and meta["conclusion"] not in ("放行", "拦截", "人工复核", "待研判", ""):
        raise SubmissionValidationError("报告快照 meta.conclusion 取值非法")


def _validate_audit(payload):
    audit = payload.get("audit")
    if not isinstance(audit, dict):
        raise SubmissionValidationError("缺少签字记录（audit）：报送台账必须带三级授权签字")
    missing = []
    for role in AUDIT_ROLES:
        sig = audit.get(role)
        if (not isinstance(sig, dict)
                or not str(sig.get("name") or "").strip()
                or not str(sig.get("id") or "").strip()):
            missing.append(AUDIT_ROLE_NAMES[role])
    if missing:
        raise SubmissionValidationError(
            f"三级授权签字不完整，缺少：{'、'.join(missing)}（台账记录必须签字齐全才可写入）")


def _normalize_ts(value):
    """报送时间统一为 ISO（YYYY-MM-DD HH:MM:SS）。

    历史上前端写 "2026/10/23 11:19:26"、接口写 "2026-10-23 09:00:00"，两种格式混存，
    字符串前缀比较会漏计"今日上报"、ORDER BY 也会乱序。这里在写入侧收敛。
    """
    v = (value or "").strip().replace("/", "-")
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            return datetime.strptime(v, fmt).strftime("%Y-%m-%d %H:%M:%S")
        except ValueError:
            continue
    return v


def create(conn, payload: dict):
    for key in REQUIRED:
        if not payload.get(key):
            raise SubmissionValidationError(f"缺少字段：{key}")
    _validate_ids(payload)
    _validate_audit(payload)

    exist = conn.execute(
        "SELECT id, report_no, receipt_no, submitted_at FROM submissions WHERE receipt_no=?",
        (payload["receipt_no"],)).fetchone()
    if exist:
        return dict(exist)

    dup = conn.execute("SELECT id FROM submissions WHERE report_no=?",
                       (payload["report_no"],)).fetchone()
    if dup:
        raise SubmissionConflictError("报告编号已存在，请重新生成报告")

    try:
        conn.execute("""
            INSERT INTO submissions
            (report_no, receipt_no, case_id, case_title, customer, submitted_at, version,
             operator, reviewer, approver, audit_json, report_json, edit_log_json, return_log_json,
             supersedes_receipt, filing_deadline, destination, status)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """, (
            payload["report_no"], payload["receipt_no"], payload["case_id"],
            payload.get("case_title", ""), payload.get("customer", ""),
            _normalize_ts(payload["submitted_at"]), int(payload.get("version", 1)),
            payload.get("operator", ""), payload.get("reviewer", ""), payload.get("approver", ""),
            json.dumps(payload.get("audit", {}), ensure_ascii=False),
            json.dumps(payload.get("report", {}), ensure_ascii=False),
            json.dumps(payload.get("edit_log", []), ensure_ascii=False),
            json.dumps(payload.get("return_log", []), ensure_ascii=False),
            payload.get("supersedes_receipt", ""),
            payload.get("filing_deadline", ""),
            payload.get("destination", "CAMLMAC"), payload.get("status", "已报送"),
        ))
        if payload.get("supersedes_receipt"):
            conn.execute("UPDATE submissions SET status='已更正' WHERE receipt_no=?",
                         (payload["supersedes_receipt"],))
        conn.commit()
    except sqlite3.IntegrityError:
        raise SubmissionConflictError("报告编号已存在，请重新生成报告")

    row = conn.execute(
        "SELECT id, report_no, receipt_no, submitted_at FROM submissions WHERE receipt_no=?",
        (payload["receipt_no"],)).fetchone()
    return dict(row)


def list_all(conn):
    # 按入库顺序倒序（id 单调递增 = 写入顺序）。
    # 曾按 submitted_at 字符串排序，而该列混存 "2026-10-23" 与 "2026/10/23" 两种格式，
    # 字符串比较会打乱时序；现在时间格式已在写入侧统一为 ISO，排序以 id 为准。
    rows = conn.execute("""
        SELECT id, report_no, receipt_no, case_id, case_title, customer, submitted_at,
               version, operator, reviewer, approver, supersedes_receipt, filing_deadline,
               destination, status
        FROM submissions ORDER BY id DESC
    """).fetchall()
    return {"count": len(rows), "submissions": [dict(r) for r in rows]}


def get(conn, sid: int):
    row = conn.execute("SELECT * FROM submissions WHERE id=?", (sid,)).fetchone()
    if not row:
        raise SubmissionNotFoundError("上报记录不存在")
    out = dict(row)
    out["audit"] = json.loads(out.pop("audit_json") or "{}")
    out["report"] = json.loads(out.pop("report_json") or "{}")
    out["edit_log"] = json.loads(out.pop("edit_log_json") or "[]")
    out["return_log"] = json.loads(out.pop("return_log_json") or "[]")
    return out
