"""大额交易报告服务：按 3 号令第五条阈值逐日累计，只做客观标准判断。"""
from collections import defaultdict

from case_store import get_case, list_cases


def build_ctr():
    rows = []
    for c in list_cases():
        case = get_case(c["case_id"])
        corp = "公司" in case["customer_info"].get("name", "")
        daily = defaultdict(lambda: {"cash": 0.0, "transfer": 0.0, "count": 0})
        for t in case["transactions"]:
            key = t["date"]
            daily[key]["count"] += 1
            if "现金" in t["type"]:
                daily[key]["cash"] += t["amount"]
            elif any(k in t["type"] for k in ("收入", "转入", "支出", "转出", "汇款")):
                daily[key]["transfer"] += t["amount"]

        for d, v in sorted(daily.items()):
            for kind, amount, th in (
                ("现金", v["cash"], 50000),
                ("转账", v["transfer"], 2000000 if corp else 500000),
            ):
                if amount >= th:
                    rows.append({"case_id": c["case_id"], "customer": c["customer_name"],
                                 "date": d, "kind": kind, "amount": round(amount, 2),
                                 "threshold": th, "count": v["count"]})

    return {
        "rows": rows,
        "count": len(rows),
        "cases": len({r["case_id"] for r in rows}),
        "thresholds": {"cash": 50000, "natural_transfer": 500000, "corp_transfer": 2000000},
        "notice": "大额报告为客观标准：达到阈值即报，不判断可疑，与可疑交易报告并行、互不替代。",
    }
