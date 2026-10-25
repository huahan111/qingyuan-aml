"""规则阈值最小回测：在已标注演示集上统计每条可执行规则的命中与有效性。

用法：python3 backend/scripts/rule_backtest.py            # 打印并写 docs/rule_backtest_report.md

口径（与规则有效性页同源，逐条可复算）：
- 确认命中：命中案例的期望结论为拦截或灰区（人工复核）
- 排除命中：命中案例期望为放行/命中-排除（如 EXCLUDE-01：规则触发但材料齐备应排除——设计行为，不是误报）
- 误命中：放行类案例（PASS-*）出现规则命中（按设计应为 0）

诚实边界：17 条案例为自建合成标注，样本量不支持统计意义上的召回/误报率结论；
本报告的价值是把"每条规则的命中/确认/排除"变成可复算数字的第一轮基线——
生产环境须用本机构已定性案例（真实报送与排除记录）重跑同一脚本。
"""
import json
import os
import sys
from collections import defaultdict
from datetime import date

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE)

from case_store import load_dataset                     # noqa: E402
from domain.rules import RULE_FUNCS, run_engine         # noqa: E402
from infra.db import get_db                             # noqa: E402


def backtest():
    cases = load_dataset().get("cases", [])
    conn = get_db()
    per_rule = defaultdict(lambda: {"hits": [], "confirm": 0, "exclude": 0})
    overall = {"cases": len(cases), "intercept_hit": 0, "intercept_total": 0,
               "pass_clean": 0, "pass_total": 0, "grey_hit": 0, "grey_total": 0,
               "mismatch": []}
    try:
        for c in cases:
            hits = run_engine(c["transactions"], c["customer_info"], conn)
            hit_ids = sorted({h["rule_id"] for h in hits})
            expect_ids = sorted(set(c.get("rules_hit") or []))
            if hit_ids != expect_ids:
                overall["mismatch"].append(
                    {"case": c["case_id"], "engine": hit_ids, "labeled": expect_ids})
            category = c.get("category")
            conclusion = str(c.get("expected_conclusion", ""))
            if category == "intercept":
                overall["intercept_total"] += 1
                overall["intercept_hit"] += 1 if hit_ids else 0
            elif category == "pass":
                overall["pass_total"] += 1
                overall["pass_clean"] += 1 if not hit_ids else 0
            elif category == "grey":
                overall["grey_total"] += 1
                overall["grey_hit"] += 1 if hit_ids else 0
            for rid in hit_ids:
                slot = per_rule[rid]
                slot["hits"].append(c["case_id"])
                # 期望放行或"命中-排除"（EXCLUDE-01：规则触发但材料齐备应排除）计入"排除"，其余计入"确认"
                if category == "pass" or "放行" in conclusion or "排除" in conclusion:
                    slot["exclude"] += 1
                else:
                    slot["confirm"] += 1
    finally:
        conn.close()
    return per_rule, overall


def render(per_rule, overall):
    lines = []
    lines.append(f"# 规则阈值回测报告（最小实证 · {date.today().isoformat()}）\n")
    lines.append("> 生成：`python3 backend/scripts/rule_backtest.py`（数字逐条可复算）。"
                 "样本为 17 条已标注合成演示案例——**是基线不是统计结论**；"
                 "生产环境用本机构已定性案例重跑同一脚本。\n")
    lines.append("## 总体\n")
    lines.append(f"- 引擎命中 vs 数据集标注：**{'一致' if not overall['mismatch'] else '存在不一致'}**"
                 f"（{overall['cases']} 条案例逐条比对）")
    if overall["mismatch"]:
        for m in overall["mismatch"]:
            lines.append(f"  - {m['case']}: 引擎 {m['engine']} vs 标注 {m['labeled']}")
    lines.append(f"- 拦截类案例规则命中率：**{overall['intercept_hit']}/{overall['intercept_total']}**")
    lines.append(f"- 放行类案例零误命中：**{overall['pass_clean']}/{overall['pass_total']}**")
    lines.append(f"- 灰区案例有规则命中（命中-人工复核并存）：{overall['grey_hit']}/{overall['grey_total']}"
                 "（灰区定义即含'规则未中但存疑'，未命中属正常）\n")
    lines.append("## 分规则\n")
    lines.append("| 规则 | 命中案例数 | 确认命中 | 排除命中 | 命中案例 |")
    lines.append("|---|---|---|---|---|")
    for rid in sorted(per_rule):
        s = per_rule[rid]
        lines.append(f"| {rid} | {len(s['hits'])} | {s['confirm']} | {s['exclude']} | "
                     f"{'、'.join(s['hits'])} |")
    lines.append("\n## 口径说明\n")
    lines.append("- **确认命中**＝命中案例期望结论为拦截/灰区；**排除命中**＝期望放行或命中-排除"
                 "（EXCLUDE-01 为设计用例：R003 触发但合同发票齐备、人工确认排除并沉淀负样本）。")
    lines.append("- 阈值来源：3 号令等条文量化项直接采用官方口径（现金 5 万、自然人转账 50 万等）；"
                 "其余为演示初值。基线标定（客户自身历史基线作分母）与更大样本回测列入生产化路径。")
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    per_rule, overall = backtest()
    report = render(per_rule, overall)
    print(report)
    out = os.path.join(BASE, "..", "docs", "rule_backtest_report.md")
    with open(out, "w", encoding="utf-8") as f:
        f.write(report)
    print("已写入 →", os.path.abspath(out))
