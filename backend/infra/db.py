"""数据库基础设施：连接工厂与台账表迁移。"""
import os
import sqlite3

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.getenv("QINGYUAN_DB", os.path.join(BASE_DIR, "data", "qingyuan.db"))


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def ensure_submissions_table():
    """已有库升级：确保上报台账表存在（运营记录，与演示案例分开）。"""
    conn = sqlite3.connect(DB_PATH)
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS submissions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        report_no TEXT NOT NULL,
        receipt_no TEXT NOT NULL UNIQUE,
        case_id TEXT NOT NULL,
        case_title TEXT DEFAULT '',
        customer TEXT DEFAULT '',
        submitted_at TEXT NOT NULL,
        version INTEGER DEFAULT 1,
        operator TEXT DEFAULT '',
        reviewer TEXT DEFAULT '',
        approver TEXT DEFAULT '',
        audit_json TEXT DEFAULT '{}',
        report_json TEXT DEFAULT '{}',
        edit_log_json TEXT DEFAULT '[]',
        return_log_json TEXT DEFAULT '[]',
        supersedes_receipt TEXT DEFAULT '',
        filing_deadline TEXT DEFAULT '',
        destination TEXT DEFAULT 'CAMLMAC',
        status TEXT DEFAULT '已报送'
    );
    CREATE INDEX IF NOT EXISTS idx_submissions_time ON submissions(submitted_at DESC);
    -- 报告编号唯一性由数据库保证（原来启动时 DROP 该索引，退化为"先查后插"，并发下有竞态窗口）
    CREATE UNIQUE INDEX IF NOT EXISTS idx_submissions_report_no ON submissions(report_no);
    """)
    cols = {r[1] for r in conn.execute("PRAGMA table_info(submissions)").fetchall()}
    for col, ddl in [
        ("edit_log_json", "TEXT DEFAULT '[]'"),
        ("return_log_json", "TEXT DEFAULT '[]'"),
        ("supersedes_receipt", "TEXT DEFAULT ''"),
        ("filing_deadline", "TEXT DEFAULT ''"),
    ]:
        if col not in cols:
            conn.execute(f"ALTER TABLE submissions ADD COLUMN {col} {ddl}")
    conn.commit()
    conn.close()


def ensure_case_library_schema():
    """已定性案例库：在 cases 表上补联动字段，供规则/案例互相追溯。"""
    conn = sqlite3.connect(DB_PATH)
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS cases (
        case_id TEXT PRIMARY KEY,
        title TEXT NOT NULL,
        category TEXT NOT NULL,
        customer_info TEXT NOT NULL,
        transactions TEXT NOT NULL,
        expected_conclusion TEXT NOT NULL,
        rules_hit TEXT DEFAULT '[]',
        official_type_no TEXT DEFAULT '',
        official_type_name TEXT DEFAULT '',
        trace_chain TEXT DEFAULT '[]',
        grey_zone TEXT DEFAULT '{}'
    );
    """)
    cols = {r[1] for r in conn.execute("PRAGMA table_info(cases)").fetchall()}
    for col, ddl in [
        ("source", "TEXT DEFAULT 'manual'"),
        ("source_case_id", "TEXT DEFAULT ''"),
        ("final_conclusion", "TEXT DEFAULT ''"),
        ("report_no", "TEXT DEFAULT ''"),
        ("receipt_no", "TEXT DEFAULT ''"),
        ("audit_json", "TEXT DEFAULT '{}'"),
        ("created_at", "TEXT DEFAULT ''"),
        ("updated_at", "TEXT DEFAULT ''"),
    ]:
        if col not in cols:
            conn.execute(f"ALTER TABLE cases ADD COLUMN {col} {ddl}")
    conn.executescript("""
    CREATE INDEX IF NOT EXISTS idx_cases_source ON cases(source);
    CREATE INDEX IF NOT EXISTS idx_cases_report ON cases(report_no);
    """)
    conn.commit()
    conn.close()
