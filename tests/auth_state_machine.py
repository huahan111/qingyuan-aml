"""清源AML 报告授权状态机迁移测试。

覆盖状态链：草稿 → 经办签字（待复核）→ 复核预览 → 退回（回草稿）
→ 修改后重新三级授权（已签字待报送）→ 提交报送（已报送）。
同时校验：签字后内容锁定、预览只读、退回清空签字并留痕、报送后不可再改、
台账持久化修订与退回记录。

运行：python3 tests/auth_state_machine.py
依赖：pip install playwright && python -m playwright install chromium
"""
import http.client
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time

from playwright.sync_api import sync_playwright

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC_DB = os.path.join(ROOT, "backend", "data", "qingyuan.db")
PORT = 8138
BASE = f"http://127.0.0.1:{PORT}"

results = []
console_errors = []


def ck(name, cond, detail=""):
    results.append((name, bool(cond), detail))
    print(("PASS " if cond else "FAIL ") + name + ((" | " + str(detail)[:220]) if detail else ""))


def wait_health(proc, log_path):
    for _ in range(80):
        try:
            conn = http.client.HTTPConnection("127.0.0.1", PORT, timeout=1)
            conn.request("GET", "/api/health")
            resp = conn.getresponse()
            if resp.status == 200:
                conn.close()
                return True
            conn.close()
        except OSError:
            pass
        if proc.poll() is not None:
            break
        time.sleep(0.2)
    print(open(log_path, encoding="utf-8", errors="ignore").read()[-2000:])
    return False


def http_json(path):
    conn = http.client.HTTPConnection("127.0.0.1", PORT, timeout=3)
    conn.request("GET", path)
    resp = conn.getresponse()
    body = resp.read().decode("utf-8")
    conn.close()
    return json.loads(body)


def open_str(page):
    page.click('.case-item[data-cid="BLOCK-01"]')
    page.wait_for_timeout(350)
    page.click("#btnDiag")
    page.wait_for_timeout(1700)
    page.evaluate("[...document.querySelectorAll('button')].find(b=>b.textContent.includes('STR 初稿')).click()")
    page.wait_for_timeout(800)


def sign_current(page):
    """完成当前待签岗位：草稿先确认初稿；授权弹层已打开时直接签。"""
    if stage(page) == "draft":
        page.click("#docSignBtn")
        page.wait_for_timeout(300)
        confirm = page.locator("#signBody button", has_text="确认，进入授权")
        if confirm.count():
            confirm.first.click()
            page.wait_for_timeout(250)
    page.locator(".channel-tab", has_text="OA").first.click()
    page.wait_for_timeout(200)
    page.locator("#signBody .method-btn", has_text="通行密钥").first.click()
    page.wait_for_timeout(350)
    done = page.locator("#signBody button", has_text="完成，返回报告")
    if done.count():
        done.first.click()
        page.wait_for_timeout(350)


def stage(page):
    return page.evaluate("reportStage()")


def sig_keys(page):
    return page.evaluate("JSON.stringify(state.signatures)")


def main():
    tmp = tempfile.TemporaryDirectory()
    db = os.path.join(tmp.name, "auth.db")
    shutil.copy(SRC_DB, db)
    log_path = os.path.join(tmp.name, "server.log")
    env = os.environ.copy()
    env["QINGYUAN_DB"] = db
    env["QINGYUAN_PORT"] = str(PORT)
    proc = subprocess.Popen(
        [sys.executable, "backend/main.py"],
        cwd=ROOT, env=env,
        stdout=open(log_path, "w"), stderr=subprocess.STDOUT,
    )
    ok = False
    try:
        if not wait_health(proc, log_path):
            ck("服务启动", False, "health 未就绪")
            return 1

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page(viewport={"width": 1440, "height": 1000})
            page.on("console", lambda m: console_errors.append(m.text) if m.type == "error" else None)
            page.on("pageerror", lambda e: console_errors.append("pageerror: " + str(e)))
            page.goto(BASE + "/?v=auth", wait_until="networkidle")
            page.wait_for_timeout(800)

            open_str(page)
            report_no = page.evaluate("state.report.report_no")
            ck("S0 初始为草稿", stage(page) == "draft", page.inner_text("#docStatus"))
            ck("S0 初稿可编辑", page.evaluate("state.editMode") is True
               and page.is_visible("#btnEdit"))
            ck("S0 未签字", page.evaluate("Object.values(state.signatures).every(v=>!v)"))

            # ---- 草稿 → 经办签字 → 待复核 ----
            sign_current(page)
            ck("S1 经办签字后待复核", stage(page) == "pending_review", page.inner_text("#docStatus"))
            ck("S1 经办签字留痕", page.evaluate("state.signatures.operator.name") == "陈立"
               and "经办岗" in page.inner_text("#signBody"))
            ck("S1 内容锁定", not page.is_visible("#btnEdit")
               and not page.is_visible("#btnSaveEdit"))
            page.evaluate("toggleEdit()")
            page.wait_for_timeout(150)
            ck("S1 锁定后无法进入编辑", page.evaluate("state.editMode") is False)

            # ---- 复核只读预览 ----
            page.locator("#signBody button", has_text="预览报告内容").first.click()
            page.wait_for_timeout(500)
            ck("S2 预览打开报告", page.is_visible("#reportMask"))
            ck("S2 预览只读", "预览模式" in page.inner_text("#docStatus")
               and not page.is_visible("#btnEdit")
               and not page.is_visible("#docSignBtn")
               and not page.is_visible("#docSubmitBtn"))
            ck("S2 预览含经办签字", "陈立" in page.inner_text("#signBlock")
               and "NJ-AML-0231" in page.inner_text("#signBlock"))
            ck("S2 预览可返回授权", page.is_visible("#docBackAuth"))

            page.click("#docBackAuth")
            page.wait_for_timeout(300)
            ck("S2 返回授权弹层", page.is_visible("#signMask")
               and not page.is_visible("#reportMask"))
            ck("S2 返回后预览标记清除", page.evaluate("state.previewMode") is False)

            # ---- 复核退回 → 回草稿 ----
            page.locator("#signBody button", has_text="发现问题 · 退回经办修改").first.click()
            page.wait_for_timeout(250)
            # 退回原因必填（留痕）：不填原因点确认会被拦截
            page.locator("#signBody button", has_text="确认退回修改").first.click()
            page.wait_for_timeout(200)
            ck("S3 缺退回原因被拦截", stage(page) == "pending_review", page.inner_text("#docStatus"))
            page.fill("#returnReason", "状态机测试：退回原因留痕")
            page.locator("#signBody button", has_text="确认退回修改").first.click()
            page.wait_for_timeout(500)
            ck("S3 退回后回草稿", stage(page) == "draft", page.inner_text("#docStatus"))
            ck("S3 三级签字清空", page.evaluate("Object.values(state.signatures).every(v=>!v)"))
            ck("S3 退回留痕", page.evaluate("state.returnLog.length") == 1
               and page.evaluate("state.returnLog[0].reason") == "状态机测试：退回原因留痕"
               and "最近退回" in page.inner_text("#signBlock")
               and "退回原因：状态机测试：退回原因留痕" in page.inner_text("#signBlock"))
            page.evaluate("openReport(state.report)")
            page.wait_for_timeout(400)
            ck("S3 退回后恢复可编辑", page.is_visible("#btnEdit"))

            # ---- 退回后修改 → 重新授权 ----
            page.click("#btnEdit")
            page.wait_for_timeout(200)
            page.fill("#el-21", "状态机测试：退回后修订")
            page.click("#btnSaveEdit")
            page.wait_for_timeout(400)
            ck("S4 退回后修订生效", "版本 v2" in page.inner_text("#docMeta")
               and page.evaluate("state.editLog.length") == 1)

            sign_current(page)
            ck("S4 经办签字→待复核", stage(page) == "pending_review", page.inner_text("#docStatus"))
            sign_current(page)
            ck("S5 复核签字→待审批", stage(page) == "pending_approval", page.inner_text("#docStatus"))
            sign_current(page)
            ck("S6 审批签字→已签字待报送", stage(page) == "approved", page.inner_text("#docStatus"))
            ck("S6 签字不可编辑", not page.is_visible("#btnEdit")
               and not page.is_visible("#docSignBtn"))
            ck("S6 提交按钮可用", page.is_visible("#docSubmitBtn")
               and page.evaluate("!document.getElementById('docSubmitBtn').disabled"))

            # ---- 报送 → 已报送 ----
            page.click("#docSubmitBtn")
            page.wait_for_timeout(250)
            page.locator("#signBody button", has_text="确认提交报送").first.click()
            page.wait_for_timeout(900)
            ck("S7 报送后状态", stage(page) == "submitted", page.inner_text("#docStatus"))
            ck("S7 报送后不可再改/签", not page.is_visible("#btnEdit")
               and not page.is_visible("#docSignBtn")
               and page.evaluate("document.getElementById('docSubmitBtn').disabled"))
            ck("S7 回执写入报告", "RX-" in page.inner_text("#signBlock"))

            # ---- 台账快照 ----
            ledger = http_json("/api/submissions")
            row = next((x for x in ledger["submissions"] if x["report_no"] == report_no), None)
            ck("S8 台账有该报告", row is not None, ledger.get("count"))
            if row:
                detail = http_json(f"/api/submissions/{row['id']}")
                ck("S8 台账保留修订记录", len(detail["edit_log"]) == 1, detail["edit_log"])
                ck("S8 台账保留退回记录", len(detail["return_log"]) == 1, detail["return_log"])

            ck("console 无错误", len(console_errors) == 0, console_errors[:2])
            browser.close()

        ok = all(x[1] for x in results)
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
        tmp.cleanup()

    print(f"\n授权状态机：{sum(1 for _, c, _ in results if c)}/{len(results)} 通过")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
