"""相似案例召回测试：配置、排序、分档与已知案例对。"""
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BACKEND = os.path.join(ROOT, "backend")
sys.path.insert(0, BACKEND)

from case_store import load_dataset  # noqa: E402
from domain.cases.config import load_config  # noqa: E402
from domain.cases.retrieval import retrieve  # noqa: E402


class SimilarityTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cases = load_dataset()["cases"]
        cls.by_id = {c["case_id"]: c for c in cls.cases}
        cls.cfg = load_config()

    def run_case(self, case_id, top_k=3):
        return retrieve(self.by_id[case_id], self.cases, self.cfg, top_k=top_k)

    def test_01_config_valid(self):
        self.assertLess(self.cfg["thresholds"]["medium"], self.cfg["thresholds"]["high"])
        self.assertIn("calibration", self.cfg)
        self.assertTrue(self.cfg["disclaimer"])

    def test_02_self_excluded_and_sorted(self):
        for case in self.cases:
            result = retrieve(case, self.cases, self.cfg)
            ids = [r["case_id"] for r in result["results"]]
            self.assertNotIn(case["case_id"], ids)
            self.assertEqual(len(ids), self.cfg["top_k"])
            scores = [r["score"] for r in result["results"]]
            self.assertEqual(scores, sorted(scores, reverse=True))
            for r in result["results"]:
                self.assertGreaterEqual(r["score"], 0)
                self.assertLessEqual(r["score"], 1)
                self.assertIn(r["band"], ("高度相似", "参考相似", "低相似"))

    def test_03_known_similar_pair(self):
        # BLOCK-02（集资）与 BLOCK-04（赌博）结构最接近：都是"多人小额转入、夜间/凌晨、网银"；
        # 第二名是同为资金归集/过账形态的 BLOCK-03
        result = self.run_case("BLOCK-02")
        self.assertEqual(result["results"][0]["case_id"], "BLOCK-04")
        self.assertEqual(result["results"][0]["band"], "高度相似")
        self.assertEqual(result["results"][1]["case_id"], "BLOCK-03")

    def test_04_neighbor_ranking(self):
        # 反向召回对称：BLOCK-04 的第一名是 BLOCK-02，第二名进入"参考相似"档
        result = self.run_case("BLOCK-04")
        self.assertEqual(result["results"][0]["case_id"], "BLOCK-02")
        self.assertEqual(result["results"][0]["band"], "高度相似")
        self.assertEqual(result["results"][1]["band"], "参考相似")

    def test_05_normal_case_low_similarity(self):
        result = self.run_case("PASS-01", top_k=3)
        self.assertTrue(all(r["band"] == "低相似" for r in result["results"]))

    def test_06_top_k_bounds(self):
        self.assertEqual(len(self.run_case("GREY-01", top_k=2)["results"]), 2)
        self.assertEqual(len(self.run_case("GREY-01", top_k=10)["results"]), 10)


if __name__ == "__main__":
    unittest.main(verbosity=2)
