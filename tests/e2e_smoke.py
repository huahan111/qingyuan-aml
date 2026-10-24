"""清源AML E2E 冒烟测试。

在临时数据库副本与独立端口上启动服务，走完：
工作台看板 → BLOCK-01 研判 → 62 项 STR → 修订 → 三级授权 → 报送 → 台账 → 归档 → 更正草稿。

运行：python3 tests/e2e_smoke.py
依赖：pip install playwright && python -m playwright install chromium
"""
import http.client
import os
import shutil
import subprocess
import sys
import tempfile
import time

from playwright.sync_api import sync_playwright

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC_DB = os.path.join(ROOT, "backend", "data", "qingyuan.db")
PORT = 8137
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


def sign_all(page):
    page.click("#docSignBtn")
    page.wait_for_timeout(300)
    confirm = page.locator("#signBody button", has_text="确认，进入授权")
    if confirm.count():
        confirm.first.click()
        page.wait_for_timeout(250)
    page.locator(".channel-tab", has_text="OA").first.click()
    page.wait_for_timeout(200)
    for _ in range(3):
        page.locator("#signBody .method-btn", has_text="通行密钥").first.click()
        page.wait_for_timeout(350)
    page.locator("#signBody button", has_text="完成，返回报告").first.click()
    page.wait_for_timeout(350)


def main():
    tmp = tempfile.TemporaryDirectory()
    db = os.path.join(tmp.name, "e2e.db")
    shutil.copy(SRC_DB, db)
    log_path = os.path.join(tmp.name, "server.log")
    env = os.environ.copy()
    env["QINGYUAN_DB"] = db
    env["QINGYUAN_PORT"] = str(PORT)
    env["QINGYUAN_READ_ONLY"] = "0"   # E2E 全流程含写操作（服务默认只读 fail-closed）
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
            page.goto(BASE + "/?v=e2e", wait_until="networkidle")
            page.wait_for_timeout(800)

            stats = page.inner_text("#dashStats")
            ck("工作台看板加载", "演示案例" in stats and "17" in stats, stats.replace("\n", " ")[:180])
            ck("案例库 17 条", page.locator(".case-item").count() == 17)
            ck("演示重置按钮可用", page.is_visible("#btnResetDemo"))
            ck("只读标签默认隐藏", not page.is_visible("#readonlyTag"))
            pages_ok = True
            for name in ("workbench", "flow", "alerts", "screening", "ctr", "cdd",
                         "rating", "rules", "reports"):
                page.click(f'.nav-item[data-page="{name}"]')
                page.wait_for_timeout(250)
                active = page.evaluate(
                    f"document.getElementById('page-{name}').classList.contains('active')")
                pages_ok = pages_ok and active
            ck("9 个页面可切换", pages_ok)
            page.click('.nav-item[data-page="workbench"]')
            page.wait_for_timeout(250)

            page.click('.case-item[data-cid="BLOCK-01"]')
            page.wait_for_timeout(350)
            page.click("#btnDiag")
            page.wait_for_timeout(1700)
            result = page.inner_text("#mainCol")
            ck("研判命中 R002", "R002" in result, result[:160])
            ck("分流为拦截", "拦截" in result)
            ck("相似案例召回", "相似案例召回" in result and "GREY-05" in result, result[:160])

            page.evaluate("[...document.querySelectorAll('button')].find(b=>b.textContent.includes('STR 初稿')).click()")
            page.wait_for_timeout(800)
            ck("报告 62 项", page.evaluate("state.report.elements.length") == 62,
               page.evaluate("state.report.elements.length"))
            ck("格式核对通过", "字段格式异常：0" in page.inner_text("#formatCheck"))
            # 第 24 项可疑交易特征代码未接官方代码集：留空 + manual，格式核对必须如实拦截
            ck("第24项待专岗补充（空值被拦截）", "第 1–24 项必填空缺：1" in page.inner_text("#formatCheck"))
            report_no = page.evaluate("state.report.report_no")

            page.fill("#el-21", "E2E 测试修订：已核实资金来源")
            page.click("#btnSaveEdit")
            page.wait_for_timeout(400)
            ck("修订升版本", "版本 v2" in page.inner_text("#docMeta"))

            sign_all(page)
            ck("三级授权完成", "已签字待报送" in page.inner_text("#docStatus"), page.inner_text("#docStatus"))
            page.click("#docSubmitBtn")
            page.wait_for_timeout(250)
            page.locator("#signBody button", has_text="确认提交报送").first.click()
            page.wait_for_timeout(900)
            ck("报送成功", "已报送" in page.inner_text("#docStatus"))
            page.click(".mask-close")
            page.wait_for_timeout(250)

            page.evaluate("showPage('workbench')")
            page.wait_for_timeout(300)
            page.click('.case-item[data-cid="EXCLUDE-01"]')
            page.wait_for_timeout(300)
            page.click("#btnDiag")
            page.wait_for_timeout(1700)
            ck("命中-排除分流", "命中-排除留痕" in page.inner_text("#mainCol"))
            page.once("dialog", lambda d: d.accept("E2E 人工确认排除"))
            page.click("button:has-text('确认排除并沉淀负样本')")
            page.wait_for_timeout(600)
            ck("负样本已沉淀", "已沉淀负样本" in page.inner_text("#mainCol"))

            page.evaluate("showPage('rules')")
            page.wait_for_timeout(900)
            ck("案例库自动沉淀", "LIB-" in page.inner_text("#caseLibraryBody")
               and "BLOCK-01" in page.inner_text("#caseLibraryBody"))
            ck("负样本入库", "DIS-EXCLUDE-01" in page.inner_text("#caseLibraryBody"))
            ck("规则有效性加载", "R002" in page.inner_text("#effectivenessBody"))
            ck("覆盖矩阵含案例支撑", "案例支撑" in page.inner_text("#coverageBody"))

            page.evaluate("showPage('reports')")
            page.wait_for_timeout(900)
            body = page.inner_text("#subBody")
            ck("台账写入", report_no in body and "BLOCK-01" in body, body[:180])
            page.fill("#subSearch", "BLOCK-01")
            page.wait_for_timeout(300)
            ck("台账筛选", "筛选 1 / 1 条" in page.inner_text("#subFilterCount"))

            sid = page.evaluate("state.submissions[0].id")
            page.evaluate(f"openArchivedSubmission({sid})")
            page.wait_for_timeout(700)
            ck("归档报告只读", "已报送归档" in page.inner_text("#docStatus"))
            ck("归档含修订留痕", "E2E 测试修订" in page.inner_text("#editLog"))
            page.click(".mask-close")
            page.wait_for_timeout(250)

            page.evaluate(f"correctSubmission({sid})")
            page.wait_for_timeout(800)
            ck("更正草稿生成", "更正报告" in page.inner_text("#docStatus"), page.inner_text("#docStatus"))
            page.click(".mask-close")
            page.wait_for_timeout(200)

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

    print(f"\nE2E：{sum(1 for _, c, _ in results if c)}/{len(results)} 通过")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
