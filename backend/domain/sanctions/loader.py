"""名单库加载与索引。

数据文件：backend/data/sanctions/sanctions.json（由 scripts/fetch_sanctions.py 生成，
源自联合国安理会综合名单与 OFAC SDN 公开数据）。仓库内自带快照，运行时不联网。

索引结构（首次访问时构建，进程内常驻）：
- exact：归一化名称/别名 → 条目（精确与别名命中走这里，O(1)）
- bigrams：二元组 → 条目下标集合（模糊匹配的候选召回，避免每次全量打分）
- 两者共用同一套 normalize.norm 口径，保证"搜得到"和"判得住"一致
"""
import json
import os
from collections import Counter, defaultdict
from functools import lru_cache

from .normalize import bigrams, norm

DATA_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "data", "sanctions"))
LIST_PATH = os.path.join(DATA_DIR, "sanctions.json")
META_PATH = os.path.join(DATA_DIR, "metadata.json")
ZH_ALIAS_PATH = os.path.join(DATA_DIR, "zh_aliases.json")

# 出现频率过高的二元组（AL / AN / IN 这类）不建索引：既占内存又不具区分度
STOP_BIGRAM_DF = 1200
# 单字词（如 "BANK"）命中面太大，超过这个条数就不进词索引
STOP_WORD_DF = 3000


class SanctionsUnavailable(RuntimeError):
    """名单库文件缺失或损坏。生产环境应视为致命错误，不能静默降级为"未命中"。"""


@lru_cache(maxsize=1)
def _load():
    if not os.path.isfile(LIST_PATH):
        raise SanctionsUnavailable(
            f"找不到名单库文件：{LIST_PATH}\n"
            "请运行 backend/scripts/fetch_sanctions.py 重新生成（需联网下载公开名单）。")

    with open(LIST_PATH, encoding="utf-8") as f:
        raw = json.load(f)
    entries = raw.get("entries") or []

    zh_aliases = {}
    if os.path.isfile(ZH_ALIAS_PATH):
        with open(ZH_ALIAS_PATH, encoding="utf-8") as f:
            zh_aliases = json.load(f).get("aliases", {})

    exact = defaultdict(list)      # norm 名称 → [(条目下标, 是否别名, 展示名)]
    postings = defaultdict(list)   # 二元组 → [条目下标]（中文/拼写容错的召回）
    words = defaultdict(list)      # 词 → [条目下标]（拉丁姓名的精确召回）
    all_keys = []                  # (归一化键, 条目下标, 展示名, 是否别名)，供包含匹配用
    countries = Counter()

    for idx, e in enumerate(entries):
        names = [(e.get("n") or "", False)]
        for a in e.get("a") or []:
            names.append((a, True))
        for zh in zh_aliases.get(e.get("id"), []):
            names.append((zh, True))
        seen = set()
        for name, is_alias in names:
            k = norm(name)
            if not k or k in seen:
                continue
            seen.add(k)
            exact[k].append((idx, is_alias, name))
            all_keys.append((k, idx, name, is_alias))
        for k in seen:
            for g in bigrams(k):
                postings[g].append(idx)
            for w in k.split():
                if len(w) >= 2:
                    words[w].append(idx)
        for c in e.get("ctry") or []:
            countries[c] += 1

    index = {}
    for g, idxs in postings.items():
        uniq = set(idxs)
        if len(uniq) <= STOP_BIGRAM_DF:
            index[g] = uniq
    word_index = {w: set(idxs) for w, idxs in words.items() if len(set(idxs)) <= STOP_WORD_DF}

    meta = {}
    if os.path.isfile(META_PATH):
        with open(META_PATH, encoding="utf-8") as f:
            meta = json.load(f)

    return {
        "entries": entries,
        "exact": dict(exact),
        "keys": all_keys,
        "bigram_index": index,
        "word_index": word_index,
        "zh_alias_count": sum(len(v) for v in zh_aliases.values()),
        "countries": countries,
        "meta": meta,
    }


def entries():
    return _load()["entries"]


def entry(idx: int):
    return _load()["entries"][idx]


def exact_lookup(key: str):
    return _load()["exact"].get(key, [])


def keys():
    """全部归一化键：(键, 条目下标, 展示名, 是否别名)。"""
    return _load()["keys"]


def candidates(text: str):
    """召回候选条目下标；返回 (下标集合, 召回方式)。

    拉丁姓名走词索引（"BIN LADIN" → 含 LADIN 的条目），召回干净；
    词索引召回不足（拼写错/中文）时退回二元组索引，保证"错一个字母也找得回来"。
    """
    data = _load()
    words = [w for w in text.split() if len(w) >= 2]
    hit = set()
    for w in words:
        hit |= data["word_index"].get(w, set())
    if len(hit) >= 200:
        return hit, "词索引召回"
    grams = bigrams(text)
    idx = data["bigram_index"]
    for g in grams:
        hit |= idx.get(g, set())
    if not hit:
        return set(), "无召回（二元组也未命中）"
    return hit, ("词索引 + 二元组召回" if words and len(hit) > 0 else "二元组召回")


def stats():
    data = _load()
    meta = data["meta"]
    return {
        "total": len(data["entries"]),
        "aliases_indexed": len(data["exact"]),
        "sources": meta.get("sources", []),
        "generated_at": meta.get("generated_at", ""),
        "zh_alias_count": data["zh_alias_count"],
        "countries": [{"country": c, "entries": n} for c, n in data["countries"].most_common(12)],
    }


def reset_cache():
    """名单库更新后（回溯筛查/热更新）清空进程内索引。"""
    _load.cache_clear()
