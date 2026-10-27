"""地区风险：FATF 名单查询 + 名单库国别派生统计。

为什么单列一块：名单命中与地区风险是两套机制。名单是"这个人/这个机构不能碰"，
地区是"这个国家整体风险高，业务要加码审查"。混在一起就会出现"俄罗斯是高风险国家
所以见俄即拒"这种既不合规也不可执行的结论。
"""
import json
import os
from functools import lru_cache

DATA_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "data", "jurisdictions.json"))


@lru_cache(maxsize=1)
def _load():
    with open(DATA_PATH, encoding="utf-8") as f:
        return json.load(f)


def _norm(s: str) -> str:
    return (s or "").strip().lower().replace(" ", "").replace("　", "")


def lookup(q: str):
    q = (q or "").strip()
    if not q:
        raise ValueError("请输入国家或地区名称")
    data = _load()
    nq = _norm(q)
    for j in data["jurisdictions"]:
        keys = {_norm(j["zh"]), _norm(j["en"]), _norm(j["code"])}
        if nq in keys or (len(nq) >= 2 and any(nq in k for k in keys)):
            tier = data["tiers"][j["tier"]]
            return {"query": q, "found": True, "jurisdiction": j, "tier": j["tier"], **tier}
    tier = data["tiers"]["normal"]
    return {"query": q, "found": False, "jurisdiction": None, "tier": "normal", **tier,
            "note": "未在 FATF 2026-06 名单内。这不等于没有风险——"
                    "还要看单边制裁项目、本机构国别风险评级与具体交易背景。"}


def overview():
    data = _load()
    from domain.sanctions import loader as sanctions_loader

    entries = sanctions_loader.entries()
    stats = sanctions_loader.stats()
    russia = sum(1 for e in entries if any("RUSSIA" in p for p in (e.get("prog") or [])))
    groups = {}
    for j in data["jurisdictions"]:
        groups.setdefault(j["tier"], []).append(j)
    return {
        "as_of": data["_meta"]["as_of"],
        "source": data["_meta"]["source"],
        "url": data["_meta"]["url"],
        "change_log": data["_meta"]["change_log"],
        "boundary": data["_meta"]["boundary"],
        "not_listed_note": data["_meta"]["not_listed_note"],
        "tiers": [{"tier": k, **v, "count": len(groups.get(k, []))}
                  for k, v in data["tiers"].items()],
        "groups": [{"tier": k, "label": data["tiers"][k]["label"], "items": groups.get(k, [])}
                   for k in ("call_for_action", "increased_monitoring")],
        "list_derived": {
            "top_countries": stats["countries"],
            "russia_entries": russia,
            "note": f"名单库 {stats['total']} 条中，按国籍/地址统计条目最多的国家如上；"
                    f"俄罗斯相关制裁项目（RUSSIA-EO14024 等）{russia} 条——"
                    "俄罗斯不在 FATF 名单，但属单边制裁范围，两者要分开看。",
        },
    }
