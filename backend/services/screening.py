"""名单筛查 v2：打分制模糊匹配 + 别名 + 回溯筛查（替代 v1 的子串包含匹配）。

匹配层级（阈值可配，演示初值；命中判定与 R005 的"名单项⊆客户名"口径兼容）：
- 完全命中（1.00）／别名一致（0.95）／名单项整体包含于查询对象（0.95）→ **命中**，先限制后核验
- 高度疑似（≥0.80，模糊相似达到）→ **命中**（按命中处置）
- 疑似（≥0.55，含"查询对象是名单项片段"的 0.70）→ 不处置，转人工核验
- 低相似（<0.55）→ 不展示

相似度 = 0.5×字符重合（Jaccard）+ 0.5×二元组 Dice；别名参与精确与模糊两种匹配。
v1 教训：双向子串包含会把"组织""洗钱"这类普通词片段直接判命中——v2 把
"查询对象只是名单项片段"降为疑似（0.70），不再直接处置。

诚实边界：演示级实现——未含拼音/音译变体库与转写引擎（生产必须接入官方
匹配引擎与名单版本管理）；名单为 3 条模拟数据，别名同为合成。
"""
import re

from domain.rules.sanctions import MOCK_SANCTION_LIST

MIN_QUERY_LEN = 2
HIT_THRESHOLD = 0.80        # ≥ 此值视为命中（处置）
SUSPECT_THRESHOLD = 0.55    # ≥ 此值展示为疑似（转人工）
BANDS = ((0.80, "高度疑似"), (0.55, "疑似"), (0.0, "低相似"))

# 演示名单主体的别名/曾用名（合成）
ALIASES = {
    "恐怖组织A": ["恐怖组织甲"],
    "制裁实体B": ["制裁实体乙"],
    "XX洗钱团伙": ["XX洗钱集团"],
}


def _norm(s: str) -> str:
    s = re.sub(r"（(对公|个人|演示)）$", "", (s or "").strip())
    return s.strip()


def _bigrams(s: str):
    return {s[i:i + 2] for i in range(len(s) - 1)} if len(s) > 1 else set()


def _similarity(a: str, b: str) -> float:
    if not a or not b:
        return 0.0
    A, B = set(a), set(b)
    jaccard = len(A & B) / len(A | B) if (A | B) else 0.0
    ga, gb = _bigrams(a), _bigrams(b)
    dice = 2 * len(ga & gb) / (len(ga) + len(gb)) if ga and gb else 0.0
    return round(0.5 * jaccard + 0.5 * dice, 3)


def _band(score: float) -> str:
    if score >= 0.95:
        return "完全命中" if score >= 1.0 else "命中"
    for threshold, name in BANDS:
        if score >= threshold:
            return name
    return "低相似"


def _best_match(query: str):
    """对全名单打分，返回 (score, match_type, entry_name)；无有效匹配返回 None。"""
    best = (0.0, "", "")
    for entry in MOCK_SANCTION_LIST:
        names = [entry] + ALIASES.get(entry, [])
        for idx, name in enumerate(names):
            score, mtype = 0.0, ""
            if query == name:
                score, mtype = 1.0, "完全一致"
            elif name in query and len(name) >= MIN_QUERY_LEN:
                score, mtype = 0.95, "名单主体整体出现在查询对象中"
            elif query in name and len(query) >= MIN_QUERY_LEN:
                score, mtype = 0.70, "查询对象仅为名单项片段（不直接判命中）"
            else:
                s = _similarity(query, name)
                if s >= SUSPECT_THRESHOLD:
                    score, mtype = s, "模糊相似（字符重合 + 二元组）"
            if idx > 0 and query == name and score < 0.95:
                score, mtype = 0.95, "别名一致"
            if score > best[0]:
                best = (score, mtype, entry)
    return best if best[0] >= SUSPECT_THRESHOLD else None


def screen(q: str):
    q = _norm(q)
    if not q:
        raise ValueError("请输入筛查对象")
    if len(q) < MIN_QUERY_LEN:
        raise ValueError(f"筛查对象至少 {MIN_QUERY_LEN} 个字符")
    match = _best_match(q)
    matches, hit = [], False
    if match:
        score, mtype, entry = match
        hit = score >= HIT_THRESHOLD
        matches.append({"name": entry, "list": "境内法定名单（模拟）",
                        "match_type": mtype, "score": score, "band": _band(score)})
    if hit:
        action = "命中即冻结账户，24 小时内人工复核，不经 AI 诊断"
    elif match:
        action = (f"未达命中阈值（{HIT_THRESHOLD}），按「疑似」转人工核验——"
                  f"v1 的子串匹配会把普通词片段直接判命中，v2 已降级为疑似")
    else:
        action = "未命中"
    return {
        "query": q,
        "hit": hit,
        "matches": matches,
        "list_size": len(MOCK_SANCTION_LIST),
        "action": action,
        "thresholds": {"hit": HIT_THRESHOLD, "suspect": SUSPECT_THRESHOLD,
                       "note": "演示初值；生产应按名单库官方匹配规范校准"},
    }


def back_screen(conn):
    """回溯筛查：名单更新后对存量客户全量复筛（监管检查必看环节，演示实现）。

    覆盖演示案例客户 + 已定性案例库主体；返回命中/疑似清单供人工处置。
    """
    from case_store import load_dataset
    from infra.case_repo import list_library

    targets = []
    for c in load_dataset().get("cases", []):
        name = _norm((c.get("customer_info") or {}).get("name", ""))
        if name:
            targets.append({"case_id": c["case_id"], "name": name})
    for row in list_library(conn):
        name = _norm((row.get("customer_info") or {}).get("name", ""))
        if name:
            targets.append({"case_id": row["case_id"], "name": name})

    hits, suspects = [], []
    for t in targets:
        match = _best_match(t["name"])
        if not match:
            continue
        score, mtype, entry = match
        item = {**t, "matched": entry, "score": score, "match_type": mtype}
        if score >= HIT_THRESHOLD:
            hits.append(item)
        else:
            suspects.append(item)
    hits.sort(key=lambda x: -x["score"])
    suspects.sort(key=lambda x: -x["score"])
    return {
        "screened": len(targets),
        "hits": hits,
        "suspects": suspects[:10],
        "list_size": len(MOCK_SANCTION_LIST),
        "thresholds": {"hit": HIT_THRESHOLD, "suspect": SUSPECT_THRESHOLD},
        "note": "回溯筛查：名单更新后对存量客户全量复筛（演示实现，覆盖演示案例与已定性库主体）；"
                "命中项应立即按名单处置流程办理并留痕。",
    }
