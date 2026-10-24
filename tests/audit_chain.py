"""审计链（L1 防篡改留痕）测试：哈希链延伸、服务器时间戳、触发器、篡改检测、只读模式。

运行：python3 tests/audit_chain.py
篡改类用例在独立数据库副本上做（绕过触发器模拟内部攻击），不污染主测试链。
"""
import json
import os
import re
import shutil
import sqlite3
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BACKEND = os.path.join(ROOT, "backend")

TMP = tempfile.TemporaryDirectory()
TEST_DB = os.path.join(TMP.name, "audit.db")
shutil.copy(os.path.join(BACKEND, "data", "qingyuan.db"), TEST_DB)
os.environ["QINGYUAN_DB"] = TEST_DB
os.environ["QINGYUAN_READ_ONLY"] = "0"   # 记录类用例需要可写（默认只读 fail-closed）
sys.path.insert(0, BACKEND)

from infra import audit  # noqa: E402
from infra.db import get_db  # noqa: E402

audit.ensure_schema()  # 独立运行时自建审计表（api_contract 场景由 main.py 装配时创建）

ISO_MS = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}\+08:00$")


class AuditChainTest(unittest.TestCase):
    def test_01_record_and_chain(self):
        conn = get_db()
        try:
            r1 = audit.record(conn, actor="张三", action="报送写入",
                              object_type="submission", object_id="RX-20260101-00001",
                              detail={"case_id": "BLOCK-01"})
            r2 = audit.record(conn, actor="李四", action="名单筛查",
                              object_type="screening", object_id="恐怖组织A",
                              detail={"hit": True})
            self.assertEqual(r1["seq"], 1)
            self.assertEqual(r2["seq"], 2)

            rows = conn.execute("SELECT * FROM audit_log ORDER BY seq").fetchall()
            self.assertEqual(len(rows), 2)
            # 哈希链衔接：第 2 条 prev_hash = 第 1 条 record_hash；首条 prev = Genesis
            self.assertEqual(rows[0]["prev_hash"], audit.GENESIS)
            self.assertEqual(rows[1]["prev_hash"], rows[0]["record_hash"])

            v = audit.verify(conn)
            self.assertTrue(v["ok"], v)
            self.assertEqual(v["records"], 2)
            self.assertEqual(v["head_hash"], rows[1]["record_hash"])
        finally:
            conn.close()

    def test_02_server_timestamps(self):
        conn = get_db()
        try:
            audit.record(conn, actor="王五", action="人工定性",
                         object_type="library_case", object_id="DIS-EXCLUDE-01")
            row = conn.execute(
                "SELECT * FROM audit_log ORDER BY seq DESC LIMIT 1").fetchone()
            # 服务器时间：ISO + 毫秒 + 北京时区偏移
            self.assertRegex(row["occurred_at"], ISO_MS)
        finally:
            conn.close()

    def test_03_query_filters(self):
        conn = get_db()
        try:
            all_rows = audit.query(conn)
            self.assertGreaterEqual(all_rows["total"], 3)

            only = audit.query(conn, action="名单筛查")
            self.assertGreaterEqual(only["total"], 1)
            self.assertTrue(all(r["action"] == "名单筛查" for r in only["records"]))

            by_actor = audit.query(conn, actor="张三")
            self.assertGreaterEqual(by_actor["total"], 1)
            self.assertTrue(all("张三" in r["actor"] for r in by_actor["records"]))

            today = conn.execute(
                "SELECT substr(occurred_at,1,10) AS d FROM audit_log LIMIT 1").fetchone()["d"]
            by_date = audit.query(conn, date_from=today, date_to=today)
            self.assertEqual(by_date["total"], all_rows["total"])
            none = audit.query(conn, date_from="2000-01-01", date_to="2000-01-02")
            self.assertEqual(none["total"], 0)

            # detail 反序列化为对象
            rec = audit.query(conn, action="报送写入")["records"][0]
            self.assertEqual(rec["detail"]["case_id"], "BLOCK-01")
        finally:
            conn.close()

    def test_04_triggers_block_update_delete(self):
        conn = get_db()
        try:
            with self.assertRaises(sqlite3.IntegrityError):
                conn.execute("UPDATE audit_log SET actor='黑客' WHERE seq=1")
            with self.assertRaises(sqlite3.IntegrityError):
                conn.execute("DELETE FROM audit_log WHERE seq=1")
            # 触发器拦截后链仍完整
            self.assertTrue(audit.verify(conn)["ok"])
        finally:
            conn.close()

    def test_05_tamper_detected_even_without_trigger(self):
        # 模拟拿到数据库文件、绕过触发器改记录的内部攻击：verify 必须发现
        tampered = os.path.join(TMP.name, "tampered.db")
        shutil.copy(TEST_DB, tampered)
        conn = sqlite3.connect(tampered)
        conn.row_factory = sqlite3.Row
        conn.execute("DROP TRIGGER audit_log_no_update")
        conn.execute("UPDATE audit_log SET actor='黑客', detail_json='{\"forged\":true}' WHERE seq=1")
        conn.commit()
        v = audit.verify(conn)
        self.assertFalse(v["ok"])
        self.assertEqual(v["broken_seq"], 1)
        conn.close()

    def test_06_deletion_detected_via_seq_gap(self):
        tampered = os.path.join(TMP.name, "gap.db")
        shutil.copy(TEST_DB, tampered)
        conn = sqlite3.connect(tampered)
        conn.row_factory = sqlite3.Row
        conn.execute("DROP TRIGGER audit_log_no_delete")
        conn.execute("DELETE FROM audit_log WHERE seq=2")
        conn.commit()
        v = audit.verify(conn)
        self.assertFalse(v["ok"])
        conn.close()

    def test_07_read_only_mode_skips_recording(self):
        os.environ["QINGYUAN_READ_ONLY"] = "1"
        try:
            conn = get_db()
            try:
                before = conn.execute("SELECT COUNT(*) AS n FROM audit_log").fetchone()["n"]
                self.assertIsNone(audit.record(conn, actor="x", action="y",
                                               object_type="z", object_id="w"))
                after = conn.execute("SELECT COUNT(*) AS n FROM audit_log").fetchone()["n"]
                self.assertEqual(before, after)
                # 只读下校验与查询仍可用
                self.assertTrue(audit.verify(conn)["ok"])
                self.assertGreaterEqual(audit.query(conn)["total"], 1)
            finally:
                conn.close()
        finally:
            os.environ["QINGYUAN_READ_ONLY"] = "0"


if __name__ == "__main__":
    try:
        unittest.main(verbosity=2)
    finally:
        TMP.cleanup()
