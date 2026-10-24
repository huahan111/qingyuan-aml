"""演示数据集读取层。

演示案例存放在独立 JSON 文件（backend/data/demo_cases.json），不写入 SQLite。
SQLite 只保存法规库、条款、规则库等参考型数据；未来真实/上传数据再走数据库。
"""
import json
import os

DEMO_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "demo_cases.json")


def load_dataset():
    with open(DEMO_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def dataset_meta():
    d = load_dataset()
    return {"dataset": d.get("dataset", "demo"), "name": d.get("name", "演示数据集"),
            "version": d.get("version", "1.0"), "synthetic": d.get("synthetic", True),
            "notice": d.get("notice", ""), "count": len(d.get("cases", []))}


def list_cases():
    out = []
    for c in load_dataset().get("cases", []):
        ci = c.get("customer_info", {})
        out.append({
            "case_id": c["case_id"], "title": c["title"], "category": c["category"],
            "expected_conclusion": c["expected_conclusion"],
            "official_type_no": c.get("official_type_no", ""),
            "official_type_name": c.get("official_type_name", ""),
            "customer_name": ci.get("name", ""),
            "occupation": ci.get("occupation", ""),
            "risk_level": ci.get("risk_level", ""),
            "rules_hit": c.get("rules_hit", []),
        })
    return out


def get_case(case_id):
    for c in load_dataset().get("cases", []):
        if c["case_id"] == case_id:
            return c
    return None
