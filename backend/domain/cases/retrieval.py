"""历史案例召回：返回 top-k 相似案例、分档与建议路径。"""
from .config import load_config
from .similarity import CaseIndex


def classify(score, thresholds):
    if score >= thresholds["high"]:
        return "高度相似", "案例同类 · 转人工复核"
    if score >= thresholds["medium"]:
        return "参考相似", "AI 结合案例二次研判"
    return "低相似", "AI 独立研判"


def retrieve(target_case, cases, config=None, top_k=None):
    cfg = config or load_config()
    k = top_k or cfg["top_k"]
    target_id = target_case["case_id"]

    corpus = list(cases)
    if not any(c["case_id"] == target_id for c in corpus):
        corpus.append(target_case)
    index = CaseIndex(corpus)
    scored = []
    for case in cases:
        if case["case_id"] == target_id:
            continue
        sim = index.score(target_id, case["case_id"], cfg["weights"])
        band, route = classify(sim["score"], cfg["thresholds"])
        scored.append({
            "case_id": case["case_id"],
            "title": case["title"],
            "category": case["category"],
            "expected_conclusion": case["expected_conclusion"],
            "official_type_no": case.get("official_type_no", ""),
            "official_type_name": case.get("official_type_name", ""),
            "rules_hit": case.get("rules_hit") or [],
            "score": sim["score"],
            "score_percent": round(sim["score"] * 100, 1),
            "band": band,
            "route": route,
            "components": {
                "text": sim["text"], "structured": sim["structured"],
                "matched_channels": sim["matched_channels"],
                "matched_tx_types": sim["matched_tx_types"],
            },
        })

    scored.sort(key=lambda x: (-x["score"], x["case_id"]))
    return {
        "query_case_id": target_id,
        "method": cfg["method"],
        "thresholds": cfg["thresholds"],
        "top_k": k,
        "disclaimer": cfg["disclaimer"],
        "results": scored[:k],
    }
