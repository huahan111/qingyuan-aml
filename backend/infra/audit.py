"""L1 审计链：append-only 记录 + SHA256 哈希链 + 服务器毫秒时间戳。

金融审计证据三环：谁操作的（actor）、做了什么（detail）、不可抵赖（哈希链）。
设计要点：
- 只允许 INSERT：触发器拒绝 UPDATE/DELETE，应用层不提供任何修改/删除接口；
- record_hash = SHA256(seq | occurred_at | actor | action | object_type | object_id
                       | detail_json | prev_hash)，首条 prev_hash 为全零 Genesis。
  任何一条记录的任何字段被改动，其后整条链的校验全部失败（verify 全链重放）；
- occurred_at 为服务器时钟（Asia/Shanghai +08:00，毫秒精度，单调 seq 兜底同毫秒排序），
  客户端时间不参与证据链；
- 只读演示模式（QINGYUAN_READ_ONLY=1）下不记录新审计（公开部署保持库不可变），
  查询与校验接口仍然开放；
- 演示重置不清空审计链——重置动作本身作为一条审计记录留痕。
"""
import hashlib
import json
from datetime import datetime, timedelta, timezone

from infra.db import DB_PATH
from infra.security import is_read_only

_TZ = timezone(timedelta(hours=8))
GENESIS = "0" * 64

# 查询上限：审计是取证接口，不是导出接口；全量导出走数据库备份
MAX_LIMIT = 200


def _now_iso_ms() -> str:
    now = datetime.now(_TZ)
    return now.strftime("%Y-%m-%dT%H:%M:%S.") + f"{now.microsecond // 1000:03d}+08:00"


def _hash(seq, occurred_at, actor, action, object_type, object_id, detail_json, prev_hash) -> str:
    payload = (f"{seq}|{occurred_at}|{actor}|{action}|{object_type}|{object_id}"
               f"|{detail_json}|{prev_hash}")
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def ensure_schema():
    import sqlite3
    conn = sqlite3.connect(DB_PATH)
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS audit_log (
        seq INTEGER PRIMARY KEY,
        occurred_at TEXT NOT NULL,
        actor TEXT NOT NULL,
        action TEXT NOT NULL,
        object_type TEXT NOT NULL,
        object_id TEXT NOT NULL DEFAULT '',
        detail_json TEXT NOT NULL DEFAULT '{}',
        prev_hash TEXT NOT NULL,
        record_hash TEXT NOT NULL
    );
    -- 防篡改第一道闸：数据库层直接拒绝改写与删除（绕过应用层的最后防线）
    CREATE TRIGGER IF NOT EXISTS audit_log_no_update BEFORE UPDATE ON audit_log
    BEGIN SELECT RAISE(ABORT, 'audit_log 为防篡改审计链，禁止 UPDATE'); END;
    CREATE TRIGGER IF NOT EXISTS audit_log_no_delete BEFORE DELETE ON audit_log
    BEGIN SELECT RAISE(ABORT, 'audit_log 为防篡改审计链，禁止 DELETE'); END;
    """)
    conn.commit()
    conn.close()


def record(conn, actor, action, object_type, object_id="", detail=None):
    """追加一条审计记录并延伸哈希链。只读模式下跳过（返回 None）。

    单写入者（单 worker 演示部署）下 seq = MAX(seq)+1 无竞态；
    并发部署需先改造为数据库序列或独立审计服务。
    """
    if is_read_only():
        return None
    row = conn.execute(
        "SELECT seq, record_hash FROM audit_log ORDER BY seq DESC LIMIT 1").fetchone()
    seq = (row["seq"] + 1) if row else 1
    prev_hash = row["record_hash"] if row else GENESIS
    occurred_at = _now_iso_ms()
    actor = str(actor or "未署名")[:80]
    action = str(action or "")[:60]
    object_type = str(object_type or "")[:40]
    object_id = str(object_id or "")[:120]
    detail_json = json.dumps(detail or {}, ensure_ascii=False, sort_keys=True)
    record_hash = _hash(seq, occurred_at, actor, action, object_type, object_id,
                        detail_json, prev_hash)
    conn.execute(
        "INSERT INTO audit_log (seq, occurred_at, actor, action, object_type, object_id,"
        " detail_json, prev_hash, record_hash) VALUES (?,?,?,?,?,?,?,?,?)",
        (seq, occurred_at, actor, action, object_type, object_id,
         detail_json, prev_hash, record_hash))
    conn.commit()
    return {"seq": seq, "occurred_at": occurred_at, "record_hash": record_hash}


def verify(conn):
    """全链重放校验：逐条重算哈希并核对 prev_hash 链接与 seq 连续性。"""
    prev_hash = GENESIS
    count = 0
    for row in conn.execute("SELECT * FROM audit_log ORDER BY seq"):
        count += 1
        if row["seq"] != count:
            return {"ok": False, "records": count - 1, "broken_seq": row["seq"],
                    "reason": f"序号不连续：应为 {count}，实为 {row['seq']}（疑似删改记录）"}
        expected = _hash(row["seq"], row["occurred_at"], row["actor"], row["action"],
                         row["object_type"], row["object_id"], row["detail_json"],
                         row["prev_hash"])
        if row["prev_hash"] != prev_hash:
            return {"ok": False, "records": count, "broken_seq": row["seq"],
                    "reason": "prev_hash 与上一条 record_hash 不衔接（疑似插入/篡改）"}
        if expected != row["record_hash"]:
            return {"ok": False, "records": count, "broken_seq": row["seq"],
                    "reason": "record_hash 与字段内容不匹配（该条记录被篡改）"}
        prev_hash = expected
    return {"ok": True, "records": count, "head_hash": prev_hash,
            "genesis": GENESIS, "algorithm": "SHA256 哈希链（append-only + 触发器防改写）"}


def query(conn, actor="", action="", object_type="", object_id="",
          date_from="", date_to="", limit=50, offset=0):
    """审计检索：按操作人/动作/对象类型/对象编号/日期范围过滤，seq 倒序。"""
    where, params = [], []
    if actor:
        where.append("actor LIKE ?"); params.append(f"%{actor}%")
    if action:
        where.append("action = ?"); params.append(action)
    if object_type:
        where.append("object_type = ?"); params.append(object_type)
    if object_id:
        where.append("object_id LIKE ?"); params.append(f"%{object_id}%")
    if date_from:
        where.append("substr(occurred_at,1,10) >= ?"); params.append(date_from)
    if date_to:
        where.append("substr(occurred_at,1,10) <= ?"); params.append(date_to)
    clause = (" WHERE " + " AND ".join(where)) if where else ""
    limit = max(1, min(int(limit or 50), MAX_LIMIT))
    offset = max(0, int(offset or 0))
    total = conn.execute("SELECT COUNT(*) AS n FROM audit_log" + clause,
                         params).fetchone()["n"]
    rows = conn.execute(
        "SELECT * FROM audit_log" + clause + " ORDER BY seq DESC LIMIT ? OFFSET ?",
        params + [limit, offset]).fetchall()
    actions = [r["action"] for r in conn.execute(
        "SELECT DISTINCT action FROM audit_log ORDER BY action")]
    return {"total": total, "count": len(rows), "offset": offset, "limit": limit,
            "actions": actions,
            "records": [dict(r, detail=json.loads(r["detail_json"] or "{}")) for r in rows]}
