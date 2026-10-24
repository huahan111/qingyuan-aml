"""导入补充法规：2006 版 3 号令、反洗钱特别预防措施管理办法。

这两个文件原先只存在于预置数据库中，run.sh 从零重建时会缺失；本脚本
从 data/regulations_extra.json 导入，保证删库重建后仍是 8 份法规 / 239 条。
可重复执行。
"""
import json
import os
import sqlite3

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.getenv("QINGYUAN_DB", os.path.join(BASE, "data", "qingyuan.db"))
DATA_PATH = os.path.join(BASE, "data", "regulations_extra.json")


def main():
    with open(DATA_PATH, encoding="utf-8") as f:
        regulations = json.load(f)
    conn = sqlite3.connect(DB_PATH)
    total = 0
    for reg in regulations:
        row = conn.execute("SELECT id FROM regulations WHERE reg_code=?",
                           (reg["reg_code"],)).fetchone()
        if row:
            reg_id = row[0]
            conn.execute(
                "UPDATE regulations SET name=?, issuer=?, doc_number=?, effective_date=?, source=? WHERE id=?",
                (reg["name"], reg.get("issuer", ""), reg.get("doc_number", ""),
                 reg.get("effective_date", ""), reg.get("source", ""), reg_id))
            conn.execute("DELETE FROM clauses WHERE regulation_id=?", (reg_id,))
        else:
            cur = conn.execute(
                "INSERT INTO regulations(reg_code, name, issuer, doc_number, effective_date, source) "
                "VALUES (?,?,?,?,?,?)",
                (reg["reg_code"], reg["name"], reg.get("issuer", ""), reg.get("doc_number", ""),
                 reg.get("effective_date", ""), reg.get("source", "")))
            reg_id = cur.lastrowid
        for clause in reg["clauses"]:
            conn.execute(
                "INSERT INTO clauses(regulation_id, clause_no, chapter, content, topic_tags) "
                "VALUES (?,?,?,?,?)",
                (reg_id, clause["clause_no"], clause.get("chapter", ""),
                 clause["content"], clause.get("topic_tags", "")))
            total += 1
    conn.commit()
    n = conn.execute("SELECT COUNT(*) FROM regulations").fetchone()[0]
    c = conn.execute("SELECT COUNT(*) FROM clauses").fetchone()[0]
    conn.close()
    print(f"补充法规入库完成：{len(regulations)} 份 / {total} 条；当前共 {n} 份 / {c} 条")


if __name__ == "__main__":
    main()
