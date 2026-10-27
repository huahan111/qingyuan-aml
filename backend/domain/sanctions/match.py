"""名单匹配：分层判定 + 打分制模糊匹配。

匹配层级（阈值可配，与 R005"名单项 ⊆ 客户名"口径兼容）：
- 归一化后完全一致（1.00）→ 命中
- 别名/曾用名一致（0.95）→ 命中
- 名单项整体出现在查询对象中（0.95）→ 命中（"XX 关联人"这类写法仍算命中）
- 查询对象只是名单项的一段（0.70）→ 疑似，不直接处置（v1 把它判命中，误报率高）
- 模糊相似 ≥ 0.80 → 命中；≥ 0.55 → 疑似；< 0.55 → 不展示

诚实边界：未内置拼音/音译变体与"张三 vs ZHANG SAN"的转写引擎，中文姓名对拉丁字母名单
无法匹配；覆盖办法是 zh_aliases.json 里人工整理的高知名度中译名，不是全量翻译。
"""
from . import loader
from .normalize import bigrams, norm
from .policy import policy_for

HIT_THRESHOLD = 0.80
SUSPECT_THRESHOLD = 0.55
MIN_QUERY_LEN = 2
# 名单项整体包含于查询对象时，过短的名单项容易误伤（如 "ADF"）；中文名本身短（"东伊运"），
# 所以按字符集分开设阈值：拉丁字母 4 位起，中日韩 2 字起
CONTAIN_MIN_LEN_ASCII = 4
CONTAIN_MIN_LEN_CJK = 2


def _contain_ok(key: str) -> bool:
    return len(key) >= (CONTAIN_MIN_LEN_ASCII if key.isascii() else CONTAIN_MIN_LEN_CJK)


def similarity(a: str, b: str) -> float:
    """0.5×字符重合（Jaccard）+ 0.5×二元组 Dice。中文按字、拉丁按字母，同一套口径。"""
    if not a or not b:
        return 0.0
    A, B = set(a), set(b)
    jaccard = len(A & B) / len(A | B) if (A | B) else 0.0
    ga, gb = bigrams(a), bigrams(b)
    dice = 2 * len(ga & gb) / (len(ga) + len(gb)) if ga and gb else 0.0
    return round(0.5 * jaccard + 0.5 * dice, 3)


def band_of(score: float) -> str:
    if score >= 1.0:
        return "完全命中"
    if score >= 0.95:
        return "命中"
    if score >= 0.70:
        return "高度疑似"
    if score >= SUSPECT_THRESHOLD:
        return "疑似"
    return "低相似"


def _detail(idx: int, name: str, is_alias: bool) -> dict:
    e = loader.entry(idx)
    src = e.get("src", "")
    return {
        "name": e.get("n", ""),
        "entry_id": e.get("id", ""),
        "list": "联合国安理会综合名单" if src == "UN" else "OFAC SDN（美国财政部）",
        "source": src,
        "type": e.get("t", ""),
        "program": " / ".join(e.get("prog") or []),
        "country": "、".join(e.get("ctry") or []),
        "listed_on": e.get("d", ""),
        "matched_name": name,
        "matched_as_alias": bool(is_alias),
        "policy": policy_for(e),
    }


def search(query: str, top_k: int = 5):
    """返回 {"matches": [...], "hit": bool, "candidates": n, "method": ...}。"""
    q = norm(query)
    if not q:
        return {"matches": [], "hit": False, "candidates": 0, "method": "空查询"}
    if len(q) < MIN_QUERY_LEN:
        return {"matches": [], "hit": False, "candidates": 0, "method": "查询过短"}

    found = []  # (score, match_type, idx, matched_name, is_alias)
    exact_idx = set()

    # 1) 精确与别名
    for idx, is_alias, name in loader.exact_lookup(q):
        exact_idx.add(idx)
        found.append((0.95 if is_alias else 1.0, "别名一致" if is_alias else "完全一致",
                      idx, name, is_alias))

    # 2) 名单项整体出现在查询对象中（"XX 关联人"仍判命中）
    if not found:
        for k, idx, name, is_alias in loader.keys():
            if _contain_ok(k) and k in q:
                found.append((0.95, "名单主体整体出现在查询对象中", idx, name, is_alias))
                break

    # 3) 模糊：先用二元组召回候选，只对候选打分
    cand, method = loader.candidates(q)
    if not cand and not found:
        return {"matches": [], "hit": False, "candidates": 0, "method": method}

    scored = {}
    for idx in cand:
        if idx in exact_idx:
            continue  # 精确/别名命中已经定了，别被模糊分数改名
        e = loader.entries()[idx]
        best = 0.0
        best_name, best_alias = "", False
        for name in [e.get("n", "")] + list(e.get("a") or []):
            s = similarity(q, norm(name))
            if s > best:
                best, best_name, best_alias = s, name, name != e.get("n")
        if best >= SUSPECT_THRESHOLD:
            scored[idx] = (best, "模糊相似（字符重合 + 二元组）", best_name, best_alias)

    # 4) 查询对象只是名单项的一段 → 疑似 0.70（不直接处置）
    if not found:
        for idx in cand:
            e = loader.entries()[idx]
            for name in [e.get("n", "")] + list(e.get("a") or []):
                k = norm(name)
                if q in k and len(q) >= MIN_QUERY_LEN and len(k) > len(q):
                    if idx not in scored or scored[idx][0] < 0.70:
                        scored[idx] = (0.70, "查询对象仅为名单项片段（不直接判命中）",
                                       name, name != e.get("n"))
                    break

    for idx, (s, mtype, name, is_alias) in scored.items():
        found.append((s, mtype, idx, name, is_alias))

    # 去重（同一 entry 取最高分），排序截断
    best_by_entry = {}
    for s, mtype, idx, name, is_alias in found:
        cur = best_by_entry.get(idx)
        if cur is None or s > cur[0]:
            best_by_entry[idx] = (s, mtype, name, is_alias)
    ranked = sorted(best_by_entry.items(), key=lambda kv: -kv[1][0])[:top_k]

    matches = []
    for idx, (s, mtype, name, is_alias) in ranked:
        d = _detail(idx, name, is_alias)
        d.update({"score": s, "band": band_of(s), "match_type": mtype})
        matches.append(d)

    return {
        "matches": matches,
        "hit": any(m["score"] >= HIT_THRESHOLD for m in matches),
        "candidates": len(cand),
        "method": method,
    }


def fast_hit(text: str):
    """规则引擎专用快路径：只做精确/别名/整体包含，不做模糊打分（保证逐案判定确定、快）。"""
    q = norm(text)
    if len(q) < MIN_QUERY_LEN:
        return None
    hits = loader.exact_lookup(q)
    if hits:
        idx, is_alias, name = hits[0]
        return _detail(idx, name, is_alias)
    for k, idx, name, is_alias in loader.keys():
        if _contain_ok(k) and k in q:
            return _detail(idx, name, is_alias)
    return None
