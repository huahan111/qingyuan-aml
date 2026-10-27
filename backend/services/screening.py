"""名单筛查 v3：真实名单库（联合国安理会综合名单 + OFAC SDN）+ 处置分级。

v1 教训：双向子串包含会把"组织""洗钱"这类普通词片段直接判命中。
v2：改成打分制 + 片段降级为疑似，但名单只有 3 条模拟数据，等于没测过真名单。
v3：接真实名单（约 2 万条、2.2 万个别名），索引 + 候选召回，中文靠人工整理的中译名映射。

诚实边界（README《演示边界清单》同步）：
- 没有拼音/音译转写引擎：中文姓名对拉丁字母名单只能靠 zh_aliases.json 里那 15 个主体命中；
- 没有名单版本管理与增量回溯（back_screen 是演示版，每次全量复筛）；
- 阈值 0.80 / 0.55 是演示初值，生产必须按名单库官方匹配规范与误报率校准。
"""
from domain import sanctions
from domain.sanctions import loader as sanctions_loader


def _meta():
    st = sanctions_loader.stats()
    return {
        "total": st["total"],
        "aliases": st["aliases_indexed"],
        "generated_at": st["generated_at"],
        "sources": [{"name": s.get("name", ""), "entries": s.get("entries", 0),
                     "url": s.get("url", ""), "retrieved_at": s.get("retrieved_at", "")}
                    for s in st["sources"]],
        "zh_alias_count": st["zh_alias_count"],
        "top_countries": st["countries"],
    }


def _action_text(hit: bool, matches):
    """按命中条目的名单类型给处置口径：联合国=法定冻结，OFAC=审查+清算行确认。"""
    if not hit:
        return "未命中"
    un = [m for m in matches if m["source"] == "UN" and m["score"] >= sanctions.HIT_THRESHOLD]
    ofac = [m for m in matches if m["source"] == "OFAC" and m["score"] >= sanctions.HIT_THRESHOLD]
    parts = []
    if un:
        parts.append("命中联合国安理会综合名单：" + sanctions.policy_for({"src": "UN"})["measures"])
    if ofac:
        parts.append("命中 OFAC SDN：" + sanctions.policy_for({"src": "OFAC"})["measures"])
    return "；".join(parts)


def screen(q: str):
    q = (q or "").strip()
    if not q:
        raise ValueError("请输入筛查对象")
    if len(q) < sanctions.MIN_QUERY_LEN:
        raise ValueError(f"筛查对象至少 {sanctions.MIN_QUERY_LEN} 个字符")

    res = sanctions.search(q, top_k=5)
    matches = res["matches"]
    hit = res["hit"]

    if hit:
        action = _action_text(True, matches)
    elif matches:
        action = (f"未达命中阈值（{sanctions.HIT_THRESHOLD}），按「疑似」转人工核验——"
                  "v1 的片段匹配会把普通词直接判命中，v2 起已降级为疑似")
    else:
        action = ("未命中。注意：中文姓名与拉丁字母名单之间需要拼音/音译转写，"
                  "本演示只内置 15 个高知名度主体的中译名")

    return {
        "query": q,
        "hit": hit,
        "matches": matches,
        "list_size": _meta()["total"],
        "list_meta": _meta(),
        "candidates": res["candidates"],
        "method": res["method"],
        "action": action,
        "thresholds": {"hit": sanctions.HIT_THRESHOLD, "suspect": sanctions.SUSPECT_THRESHOLD,
                       "note": "演示初值；生产应按名单库官方匹配规范与本机构误报率校准"},
    }


def back_screen(conn):
    """回溯筛查：名单更新后对存量客户全量复筛（监管检查必看环节，演示实现）。"""
    from case_store import load_dataset
    from infra.case_repo import list_library

    targets = []
    seen = set()

    def add(case_id, name, dimension):
        name = (name or "").strip()
        key = (case_id, dimension, name)
        if name and key not in seen:
            seen.add(key)
            targets.append({"case_id": case_id, "name": name, "dimension": dimension})

    for c in load_dataset().get("cases", []):
        add(c["case_id"], (c.get("customer_info") or {}).get("name"), "客户")
        for t in c.get("transactions") or []:
            add(c["case_id"], t.get("counterparty"), "交易对手")
    for row in list_library(conn):
        add(row["case_id"], (row.get("customer_info") or {}).get("name"), "客户")

    hits, suspects = [], []
    for t in targets:
        res = sanctions.search(t["name"], top_k=1)
        if not res["matches"]:
            continue
        m = res["matches"][0]
        item = {**t, "matched": m["name"], "matched_id": m["entry_id"],
                "list": m["list"], "program": m["program"], "score": m["score"],
                "match_type": m["match_type"], "policy": m["policy"]}
        (hits if m["score"] >= sanctions.HIT_THRESHOLD else suspects).append(item)
    hits.sort(key=lambda x: -x["score"])
    suspects.sort(key=lambda x: -x["score"])
    meta = _meta()
    return {
        "screened": len(targets),
        "hits": hits,
        "suspects": suspects[:10],
        "list_size": meta["total"],
        "list_meta": meta,
        "thresholds": {"hit": sanctions.HIT_THRESHOLD, "suspect": sanctions.SUSPECT_THRESHOLD},
        "note": f"回溯筛查：对存量 {len(targets)} 个主体（客户 + 交易对手，去重后）按当前名单库"
                f"（{meta['total']} 条）全量复筛；命中的按名单类型分别处置"
                "（联合国=法定冻结，OFAC=加强审查并与清算行确认），全过程留痕。",
    }
