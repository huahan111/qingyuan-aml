"""相似案例阈值与权重配置。

阈值为演示初始值，必须用已定性案例回测后调整；不是监管标准。
"""
import json
import os

_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "data", "case_similarity.json")


def load_config(path=None):
    with open(path or _PATH, encoding="utf-8") as f:
        cfg = json.load(f)
    if not (0 <= cfg["thresholds"]["medium"] < cfg["thresholds"]["high"] <= 1):
        raise ValueError("case_similarity.json 阈值必须满足 0 ≤ medium < high ≤ 1")
    total = sum(cfg["weights"]["structured"].values())
    if abs(total - 1) > 1e-6:
        raise ValueError("case_similarity.json 结构化权重之和必须为 1")
    return cfg
