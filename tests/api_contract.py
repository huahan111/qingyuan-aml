"""清源AML API 契约测试。

在临时数据库副本上启动 TestClient，验证 16 个核心接口的入参/出参约定。
运行：python3 tests/api_contract.py
"""
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
TEST_DB = os.path.join(TMP.name, "contract.db")
shutil.copy(SRC_DB, TEST_DB)
os.environ["QINGYUAN_DB"] = TEST_DB
sys.path.insert(0, BACKEND)

import main  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

CLIENT = TestClient(main.app)
REPORT_CACHE = {}


class ContractTest(unittest.TestCase):
    def test_01_health_and_dataset(self):
        r = CLIENT.get("/api/health")
        self.assertEqual(r.status_code, 200)
        d = r.json()
        for k in ("status", "ai_provider", "dataset"):
            self.assertIn(k, d)
        self.assertEqual(d["status"], "ok")

        r = CLIENT.get("/api/dataset")
        self.assertEqual(r.status_code, 200)
        self.assertIn("dataset", r.json())

        r = CLIENT.get("/")
        self.assertEqual(r.status_code, 200)
        self.assertIn("清源AML", r.text)

    def test_02_cases(self):
        r = CLIENT.get("/api/cases")
        self.assertEqual(r.status_code, 200)
        cases = r.json()["cases"]
        self.assertEqual(len(cases), 17)
        for c in cases:
            for k in ("case_id", "title", "category", "customer_name", "rules_hit"):
                self.assertIn(k, c)

        r = CLIENT.get("/api/cases/BLOCK-01")
        self.assertEqual(r.status_code, 200)
        c = r.json()
        self.assertIn("customer_info", c)
        self.assertIn("transactions", c)
        self.assertTrue(len(c["transactions"]) > 0)

        r = CLIENT.get("/api/similar-cases/BLOCK-02?top_k=2")
        self.assertEqual(r.status_code, 200)
        sim = r.json()
        self.assertEqual(sim["query_case_id"], "BLOCK-02")
        self.assertEqual(len(sim["results"]), 2)
        for key in ("case_id", "score", "score_percent", "band", "route", "components"):
            self.assertIn(key, sim["results"][0])
        self.assertNotIn("BLOCK-02", [x["case_id"] for x in sim["results"]])

        self.assertEqual(CLIENT.get("/api/similar-cases/NO-SUCH").status_code, 404)
    def test_03_diagnose(self):
        r = CLIENT.post("/api/diagnose/BLOCK-01")
        self.assertEqual(r.status_code, 200)
        d = r.json()
        for k in ("case_id", "rule_hits", "ai_diagnosis", "triage", "trace_chain", "similar_cases"):
            self.assertIn(k, d)
        self.assertIn("R002", [h["rule_id"] for h in d["rule_hits"]])
        self.assertEqual(d["triage"]["decision"], "拦截")
        self.assertEqual(d["similar_cases"]["query_case_id"], "BLOCK-01")
        self.assertEqual(len(d["similar_cases"]["results"]), 3)

        r = CLIENT.post("/api/diagnose/EXCLUDE-01")
        self.assertEqual(r.status_code, 200)
        d = r.json()
        self.assertIn("R003", [h["rule_id"] for h in d["rule_hits"]])
        self.assertEqual(d["ai_diagnosis"]["conclusion"], "放行")
        self.assertEqual(d["triage"]["decision"], "人工复核")
        self.assertEqual(d["triage"]["path"], "命中-排除留痕")

        r = CLIENT.post("/api/case-library/disposition", json={
            "case_id": "EXCLUDE-01", "conclusion": "放行",
            "reason": "合同、发票齐备，人工确认排除", "operator": "测试经办 T-01"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["source"], "disposition")
        self.assertTrue(r.json()["library_case_id"].startswith("DIS-EXCLUDE-01"))

        r = CLIENT.post("/api/case-library/disposition", json={
            "case_id": "EXCLUDE-01", "conclusion": "随便写"})
        self.assertEqual(r.status_code, 422)

    def test_04_report(self):
        r = CLIENT.post("/api/report/BLOCK-01")
        self.assertEqual(r.status_code, 200)
        rep = r.json()
        for k in ("report_no", "elements", "parts", "total", "cn", "en",
                  "meta", "filing_deadline", "counts"):
            self.assertIn(k, rep)
        self.assertEqual(rep["total"], 62)
        self.assertEqual(len(rep["elements"]), 62)
        self.assertEqual(len({e["part"] for e in rep["elements"]}), 4)
        self.assertEqual(len(rep["elements"][0]["value"]) > 0, True)
        self.assertEqual(len(rep["report_no"].split("-")) >= 5, True)
        REPORT_CACHE.update(rep)

        # 第 24 项可疑交易特征代码：官方代码集未接入 → manual 空值，不再用规则号顶替
        e24 = next(e for e in rep["elements"] if e["no"] == 24)
        self.assertEqual(e24["source"], "manual")
        self.assertEqual(e24["value"], "")
        self.assertEqual(rep["counts"]["manual"], 1)
        # 第 21/22 项来源可审计：服务端 Provider 产出标 "server"
        self.assertEqual(rep["meta"]["diagnosis_origin"], "server")
        # 时限说明如实反映节假日配置状态
        self.assertIn("节假日", rep["deadline_note"])

    def test_04b_report_diagnosis_validation(self):
        # diagnosis 入参结构校验：结论枚举之外一律 422（防止任意文本直出报告）
        r = CLIENT.post("/api/report/BLOCK-01", json={"diagnosis": {"conclusion": "放行"}})
        self.assertEqual(r.status_code, 200)  # 合法结构放行
        # 客户端提交的 diagnosis：meta 如实标注来源，事后审计可区分模型产出与人工文本
        self.assertEqual(r.json()["meta"]["diagnosis_origin"], "client")
        r = CLIENT.post("/api/report/BLOCK-01", json={"diagnosis": {"conclusion": "想怎么写就怎么写"}})
        self.assertEqual(r.status_code, 422)
        r = CLIENT.post("/api/report/BLOCK-01", json={"diagnosis": "不是对象"})
        self.assertEqual(r.status_code, 422)
        r = CLIENT.post("/api/report/BLOCK-01",
                        json={"diagnosis": {"conclusion": "拦截", "analysis_points": ["x" * 501]}})
        self.assertEqual(r.status_code, 422)

    def test_05_trace_clauses_rules_regulations(self):
        r = CLIENT.get("/api/trace/BLOCK-01")
        self.assertEqual(r.status_code, 200)
        d = r.json()
        self.assertIn("chain", d)
        self.assertTrue(len(d["chain"]) > 0)

        first_clause = next((c for c in d["chain"][0].get("clauses", [])), None)
        self.assertIsNotNone(first_clause)
        self.assertIn("clause_id", first_clause)

        # 溯源链第三层（官方类型识别点）必须真实存在：
        # BLOCK-01 的贴线分拆对应官方对照表类型1-1 的『规避』识别点
        tc = d["chain"][0]
        self.assertIn("类型1-1", tc.get("type_clause_no", ""))
        self.assertTrue(tc.get("type_identify_content"))
        self.assertIn("规避", tc["type_identify_content"])

        # GREY-02 不套用官方类型（官方对照表无"新开户短期大额跨境"类），必须显式说明而非静默缺失
        r = CLIENT.get("/api/trace/GREY-02")
        self.assertEqual(r.status_code, 200)
        gtc = r.json()["chain"][0]
        self.assertEqual(gtc.get("type_clause_no", ""), "")
        self.assertIsNone(gtc.get("type_identify_content"))
        self.assertTrue(gtc.get("type_note"))

        r = CLIENT.get(f"/api/clauses/{first_clause['clause_id']}")
        self.assertEqual(r.status_code, 200)
        self.assertIn("content", r.json())

        r = CLIENT.get("/api/rules")
        self.assertEqual(len(r.json()["rules"]), 17)
        executable = [x["rule_id"] for x in r.json()["rules"] if x.get("executable")]
        self.assertIn("R017", executable)
        self.assertEqual(len(executable), 10)
        r = CLIENT.get("/api/regulations")
        self.assertEqual(len(r.json()["regulations"]), 8)

    def test_06_screening_and_ctr(self):
        # 单字符查询一律拒绝（历史上 1 个字符即可命中「恐怖组织A」）
        r = CLIENT.get("/api/screening", params={"q": "恐"})
        self.assertEqual(r.status_code, 400)
        r = CLIENT.get("/api/screening", params={"q": "李某"})
        self.assertEqual(r.status_code, 200)
        self.assertIn("hit", r.json())
        self.assertIn("matches", r.json())
        self.assertFalse(r.json()["hit"])
        r = CLIENT.get("/api/screening", params={"q": "恐怖组织A"})
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.json()["hit"])
        r = CLIENT.get("/api/ctr")
        self.assertEqual(r.status_code, 200)
        self.assertIn("rows", r.json())
        self.assertIn("thresholds", r.json())

    def test_07_submissions_contract(self):
        rep = REPORT_CACHE
        self.assertTrue(rep)
        payload = {
            "report_no": rep["report_no"],
            "receipt_no": "RX-CONTRACT-0001",
            "case_id": rep["case_id"],
            "case_title": rep["title"],
            "customer": rep["meta"].get("customer", ""),
            "submitted_at": "2026-10-22 10:00:00",
            "version": 2,
            "operator": "测试经办 T-01",
            "reviewer": "测试复核 T-02",
            "approver": "测试审批 T-03",
            "audit": {"operator": {"name": "测试经办", "id": "T-01"},
                      "reviewer": {"name": "测试复核", "id": "T-02"},
                      "approver": {"name": "测试审批", "id": "T-03"}},
            "report": rep,
            "edit_log": [{"no": 21, "old": "a", "new": "b", "who": "测试经办"}],
            "return_log": [],
            "supersedes_receipt": "",
            "filing_deadline": rep["filing_deadline"],
        }
        r = CLIENT.post("/api/submissions", json=payload)
        self.assertEqual(r.status_code, 200)
        sid = r.json()["id"]
        self.assertTrue(sid)

        r = CLIENT.get("/api/submissions")
        self.assertEqual(r.status_code, 200)
        self.assertGreaterEqual(r.json()["count"], 1)

        r = CLIENT.get(f"/api/submissions/{sid}")
        self.assertEqual(r.status_code, 200)
        d = r.json()
        # 回执号由服务端生成（RX-YYYYMMDD-NNNNN，当日递增）：客户端传入值一律忽略
        self.assertRegex(d["receipt_no"], r"^RX-\d{8}-\d{5}$")
        self.assertNotEqual(d["receipt_no"], "RX-CONTRACT-0001")
        self.assertEqual(d["edit_log"][0]["no"], 21)
        self.assertIn("report", d)

        # 同一报告重复提交（重试/双击）：幂等返回同一条记录
        r2 = CLIENT.post("/api/submissions", json=payload)
        self.assertEqual(r2.status_code, 200)
        self.assertEqual(r2.json()["id"], sid)

        # 不同报告：各自生成回执号、两条台账并存（历史上客户端随机回执碰撞
        # 会走幂等分支，把第二份报告静默并进第一条记录）
        rep2 = CLIENT.post("/api/report/BLOCK-01").json()
        r3 = CLIENT.post("/api/submissions", json=dict(payload, report_no=rep2["report_no"]))
        self.assertEqual(r3.status_code, 200)
        self.assertNotEqual(r3.json()["receipt_no"], d["receipt_no"])
        self.assertGreaterEqual(CLIENT.get("/api/submissions").json()["count"], 2)

        # 缺字段
        r4 = CLIENT.post("/api/submissions", json={"case_id": "BLOCK-01"})
        self.assertEqual(r4.status_code, 422)

        # 签字不齐全：台账拒绝写入（P1-3 收口）
        no_audit = dict(payload, receipt_no="RX-CONTRACT-0003", report_no=rep["report_no"] + "-X")
        no_audit.pop("audit")
        r5 = CLIENT.post("/api/submissions", json=no_audit)
        self.assertEqual(r5.status_code, 422)
        partial = dict(no_audit, audit={"operator": {"name": "测试经办", "id": "T-01"}})
        r6 = CLIENT.post("/api/submissions", json=partial)
        self.assertEqual(r6.status_code, 422)

    def test_07b_submissions_hardening(self):
        """报送链路加固回归：类型混淆 422、非法时间拒绝、supersedes 越权拦截、更正闭环。"""
        rep = CLIENT.post("/api/report/BLOCK-01").json()
        base = {
            "report_no": rep["report_no"], "case_id": rep["case_id"],
            "case_title": rep["title"], "customer": rep["meta"].get("customer", ""),
            "submitted_at": "2026-10-22 10:00:00", "version": 1,
            "operator": "T-01", "reviewer": "T-02", "approver": "T-03",
            "audit": {"operator": {"name": "经办", "id": "T-01"},
                      "reviewer": {"name": "复核", "id": "T-02"},
                      "approver": {"name": "审批", "id": "T-03"}},
            "report": rep, "edit_log": [], "return_log": [],
            "supersedes_receipt": "", "filing_deadline": rep["filing_deadline"],
        }
        # 类型混淆（历史上 int("abc")/[1].strip() 裸抛 500）→ 一律 422
        self.assertEqual(CLIENT.post("/api/submissions",
            json=dict(base, version="abc")).status_code, 422)
        self.assertEqual(CLIENT.post("/api/submissions",
            json=dict(base, version=[1])).status_code, 422)
        self.assertEqual(CLIENT.post("/api/submissions",
            json=dict(base, submitted_at=[1])).status_code, 422)
        self.assertEqual(CLIENT.post("/api/submissions",
            json=dict(base, submitted_at="昨天下午")).status_code, 422)

        # supersedes 指向不存在的回执 → 拒绝（此前 UPDATE 无校验，可越权改状态）
        self.assertEqual(CLIENT.post("/api/submissions",
            json=dict(base, supersedes_receipt="RX-20990101-00001")).status_code, 422)

        # 合法报送 → 服务端回执 → 更正闭环 → 重复更正被拦
        r = CLIENT.post("/api/submissions", json=base)
        self.assertEqual(r.status_code, 200)
        origin_receipt, origin_id = r.json()["receipt_no"], r.json()["id"]

        # 跨案例更正 → 拒绝
        other = CLIENT.post("/api/report/GREY-01").json()
        cross = dict(base, report_no=other["report_no"], case_id=other["case_id"],
                     supersedes_receipt=origin_receipt)
        self.assertEqual(CLIENT.post("/api/submissions", json=cross).status_code, 422)

        # 同案例更正 → 成功，原回执状态翻转
        corr_rep = CLIENT.post("/api/report/BLOCK-01").json()
        correction = dict(base, report_no=corr_rep["report_no"],
                          supersedes_receipt=origin_receipt, status="更正报告")
        r2 = CLIENT.post("/api/submissions", json=correction)
        self.assertEqual(r2.status_code, 200)
        self.assertEqual(
            CLIENT.get(f"/api/submissions/{origin_id}").json()["status"], "已更正")

        # 同一原回执二次更正 → 拒绝
        again_rep = CLIENT.post("/api/report/BLOCK-01").json()
        again = dict(base, report_no=again_rep["report_no"],
                     supersedes_receipt=origin_receipt, status="更正报告")
        self.assertEqual(CLIENT.post("/api/submissions", json=again).status_code, 422)

    def test_08_intake(self):
        case = CLIENT.get("/api/cases/BLOCK-01").json()
        payload = {
            "customer_info": case["customer_info"],
            "transactions": case["transactions"],
            "title": "新交易接入测试",
        }
        r = CLIENT.post("/api/intake", json=payload)
        self.assertEqual(r.status_code, 200)
        d = r.json()
        for key in ("case_id", "rule_hits", "similar_cases", "route"):
            self.assertIn(key, d)
        self.assertIn("R002", [h["rule_id"] for h in d["rule_hits"]])
        self.assertEqual(d["route"]["decision"], "人工复核")
        self.assertTrue(d["similar_cases"]["results"])
        self.assertTrue(d["case_id"].startswith("NEW-"))

        self.assertEqual(CLIENT.post("/api/intake", json={}).status_code, 422)
        bad = {"customer_info": {"name": "测试"}, "transactions": [{"date": "2026-01-01"}]}
        self.assertEqual(CLIENT.post("/api/intake", json=bad).status_code, 422)

        normal = CLIENT.get("/api/cases/PASS-01").json()
        r = CLIENT.post("/api/intake", json={
            "customer_info": normal["customer_info"],
            "transactions": normal["transactions"],
        })
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["rule_hits"], [])
        self.assertEqual(r.json()["route"]["decision"], "放行候选")

        # ---- 输入健壮性：四类曾直接 500 的输入，现在要么被归一化、要么 422 ----
        base_tx = {"date": "2026-09-01", "time": "10:00", "type": "转账收入",
                   "amount": 1000, "counterparty": "张某"}
        # 金额为字符串：归一化为数字后正常处理（不再 500）
        r = CLIENT.post("/api/intake", json={
            "customer_info": {"name": "测试客户（个人）", "open_date": "2020-01"},
            "transactions": [dict(base_tx, amount="1000")]})
        self.assertEqual(r.status_code, 200)
        # 金额为 0：业务上不合法 → 422（不再 500）
        r = CLIENT.post("/api/intake", json={
            "customer_info": {"name": "测试客户（个人）"},
            "transactions": [dict(base_tx, amount=0)] * 5})
        self.assertEqual(r.status_code, 422)
        # 金额为非数字字符串 → 422
        r = CLIENT.post("/api/intake", json={
            "customer_info": {"name": "测试客户（个人）"},
            "transactions": [dict(base_tx, amount="一万")]})
        self.assertEqual(r.status_code, 422)
        # 斜杠日期：归一化为 ISO 后正常处理（不再 500）
        r = CLIENT.post("/api/intake", json={
            "customer_info": {"name": "测试客户（个人）", "open_date": "2020/01"},
            "transactions": [dict(base_tx, date="2026/09/01")]})
        self.assertEqual(r.status_code, 200)
        # 无法解析的日期 → 422
        r = CLIENT.post("/api/intake", json={
            "customer_info": {"name": "测试客户（个人）"},
            "transactions": [dict(base_tx, date="9月1日")]})
        self.assertEqual(r.status_code, 422)
        # 缺 counterparty：补占位符后正常处理（不再 500）
        r = CLIENT.post("/api/intake", json={
            "customer_info": {"name": "测试客户（个人）"},
            "transactions": [{k: v for k, v in base_tx.items() if k != "counterparty"}]})
        self.assertEqual(r.status_code, 200)
        # 超大请求：笔数上限 → 422
        r = CLIENT.post("/api/intake", json={
            "customer_info": {"name": "测试客户（个人）"},
            "transactions": [dict(base_tx)] * 501})
        self.assertEqual(r.status_code, 422)

        # ---- P1-1：无姓名客户 → R017 身份不明，拦截理由不再套"制裁名单" ----
        r = CLIENT.post("/api/intake", json={
            "customer_info": {"open_date": "2020-01"},
            "transactions": [dict(base_tx)]})
        self.assertEqual(r.status_code, 200)
        d = r.json()
        hit_ids = [h["rule_id"] for h in d["rule_hits"]]
        self.assertIn("R017", hit_ids)
        self.assertNotIn("R005", hit_ids)
        self.assertEqual(d["route"]["decision"], "拦截")
        self.assertEqual(d["route"]["path"], "身份不明拒办")
        r017 = next(h for h in d["rule_hits"] if h["rule_id"] == "R017")
        self.assertIn("反洗钱法第28条", r017["legal_desc"] + r017["trigger_desc"])

    def test_09_linkage(self):
        r = CLIENT.get("/api/linkage/coverage")
        self.assertEqual(r.status_code, 200)
        cov = r.json()
        self.assertEqual(cov["count"], 18)
        # 同案例多份报送会各自沉淀 LIB- 条目，案例总数随之增加；
        # 覆盖矩阵必须守恒：每个案例都恰好归入一行（含"无法归类"出口）
        self.assertGreaterEqual(cov["total_cases"], 17)
        self.assertEqual(sum(t["case_count"] for t in cov["types"]), cov["total_cases"])
        self.assertGreaterEqual(cov["library_cases"], 1)
        self.assertIn("case_count", cov["types"][0])

        r = CLIENT.get("/api/linkage/effectiveness")
        self.assertEqual(r.status_code, 200)
        eff = r.json()
        self.assertEqual(len(eff["rules"]), 10)
        self.assertIn("R002", [x["rule_id"] for x in eff["rules"]])
        self.assertIn("R017", [x["rule_id"] for x in eff["rules"]])

        r = CLIENT.get("/api/case-library")
        self.assertEqual(r.status_code, 200)
        lib = r.json()
        self.assertGreaterEqual(lib["count"], 2)
        sources = {e["source"] for e in lib["entries"]}
        self.assertIn("submission", sources)
        self.assertIn("disposition", sources)
        self.assertTrue(any(e["case_id"].startswith("LIB-") for e in lib["entries"]))

        r = CLIENT.post("/api/linkage/backfill")
        self.assertEqual(r.status_code, 200)
        self.assertGreaterEqual(r.json()["submissions"], 1)
        self.assertGreaterEqual(r.json()["promoted"], 1)

    def test_12_cdd(self):
        """CDD：对公工商尽调 + 个人身份核验；未配置的数据源必须报错而不是假装查了。"""
        info = CLIENT.get("/api/cdd/info").json()
        ent_ids = [p["id"] for p in info["enterprise_providers"]]
        self.assertIn("mock-enterprise", ent_ids)
        self.assertIn("qcc", ent_ids)          # 接入位存在
        qcc = next(p for p in info["enterprise_providers"] if p["id"] == "qcc")
        self.assertFalse(qcc["available"])      # 未配 key 时不可用

        r = CLIENT.post("/api/cdd/enterprise", json={"name": "ZZ供应链有限公司（对公）"})
        self.assertEqual(r.status_code, 200)
        d = r.json()
        self.assertTrue(d["found"])
        self.assertEqual(d["conclusion"], "高风险")
        self.assertIn("风险标签", [c["item"] for c in d["checks"]])

        # 统一社会信用代码：GB 32100 真实校验位算法 + 按信用代码反查 + 名称一致性核对
        self.assertTrue(__import__("services.cdd", fromlist=["verify_uscc"]).verify_uscc(d["uscc"]))
        r = CLIENT.post("/api/cdd/enterprise", json={"uscc": "91310104MA1FL2XK72"})
        self.assertEqual(r.status_code, 200)
        by_uscc = r.json()
        self.assertTrue(by_uscc["found"])
        self.assertEqual(by_uscc["conclusion"], "高风险")
        self.assertIn("统一社会信用代码校验位（GB 32100）",
                      [c["item"] for c in by_uscc["checks"]])
        # 名称与信用代码不一致 → 一致性核对不通过
        r = CLIENT.post("/api/cdd/enterprise",
                        json={"name": "ZZ供应链有限公司（对公）", "uscc": "91310115MA1H8YQ238"})
        mismatch = next(c for c in r.json()["checks"] if c["item"] == "名称与信用代码一致性")
        self.assertFalse(mismatch["ok"])

        r = CLIENT.post("/api/cdd/enterprise", json={"name": "查无此企业有限公司"})
        self.assertEqual(r.status_code, 200)
        self.assertFalse(r.json()["found"])     # 查不到就说查不到

        r = CLIENT.post("/api/cdd/enterprise", json={"name": "某公司", "provider": "qcc"})
        self.assertEqual(r.status_code, 422)    # 未配置数据源 → 明确报错

        r = CLIENT.post("/api/cdd/personal",
                        json={"name": "赵某", "id_no": "999999199303125513", "id_expiry": "2030-01-01"})
        self.assertEqual(r.status_code, 200)
        d = r.json()
        self.assertTrue(d["verified"])
        self.assertNotIn("999999199303125513", d["id_masked"])   # 返回掩码，不回显完整号

        r = CLIENT.post("/api/cdd/personal", json={"name": "赵某", "id_no": "999999199303125510"})
        self.assertFalse(r.json()["verified"])  # 校验位错误

        r = CLIENT.post("/api/cdd/personal", json={"name": "赵", "id_no": "123"})
        self.assertEqual(r.status_code, 422)

    def test_13_transaction_fields(self):
        """交易字段三分：type 只描述方向，purpose 是用途，summary 是客户附言；外币带折算金额。"""
        from domain.rules.common import IN_TYPES, OUT_TYPES
        cases = CLIENT.get("/api/cases").json()["cases"]
        bad = []
        for c in cases:
            detail = CLIENT.get(f"/api/cases/{c['case_id']}").json()
            for t in detail["transactions"]:
                if t["type"] not in IN_TYPES + OUT_TYPES:
                    bad.append((c["case_id"], t["type"]))
                if "purpose" not in t or "currency" not in t or "amount_cny" not in t:
                    bad.append((c["case_id"], "缺少 purpose/currency/amount_cny"))
        self.assertEqual(bad, [])
        # 外币交易：原币与折人民币都必须在，且不相等
        fx = CLIENT.get("/api/cases/GREY-02").json()["transactions"]
        usd = [t for t in fx if t["currency"] == "USD"]
        self.assertTrue(usd)
        self.assertTrue(all(t["amount_cny"] > t["amount"] for t in usd))
        # 折算必须与 fx_rates.json 的取整汇率一致（界面汇率条与数据金额同源）
        rates = CLIENT.get("/api/fx").json()["rates"]
        for t in usd:
            self.assertAlmostEqual(t["amount_cny"], round(t["amount"] * rates["USD"], 2))
        # 汇率说明必须可手算核对：取整、非实时牌价、附真实中间价
        fx_info = CLIENT.get("/api/fx").json()
        self.assertTrue(all(isinstance(v, int) or float(v).is_integer() or v == 7.5
                            for v in rates.values()))
        self.assertIn("real_rates", fx_info)
        self.assertIn("as_of", fx_info)

    def test_14_reset_demo(self):
        r = CLIENT.post("/api/admin/reset-demo")
        self.assertEqual(r.status_code, 200)
        self.assertGreaterEqual(r.json()["submissions"], 1)
        self.assertGreaterEqual(r.json()["library_cases"], 1)

        self.assertEqual(CLIENT.get("/api/case-library").json()["count"], 0)
        self.assertEqual(CLIENT.get("/api/linkage/coverage").json()["library_cases"], 0)
        self.assertEqual(CLIENT.get("/api/submissions").json()["count"], 0)

        # 审计链不随重置清空：重置动作本身留痕，且链仍完整
        r = CLIENT.get("/api/audit", params={"action": "演示重置"})
        self.assertGreaterEqual(r.json()["total"], 1)
        v = CLIENT.get("/api/audit/verify").json()
        self.assertTrue(v["ok"], v)

    def test_10_audit(self):
        """审计链接口：写入留痕、读操作留痕、隐私红线、检索过滤、全链校验通过。"""
        r = CLIENT.get("/api/audit/verify")
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.json()["ok"], r.json())
        self.assertGreater(r.json()["records"], 0)  # 之前的报送/筛查已入链

        # 写操作留痕：报送写入
        r = CLIENT.get("/api/audit", params={"action": "报送写入", "limit": 200})
        self.assertEqual(r.status_code, 200)
        d = r.json()
        self.assertGreaterEqual(d["total"], 1)
        self.assertTrue(all(x["action"] == "报送写入" for x in d["records"]))
        rec = d["records"][0]
        self.assertIn("record_hash", rec)
        # 服务器时间戳：ISO + 毫秒 + 北京时区
        self.assertRegex(rec["occurred_at"],
                         r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}\+08:00$")

        # 读操作留痕：名单筛查（含未命中的）
        CLIENT.get("/api/screening", params={"q": "李某"})
        r = CLIENT.get("/api/audit", params={"action": "名单筛查"})
        self.assertGreaterEqual(r.json()["total"], 1)

        # CDD 留痕 + 隐私红线：审计里只有掩码，绝不落完整证件号
        CLIENT.post("/api/cdd/personal",
                    json={"name": "赵某", "id_no": "999999199303125513"})
        r = CLIENT.get("/api/audit", params={"action": "CDD身份核验"})
        self.assertGreaterEqual(r.json()["total"], 1)
        self.assertNotIn("999999199303125513",
                         json.dumps(r.json()["records"], ensure_ascii=False))

        # 非法参数：日期格式错误 → 422
        self.assertEqual(
            CLIENT.get("/api/audit", params={"date_from": "昨天"}).status_code, 422)

    def test_11_live_provider_signature(self):
        """Live 模式回归（P0-1）：available/diagnose 与 Mock 同签名，不再必然 500。

        不发起真实网络请求——把 LiveProvider.diagnose 替换为桩函数，
        只验证调用链（签名不匹配会在这里抛 TypeError → 500）。
        """
        import ai_diagnosis

        def fake_diagnose(self, case_id, case_data, rule_hits):
            return {"conclusion": "拦截", "official_type_no": "官方第1-1类",
                    "official_type_name": "疑似非法汇兑型地下钱庄", "risk_level": "高",
                    "analysis_points": ["live 桩诊断：签名链验证"], "elimination": "",
                    "materials_to_check": [], "suggestion": "提交可疑交易报告",
                    "model": "stub-model", "provider": "live"}

        original = ai_diagnosis.LiveProvider.diagnose
        ai_diagnosis.LiveProvider.diagnose = fake_diagnose
        os.environ["AML_AI_PROVIDER"] = "live"
        os.environ["OPENAI_API_KEY"] = "sk-dummy"
        try:
            r = CLIENT.post("/api/diagnose/BLOCK-01")
            self.assertEqual(r.status_code, 200)
            self.assertEqual(r.json()["ai_diagnosis"]["provider"], "live")
            r = CLIENT.post("/api/report/BLOCK-01")
            self.assertEqual(r.status_code, 200)
            self.assertEqual(r.json()["total"], 62)
        finally:
            ai_diagnosis.LiveProvider.diagnose = original
            os.environ.pop("AML_AI_PROVIDER", None)
            os.environ.pop("OPENAI_API_KEY", None)


if __name__ == "__main__":
    try:
        unittest.main(verbosity=2)
    finally:
        TMP.cleanup()
