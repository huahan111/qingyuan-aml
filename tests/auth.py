"""鉴权模式测试（QINGYUAN_AUTH=1）：登录/登出、角色校验、审计实名、令牌防伪。

运行：python3 tests/auth.py
在独立临时库 + 鉴权开启的 TestClient 上验证；鉴权关闭的行为由 api_contract 全套覆盖。
"""
import os
import shutil
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BACKEND = os.path.join(ROOT, "backend")

TMP = tempfile.TemporaryDirectory()
TEST_DB = os.path.join(TMP.name, "auth.db")
shutil.copy(os.path.join(BACKEND, "data", "qingyuan.db"), TEST_DB)
os.environ["QINGYUAN_DB"] = TEST_DB
os.environ["QINGYUAN_READ_ONLY"] = "0"
os.environ["QINGYUAN_RATE_LIMIT"] = "0"
os.environ["QINGYUAN_AUTH"] = "1"      # 本套件的主角：鉴权开启
os.environ["QINGYUAN_DEMO_PASSWORD"] = "见后端启动日志"   # 测试固定口令，生产/演示由首次启动随机生成
sys.path.insert(0, BACKEND)

import main  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

CLIENT = TestClient(main.app)
PWD = "见后端启动日志"


def _login(username):
    r = CLIENT.post("/api/auth/login", json={"username": username, "password": PWD})
    assert r.status_code == 200, r.text
    return r.json()["user"]


def _submission_payload():
    rep = CLIENT.post("/api/report/BLOCK-01").json()
    return {
        "report_no": rep["report_no"], "case_id": rep["case_id"],
        "case_title": rep["title"], "customer": rep["meta"].get("customer", ""),
        "submitted_at": "2026-10-25 10:00:00", "version": 1,
        "operator": "T-01", "reviewer": "T-02", "approver": "T-03",
        "audit": {"operator": {"name": "经办", "id": "T-01"},
                  "reviewer": {"name": "复核", "id": "T-02"},
                  "approver": {"name": "审批", "id": "T-03"}},
        "report": rep, "edit_log": [], "return_log": [],
        "supersedes_receipt": "", "filing_deadline": rep["filing_deadline"],
    }


class AuthModeTest(unittest.TestCase):
    def test_01_unauthenticated_blocked(self):
        self.assertEqual(CLIENT.get("/api/cases").status_code, 401)
        self.assertEqual(CLIENT.get("/api/audit").status_code, 401)
        # 豁免路径可达
        self.assertEqual(CLIENT.get("/api/health").status_code, 200)
        self.assertTrue(CLIENT.get("/api/health").json()["auth_required"])
        me = CLIENT.get("/api/auth/me").json()
        self.assertTrue(me["auth_required"])
        self.assertIsNone(me["user"])
        self.assertIn("jingban", me["demo_hint"])
        self.assertNotIn(PWD, me["demo_hint"])   # 口令不回显，只在启动日志/环境变量里

    def test_02_login_logout(self):
        r = CLIENT.post("/api/auth/login", json={"username": "jingban", "password": "wrong"})
        self.assertEqual(r.status_code, 401)
        r = CLIENT.post("/api/auth/login", json={"username": "nosuch", "password": PWD})
        self.assertEqual(r.status_code, 401)
        user = _login("jingban")
        self.assertEqual(user["role_name"], "经办")
        self.assertEqual(user["id"], "NJ-AML-0231")
        # 登录后可访问
        self.assertEqual(CLIENT.get("/api/cases").status_code, 200)
        self.assertEqual(CLIENT.get("/api/auth/me").json()["user"]["username"], "jingban")
        # 登出后回到 401
        CLIENT.post("/api/auth/logout")
        self.assertEqual(CLIENT.get("/api/cases").status_code, 401)

    def test_03_role_enforcement(self):
        # 复核角色不能写台账（报送写入＝经办职责）
        _login("fuhe")
        payload = _submission_payload()
        r = CLIENT.post("/api/submissions", json=payload)
        self.assertEqual(r.status_code, 403)
        self.assertIn("经办", r.json()["detail"])
        # 经办可以
        _login("jingban")
        r = CLIENT.post("/api/submissions", json=_submission_payload())
        self.assertEqual(r.status_code, 200, r.text)
        # 经办不能重置演示（审批职责）
        r = CLIENT.post("/api/admin/reset-demo")
        self.assertEqual(r.status_code, 403)
        _login("shenpi")
        r = CLIENT.post("/api/admin/reset-demo")
        self.assertEqual(r.status_code, 200)

    def test_04_audit_actor_realname(self):
        _login("jingban")
        before = CLIENT.get("/api/audit", params={"action": "报送写入"}).json()["total"]
        CLIENT.post("/api/submissions", json=_submission_payload())
        d = CLIENT.get("/api/audit", params={"action": "报送写入"}).json()
        self.assertEqual(d["total"], before + 1)
        # 审计操作人为登录实名（不再"未鉴权"）
        self.assertEqual(d["records"][0]["actor"], "陈立（NJ-AML-0231）")
        # 演示重置的审计人是审批实名
        _login("shenpi")
        CLIENT.post("/api/admin/reset-demo")
        recs = CLIENT.get("/api/audit", params={"action": "演示重置"}).json()["records"]
        self.assertEqual(recs[0]["actor"], "王建国（NJ-CC-0006）")

    def test_05_tampered_cookie_rejected(self):
        _login("jingban")
        token = CLIENT.cookies.get("qy_session")
        bad = token[:-4] + ("dead" if not token.endswith("dead") else "beef")
        CLIENT.cookies.set("qy_session", bad)
        self.assertEqual(CLIENT.get("/api/cases").status_code, 401)
        # 过期令牌拒绝：伪造 exp 已过的时间戳无法通过 HMAC（签名不匹配即拒）
        CLIENT.cookies.set("qy_session", "eyJ1IjoiaiIsImUiOjF9." + "0" * 64)
        self.assertEqual(CLIENT.get("/api/cases").status_code, 401)
        # 恢复合法 cookie，避免污染 jar 影响后续用例（手动 set 与服务端下发的
        # cookie 属性不同，jar 中会并存同名 cookie，坏的那条仍会被发送）
        CLIENT.cookies.set("qy_session", token)

    def test_06_read_only_plus_auth(self):
        # 只读 + 鉴权并存：登录可用（auth 在只读白名单内），业务写入按只读语义 403
        _login("jingban")
        payload = _submission_payload()   # 先在可写状态生成报告草稿
        os.environ["QINGYUAN_READ_ONLY"] = "1"
        try:
            r = CLIENT.post("/api/submissions", json=payload)
            self.assertEqual(r.status_code, 403)
            self.assertIn("只读", r.json()["detail"])
            # 只读下仍可登录（登出后重新登录）
            CLIENT.post("/api/auth/logout")
            self.assertEqual(CLIENT.post("/api/auth/login",
                json={"username": "shenpi", "password": PWD}).status_code, 200)
        finally:
            os.environ["QINGYUAN_READ_ONLY"] = "0"


if __name__ == "__main__":
    try:
        unittest.main(verbosity=2)
    finally:
        TMP.cleanup()
