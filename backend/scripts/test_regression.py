"""清源AML MVP 回归测试。

覆盖：
1. 12 条演示案例的规则命中与期望一致
2. 每条案例生成的 STR 均为 62 项、四部分完整、无空值（第 24 项按设计留空待专岗补充）
3. 报告编号唯一（同案例连续生成不重复）
4. 上报台账表结构包含审计字段
5. 62 项要素定义来自 JSON 且编号连续、四部分齐全
6. 10 条可执行规则的参数键完整（数据驱动）

运行：python3 backend/scripts/test_regression.py
"""
import json
import os
import sqlite3
import sys

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE)

from domain.rules import run_engine
from ai_diagnosis import get_provider
from domain.report.builder import build_report
from domain.report.elements import ELEMENTS, PARTS

DB = os.path.join(BASE, "data", "qingyuan.db")
CASES = os.path.join(BASE, "data", "demo_cases.json")

REQUIRED_PARAMS = {
    "R001": ["cash_threshold"],
    "R002": ["window_days", "min_count", "ratio_min", "ratio_max", "dispersion_max",
             "span_window_multiple", "cash_threshold", "transfer_threshold"],
    "R003": ["out_within_days", "out_ratio", "min_counterparties", "balance_ratio_max"],
    "R004": ["night_start", "night_end", "night_ratio", "min_days", "min_count_per_day"],
    "R005": [],
    "R006": ["account_age_days", "cross_border_natural", "cross_border_corp", "early_warning_ratio"],
    "R007": ["monthly_transfers"],
    "R008": ["keywords", "amount_multiple", "amount_min", "amount_max", "min_count"],
    "R009": ["collect_min_count", "min_in_counterparties", "amount_spread_max",
             "concentrated_ratio", "min_out_counterparties", "min_out_count"],
    "R017": [],
}

# 按设计允许留空的要素：
#  24 可疑交易特征代码——官方代码集未接入，专岗补充
#  BLOCK-08 客户拒不出示证件：5/6/26/27 证件类型与号码如实留空（11号令第四十一条（一）场景）
MANUAL_BY_CASE = {"BLOCK-08": {5, 6, 24, 26, 27}}
DEFAULT_MANUAL = {24}


def main():
    cases = json.load(open(CASES, encoding="utf-8"))["cases"]
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    provider = get_provider()
    failures = []
    passed = 0

    for c in cases:
        cid = c["case_id"]
        hits = run_engine(c["transactions"], c["customer_info"], conn)
        got = sorted(h["rule_id"] for h in hits)
        exp = sorted(c.get("rules_hit") or [])
        if got != exp:
            failures.append(f"{cid} 规则命中不一致：期望 {exp}，实际 {got}")
            continue

        diag = provider.diagnose(cid, c, hits)
        rep = build_report(c, diag, hits, conn)
        if rep["total"] != 62:
            failures.append(f"{cid} 要素数 {rep['total']} != 62")
            continue
        if len({e["part"] for e in rep["elements"]}) != 4:
            failures.append(f"{cid} 四部分不完整")
            continue
        empty = [e["no"] for e in rep["elements"]
                 if str(e.get("value", "")).strip() == "" and e["no"] not in MANUAL_BY_CASE.get(cid, DEFAULT_MANUAL)]
        if empty:
            failures.append(f"{cid} 存在空值项：{empty}")
            continue
        manual = [e["no"] for e in rep["elements"] if e["source"] == "manual"]
        expected_manual = MANUAL_BY_CASE.get(cid, DEFAULT_MANUAL)
        if set(manual) != expected_manual:
            failures.append(f"{cid} 待人工补充项应为 {sorted(expected_manual)}，实际 {manual}")
            continue
        if not rep.get("filing_deadline"):
            failures.append(f"{cid} 缺少法定报送时限")
            continue
        passed += 1

    a = build_report(cases[0], provider.diagnose(cases[0]["case_id"], cases[0], []), [], conn)
    b = build_report(cases[0], provider.diagnose(cases[0]["case_id"], cases[0], []), [], conn)
    if a["report_no"] == b["report_no"]:
        failures.append("报告编号重复：" + a["report_no"])
    else:
        passed += 1

    if (len(ELEMENTS) == 62 and set(PARTS) == {1, 2, 3, 4}
            and [e["no"] for e in ELEMENTS] == list(range(1, 63))):
        passed += 1
    else:
        failures.append("要素定义不符合 62 项 / 四部分 / 编号连续")

    stored_params = {
        row[0]: json.loads(row[1] or "{}")
        for row in conn.execute("SELECT rule_id, params FROM rules").fetchall()
        if row[0] in REQUIRED_PARAMS
    }
    missing_params = [
        f"{rid}.{key}" for rid, keys in REQUIRED_PARAMS.items()
        for key in keys if key not in stored_params.get(rid, {})
    ]
    if missing_params:
        failures.append("规则参数缺失：" + ", ".join(missing_params))
    else:
        passed += 1

    cols = {r[1] for r in conn.execute("PRAGMA table_info(submissions)").fetchall()}
    need = {"report_no", "receipt_no", "audit_json", "report_json",
            "edit_log_json", "return_log_json", "supersedes_receipt", "filing_deadline"}
    if need - cols:
        failures.append("台账表缺少字段：" + ", ".join(sorted(need - cols)))
    else:
        passed += 1

    # 报送时限必须真的按法定节假日计算：节假日表未加载、或跨国庆算错，都判失败
    from datetime import date
    from domain.report.deadline import add_workdays, holiday_count
    if holiday_count() < 20:
        failures.append(f"节假日表未加载（{holiday_count()} 天）：报送时限会跨假期算错")
    elif add_workdays(date(2026, 9, 30), 5) != date(2026, 10, 13):
        failures.append(f"跨国庆 5 工作日计算错误：{add_workdays(date(2026, 9, 30), 5)}"
                        f"（应为 2026-10-13，跳过 10/1–10/7 且计入 10/10 调休上班）")
    else:
        passed += 1
    conn.close()

    total = passed + len(failures)
    print(f"回归测试：{passed}/{total} 通过")
    for f in failures:
        print("FAIL " + f)
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
