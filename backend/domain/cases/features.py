"""案例特征提取：只取可观测信息，不使用历史结论/官方类型，避免标签泄漏。"""
import re
from collections import Counter

_CJK_RUN = re.compile(r"[\u4e00-\u9fff]+")
_WORD = re.compile(r"[A-Za-z0-9]+")


def tokens(text):
    """中文按单字 + 二元组切分，英文/数字按词切分，不依赖分词库。"""
    text = str(text or "")
    terms = []
    for run in _CJK_RUN.findall(text):
        terms.extend(run)
        terms.extend(run[i:i + 2] for i in range(len(run) - 1))
    terms.extend(w.lower() for w in _WORD.findall(text))
    return terms


def _night(tx):
    try:
        hour = int(str(tx.get("time", "12:00")).split(":")[0])
    except (ValueError, IndexError):
        return False
    return hour >= 22 or hour < 6


def extract(case):
    ci = case.get("customer_info") or {}
    txs = case.get("transactions") or []

    text_parts = [
        ci.get("occupation", ""), ci.get("income", ""), ci.get("employer", ""),
        " ".join(ci.get("tags") or []),
    ]
    for t in txs:
        text_parts.append(" ".join(str(t.get(k, "")) for k in
                                   ("type", "summary", "channel", "counterparty")))
    text = " ".join(text_parts)

    counts = Counter(tokens(text))
    total = sum(t["amount"] for t in txs)
    night_count = sum(1 for t in txs if _night(t))

    return {
        "case_id": case["case_id"],
        "text_counts": counts,
        "channels": {t.get("channel", "") for t in txs if t.get("channel")},
        "tx_types": {t.get("type", "") for t in txs if t.get("type")},
        "amount": total,
        "count": len(txs),
        "night_ratio": night_count / len(txs) if txs else 0.0,
    }
