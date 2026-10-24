"""案例相似度：字符 n-gram TF-IDF 余弦 + 结构化特征加权。"""
import math
from collections import Counter


class CaseIndex:
    """在给定案例集上建立轻量索引；不引入向量库或外部依赖。"""

    def __init__(self, cases):
        from .features import extract
        self.features = {c["case_id"]: extract(c) for c in cases}
        n = len(self.features)
        df = Counter()
        for f in self.features.values():
            df.update(set(f["text_counts"]))
        self.idf = {term: math.log((n + 1) / (freq + 1)) + 1 for term, freq in df.items()}
        self.vectors = {
            cid: self._vector(f["text_counts"]) for cid, f in self.features.items()
        }

    def _vector(self, counts):
        if not counts:
            return {}
        total = sum(counts.values())
        return {term: (count / total) * self.idf.get(term, 1.0)
                for term, count in counts.items()}

    @staticmethod
    def _cosine(a, b):
        if not a or not b:
            return 0.0
        dot = sum(v * b.get(k, 0.0) for k, v in a.items())
        na = math.sqrt(sum(v * v for v in a.values()))
        nb = math.sqrt(sum(v * v for v in b.values()))
        return dot / (na * nb) if na and nb else 0.0

    @staticmethod
    def _jaccard(a, b):
        if not a and not b:
            return 1.0
        return len(a & b) / len(a | b)

    def score(self, left_id, right_id, weights):
        left = self.features[left_id]
        right = self.features[right_id]
        text = self._cosine(self.vectors[left_id], self.vectors[right_id])

        amount_max = max(left["amount"], right["amount"])
        amount = min(left["amount"], right["amount"]) / amount_max if amount_max else 1.0
        count_max = max(left["count"], right["count"])
        count = min(left["count"], right["count"]) / count_max if count_max else 1.0

        sw = weights["structured"]
        structured = (
            sw["channels"] * self._jaccard(left["channels"], right["channels"])
            + sw["tx_types"] * self._jaccard(left["tx_types"], right["tx_types"])
            + sw["amount"] * amount
            + sw["night"] * (1 - abs(left["night_ratio"] - right["night_ratio"]))
            + sw["count"] * count
        )
        total = weights["text"] * text + (1 - weights["text"]) * structured
        return {
            "score": round(total, 4),
            "text": round(text, 4),
            "structured": round(structured, 4),
            "matched_channels": sorted(left["channels"] & right["channels"]),
            "matched_tx_types": sorted(left["tx_types"] & right["tx_types"]),
        }
