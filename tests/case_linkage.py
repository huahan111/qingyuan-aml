"""案例库与规则库联动测试：反哺、合并、覆盖、有效性。"""
import json
import os
import shutil
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BACKEND = os.path.join(ROOT, "backend")
SRC_DB = os.path.join(BACKEND, "data", "qingyuan.db")
TMP = tempfile.TemporaryDirectory()
TEST_DB = os.path.join(TMP.name, "linkage.db")
shutil.copy(SRC_DB, TEST_DB)
os.environ["QINGYUAN_DB"] = TEST_DB
sys.path.insert(0, BACKEND)

from infra.db import ensure_case_library_schema, ensure_submissions_table, get_db  # noqa: E402
from infra import case_repo  # noqa: E402
from case_store import get_case  # noqa: E402
from domain.rules import run_engine  # noqa: E402
from domain.report.builder import build_report  # noqa: E402
from ai_diagnosis import get_provider  # noqa: E402
from services import submissions as submission_svc  # noqa: E402
from services import case_linkage  # noqa: E402


class LinkageTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        ensure_submissions_table()
        ensure_case_library_schema()
        cls.conn = get_db()
        cls.case = get_case("BLOCK-01")
        hits = run_engine(cls.case["transactions"], cls.case["customer_info"], cls.conn)
        diag = get_provider().diagnose("BLOCK-01", cls.case, hits)
        cls.report = build_report(cls.case, diag, hits, cls.conn)
        cls.sub = submission_svc.create(cls.conn, {
            "report_no": cls.report["report_no"], "receipt_no": "RX-LINK-0001",
            "case_id": "BLOCK-01", "case_title": cls.case["title"],
            "customer": cls.case["customer_info"]["name"],
            "submitted_at": "2026-10-23 09:00:00", "version": 1,
            "operator": "陈立 NJ-AML-0231", "reviewer": "张敏 NJ-AML-0108",
            "approver": "王建国 NJ-CC-0006",
            "audit": {"operator": {"name": "陈立", "id": "NJ-AML-0231"},
                      "reviewer": {"name": "张敏", "id": "NJ-AML-0108"},
                      "approver": {"name": "王建国", "id": "NJ-CC-0006"}},
            "report": cls.report, "edit_log": [], "return_log": [],
            "supersedes_receipt": "", "filing_deadline": cls.report["filing_deadline"],
        })
        cls.promoted = case_linkage.promote_submission(cls.conn, cls.sub["id"])

    @classmethod
    def tearDownClass(cls):
        cls.conn.close()
        TMP.cleanup()

    def test_01_promoted(self):
        self.assertTrue(self.promoted["promoted"])
        self.assertTrue(self.promoted["library_case_id"].startswith("LIB-"))
        entry = case_repo.get_library(self.conn, self.promoted["library_case_id"])
        self.assertIsNotNone(entry)
        self.assertEqual(entry["source"], "submission")
        self.assertEqual(entry["source_case_id"], "BLOCK-01")
        self.assertEqual(entry["expected_conclusion"], "拦截")
        self.assertEqual(entry["rules_hit"], ["R002"])
        self.assertTrue(entry["transactions"])

    def test_02_promote_idempotent(self):
        case_linkage.promote_submission(self.conn, self.sub["id"])
        self.assertEqual(len(case_repo.list_library(self.conn)), 1)

    def test_03_merge_replaces_demo(self):
        cases = case_linkage.merge_cases(self.conn)
        ids = [c["case_id"] for c in cases]
        self.assertNotIn("BLOCK-01", ids)
        self.assertIn(self.promoted["library_case_id"], ids)
        self.assertEqual(len(cases), 17)

    def test_04_coverage(self):
        data = case_linkage.coverage(self.conn)
        self.assertEqual(data["count"], 18)
        # BLOCK-01 贴线分拆归入官方类型1-1（『规避』识别点），不再挂不存在的"第13类"
        type11 = next(t for t in data["types"] if t["no"] == "1-1")
        self.assertEqual(type11["case_count"], 1)
        self.assertTrue(type11["official"])
        # 第13组为行内归纳维度，不是官方类型；案例不再计入
        type13 = next(t for t in data["types"] if t["no"] == "13")
        self.assertEqual(type13["case_count"], 0)
        self.assertFalse(type13["official"])
        self.assertTrue(type13["executable"])
        # "无法归类"出口承接其余 7 条无官方类型编号的案例（PASS×3、GREY×4）
        exit_row = next(t for t in data["types"] if t["no"] == "—")
        self.assertEqual(exit_row["case_count"], 12)
        self.assertTrue(exit_row["executable"])
        self.assertEqual(data["library_cases"], 1)

    def test_05_effectiveness(self):
        data = case_linkage.effectiveness(self.conn)
        r002 = next(r for r in data["rules"] if r["rule_id"] == "R002")
        self.assertEqual(r002["hit_cases"], 1)
        self.assertEqual(r002["confirmed"], 1)
        self.assertEqual(r002["excluded"], 0)
        self.assertIn(self.promoted["library_case_id"], r002["case_ids"])

    def test_06_backfill(self):
        result = case_linkage.backfill(self.conn)
        self.assertEqual(result["submissions"], 1)
        self.assertEqual(result["promoted"], 1)

    def test_07_disposition_negative_sample(self):
        case = get_case("EXCLUDE-01")
        result = case_linkage.record_disposition(
            self.conn, case, "放行", "合同、发票齐备，人工确认排除", "陈立 NJ-AML-0231")
        self.assertEqual(result["source"], "disposition")
        entry = case_repo.get_library(self.conn, result["library_case_id"])
        self.assertEqual(entry["source"], "disposition")
        self.assertEqual(entry["expected_conclusion"], "放行")
        self.assertEqual(entry["audit"]["reason"], "合同、发票齐备，人工确认排除")
        self.assertEqual(len(case_repo.list_library(self.conn)), 2)

        eff = case_linkage.effectiveness(self.conn)
        r003 = next(r for r in eff["rules"] if r["rule_id"] == "R003")
        self.assertEqual(r003["excluded"], 1)
        self.assertEqual(r003["confirmed"], 1)
        self.assertEqual(r003["confirm_rate"], 50.0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
