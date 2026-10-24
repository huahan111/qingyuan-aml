"""清源MVP 法规库/案例库 SQLite 建表脚本"""
import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "qingyuan.db")

SCHEMA = """
-- 法规主表
CREATE TABLE IF NOT EXISTS regulations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    reg_code TEXT UNIQUE NOT NULL,   -- 如 'PBOC_3_2016'
    name TEXT NOT NULL,              -- 法规全名
    issuer TEXT,                     -- 发文机关
    doc_number TEXT,                 -- 文号
    effective_date TEXT,             -- 生效日期
    source TEXT                      -- 来源说明
);

-- 条款表（切块到"条"）
CREATE TABLE IF NOT EXISTS clauses (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    regulation_id INTEGER NOT NULL REFERENCES regulations(id),
    chapter TEXT,                    -- 章节
    clause_no TEXT NOT NULL,         -- 条款号 如 "第十一条" / "第28条"
    content TEXT NOT NULL,           -- 条文原文
    topic_tags TEXT DEFAULT '',      -- 主题标签，逗号分隔
    UNIQUE(regulation_id, clause_no)
);

-- 条款全文检索（trigram 分词器，支持中文子串匹配）
CREATE VIRTUAL TABLE IF NOT EXISTS clauses_fts USING fts5(
    content, clause_no, chapter,
    content=clauses, content_rowid=id,
    tokenize='trigram'
);

-- FTS 同步触发器
CREATE TRIGGER IF NOT EXISTS clauses_ai AFTER INSERT ON clauses BEGIN
    INSERT INTO clauses_fts(rowid, content, clause_no, chapter)
    VALUES (new.id, new.content, new.clause_no, new.chapter);
END;
CREATE TRIGGER IF NOT EXISTS clauses_ad AFTER DELETE ON clauses BEGIN
    INSERT INTO clauses_fts(clauses_fts, rowid, content, clause_no, chapter)
    VALUES ('delete', old.id, old.content, old.clause_no, old.chapter);
END;

-- 规则表（R001-R016，legal_basis 关联条款）
CREATE TABLE IF NOT EXISTS rules (
    rule_id TEXT PRIMARY KEY,        -- R001
    name TEXT NOT NULL,
    category TEXT NOT NULL,          -- 'base' | 'typed'
    legal_clause_ids TEXT DEFAULT '[]',  -- 关联 clauses.id，JSON数组
    legal_desc TEXT DEFAULT '',      -- 法规依据描述
    official_type_no TEXT DEFAULT '',    -- 官方类型编号
    official_type_name TEXT DEFAULT '',
    crime_code TEXT DEFAULT '',      -- 疑似涉罪类型代码
    crime_name TEXT DEFAULT '',
    params TEXT DEFAULT '{}',        -- 规则参数JSON
    penalty_ref TEXT DEFAULT ''      -- 对应央行处罚事由类别
);

-- 案例表
CREATE TABLE IF NOT EXISTS cases (
    case_id TEXT PRIMARY KEY,        -- CASE-01
    title TEXT NOT NULL,
    category TEXT NOT NULL,          -- 'pass' | 'intercept' | 'grey'
    customer_info TEXT NOT NULL,     -- JSON 客户画像（脱敏合成）
    transactions TEXT NOT NULL,      -- JSON 交易序列
    expected_conclusion TEXT NOT NULL,   -- '放行' | '拦截' | '人工复核'
    rules_hit TEXT DEFAULT '[]',     -- JSON 命中规则编号
    official_type_no TEXT DEFAULT '',
    official_type_name TEXT DEFAULT '',
    trace_chain TEXT DEFAULT '[]',   -- JSON 溯源链 [{rule_id, clause_id, ...}]
    grey_zone TEXT DEFAULT '{}',     -- JSON 灰区双向判定 {pass_if, intercept_if, human_check}
    source TEXT DEFAULT 'manual',    -- demo | submission | disposition | manual | import
    source_case_id TEXT DEFAULT '',  -- 来源演示案例编号
    final_conclusion TEXT DEFAULT '',-- 人工确认结论
    report_no TEXT DEFAULT '',
    receipt_no TEXT DEFAULT '',
    audit_json TEXT DEFAULT '{}',    -- 排除/确认理由、操作人、时间
    created_at TEXT DEFAULT '',
    updated_at TEXT DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_cases_source ON cases(source);
CREATE INDEX IF NOT EXISTS idx_cases_report ON cases(report_no);

-- 上报台账：运营记录，持久化保存每次报送（不属于演示案例数据）
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
"""

def init_db():
    conn = sqlite3.connect(DB_PATH)
    conn.executescript(SCHEMA)
    conn.commit()
    conn.close()
    print(f"DB initialized: {DB_PATH}")

if __name__ == "__main__":
    init_db()
