"""把 build_rules.RULES 中的参数合并进现有 rules 表。

用途：规则参数改为数据驱动后，旧库只需补参数键，不重建规则、不改案例。
幂等：重复执行结果一致。
运行：python3 backend/scripts/migrate_rule_params.py
"""
import json
import os
import sqlite3
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from build_rules import RULES

DB_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "qingyuan.db")


def main():
    conn = sqlite3.connect(DB_PATH)
    updated = 0
    for row in RULES:
        rule_id, params = row[0], row[9]
        cur = conn.execute("SELECT params FROM rules WHERE rule_id=?", (rule_id,)).fetchone()
        if not cur:
            continue
        merged = json.loads(cur[0] or "{}")
        merged.update(params)
        conn.execute("UPDATE rules SET params=? WHERE rule_id=?",
                     (json.dumps(merged, ensure_ascii=False), rule_id))
        updated += 1
    conn.commit()
    conn.close()
    print(f"规则参数迁移完成：{updated} 条")


if __name__ == "__main__":
    main()
