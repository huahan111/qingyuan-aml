"""上报台账服务：写入、查询与详情解析。不依赖 FastAPI。"""
import json
import re
import sqlite3
from datetime import date, datetime


class SubmissionValidationError(ValueError):
    pass


class SubmissionConflictError(ValueError):
    pass


class SubmissionNotFoundError(ValueError):
    pass


REQUIRED = ("report_no", "case_id", "submitted_at")

# 三级授权签字：写入台账必须带齐三级，且每级有姓名+工号。
# 只靠前端状态机把关不够——直接 POST /api/submissions 曾能造出"签字齐全"的台账记录。
AUDIT_ROLES = ("operator", "reviewer", "approver")
AUDIT_ROLE_NAMES = {"operator": "经办", "reviewer": "复核", "approver": "审批"}


# 标识符白名单：报告编号/回执号/案例号是"编号"，不是自由文本。
# 这些值会被写进台账、再拼成 LIB- 案例号在前端渲染，放开字符集等于开放存储型 XSS 入口。
_SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:\-]{0,79}$")


def _validate_ids(payload):
    for key in ("report_no", "case_id"):
        value = str(payload.get(key) or "")
        if not _SAFE_ID.match(value):
            raise SubmissionValidationError(
                f"{key} 只允许字母、数字与 . _ : -（须以字母或数字开头，最长 80 字符）")
    # 回执号由服务端生成；客户端传入值一律忽略，但若传入仍须格式合法（兼容旧客户端）
    client_receipt = str(payload.get("receipt_no") or "")
    if client_receipt and not _SAFE_ID.match(client_receipt):
        raise SubmissionValidationError(
            "receipt_no 只允许字母、数字与 . _ : -（须以字母或数字开头，最长 80 字符）")
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
    字符串前缀比较会漏计"今日上报"、ORDER BY 也会乱序。这里在写入侧收敛；
    解析失败返回 None，由调用方决定是否拒绝（此前失败值会原样入库）。
    """
    v = (value or "").strip().replace("/", "-")
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            return datetime.strptime(v, fmt).strftime("%Y-%m-%d %H:%M:%S")
        except ValueError:
            continue
    return None


def _validate_version(payload):
    """version 必须是整数（或纯数字字符串）。历史上 "abc"、[1] 会在 int() 处裸抛 500。"""
    raw = payload.get("version", 1)
    if isinstance(raw, bool):
        raise SubmissionValidationError("version 必须为整数")
    if isinstance(raw, int):
        return raw
    if isinstance(raw, str) and raw.strip().isdigit():
        return int(raw.strip())
    raise SubmissionValidationError("version 必须为整数（如 1、2），当前值类型非法")


def _validate_submitted_at(payload):
    """submitted_at 必须是非空字符串且可解析。历史上 [1]、时间戳数组会裸抛 500。"""
    value = payload.get("submitted_at")
    if not isinstance(value, str) or not value.strip():
        raise SubmissionValidationError("submitted_at 必须为非空字符串（YYYY-MM-DD HH:MM:SS）")
    ts = _normalize_ts(value)
    if ts is None:
        raise SubmissionValidationError("submitted_at 格式非法，应为 YYYY-MM-DD [HH:MM[:SS]]")
    return ts


def _validate_supersedes(conn, payload):
    """更正报告必须指向真实存在、同案例、且未被更正过的原回执。

    此前 UPDATE 无任何校验：任意回执号（甚至不存在的）都能把他人记录改成「已更正」。
    """
    supersedes = str(payload.get("supersedes_receipt") or "").strip()
    if not supersedes:
        return ""
    target = conn.execute(
        "SELECT case_id, status FROM submissions WHERE receipt_no=?", (supersedes,)).fetchone()
    if not target:
        raise SubmissionValidationError(f"原回执 {supersedes} 不存在，无法生成更正报告")
    if target["case_id"] != payload["case_id"]:
        raise SubmissionValidationError("原回执归属案例与本报告不一致，拒绝跨案例更正")
    if target["status"] == "已更正":
        raise SubmissionValidationError("该回执已有更正报告，不能重复更正")
    return supersedes


def _next_receipt_no(conn):
    """服务端生成回执号：RX-YYYYMMDD-NNNNN（当日递增序号）。

    回执号不再由客户端随机生成——历史上前端 5 位随机数（同日仅 9 万空间）碰撞时，
    幂等分支会把第二份报告的写入并进第一条记录，造成静默丢失。
    """
    prefix = f"RX-{date.today().strftime('%Y%m%d')}-"
    row = conn.execute(
        "SELECT receipt_no FROM submissions WHERE receipt_no LIKE ? "
        "ORDER BY receipt_no DESC LIMIT 1", (prefix + "%",)).fetchone()
    seq = int(row["receipt_no"][len(prefix):]) + 1 if row else 1
    return prefix, seq


def create(conn, payload: dict):
    for key in REQUIRED:
        if not payload.get(key):
            raise SubmissionValidationError(f"缺少字段：{key}")
    _validate_ids(payload)
    _validate_audit(payload)
    submitted_at = _validate_submitted_at(payload)
    version = _validate_version(payload)

    # 幂等以报告编号为准：同一份报告重复提交（重试/双击）返回同一条台账记录。
    dup = conn.execute(
        "SELECT id, report_no, receipt_no, submitted_at FROM submissions WHERE report_no=?",
        (payload["report_no"],)).fetchone()
    if dup:
        return dict(dup)

    supersedes = _validate_supersedes(conn, payload)

    # 回执号由服务端生成，客户端传入的 receipt_no 一律忽略
    last_err = None
    for _ in range(5):
        prefix, seq = _next_receipt_no(conn)
        receipt_no = f"{prefix}{seq:05d}"
        try:
            conn.execute("""
                INSERT INTO submissions
                (report_no, receipt_no, case_id, case_title, customer, submitted_at, version,
                 operator, reviewer, approver, audit_json, report_json, edit_log_json, return_log_json,
                 supersedes_receipt, filing_deadline, destination, status)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """, (
                payload["report_no"], receipt_no, payload["case_id"],
                payload.get("case_title", ""), payload.get("customer", ""),
                submitted_at, version,
                payload.get("operator", ""), payload.get("reviewer", ""), payload.get("approver", ""),
                json.dumps(payload.get("audit", {}), ensure_ascii=False),
                json.dumps(payload.get("report", {}), ensure_ascii=False),
                json.dumps(payload.get("edit_log", []), ensure_ascii=False),
                json.dumps(payload.get("return_log", []), ensure_ascii=False),
                supersedes,
                payload.get("filing_deadline", ""),
                payload.get("destination", "CAMLMAC"), payload.get("status", "已报送"),
            ))
            if supersedes:
                conn.execute("UPDATE submissions SET status='已更正' WHERE receipt_no=?",
                             (supersedes,))
            conn.commit()
            break
        except sqlite3.IntegrityError as e:
            conn.rollback()
            last_err = e
    else:
        raise SubmissionConflictError(f"回执号生成冲突，写入失败：{last_err}")

    row = conn.execute(
        "SELECT id, report_no, receipt_no, submitted_at FROM submissions WHERE receipt_no=?",
        (receipt_no,)).fetchone()
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
