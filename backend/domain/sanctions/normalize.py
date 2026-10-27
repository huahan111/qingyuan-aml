"""名单名称归一化：抓取脚本与运行时共用同一套规则，避免两边口径漂移。

归一化只做"去掉不影响比对"的处理，不做音译、不做拼音转换：
- Unicode NFKD 去重音（José → Jose），保留 CJK 字符
- 全角转半角（Ｎ → N）
- 大写、标点与多余空白归一
- 去掉常见法人后缀（LTD / LIMITED / CO / COMPANY），减少"XX 有限公司 vs XX LTD"这类假阴性
"""
import re
import unicodedata

# 只作为"后缀噪音"处理，出现在名称中间时不动（避免把 "CO., LTD." 之外的词误删）
_SUFFIX_RE = re.compile(
    r"\b(CO|COMPANY|CORP|CORPORATION|INC|INCORPORATED|LTD|LIMITED|LLC|PLC|GMBH|"
    r"SA|SAS|SRL|BV|NV|AG|PTE|PTY|HOLDINGS?|GROUP)\b\.?$"
)
_PUNCT_RE = re.compile(r"[^\w\u4e00-\u9fff]+", re.UNICODE)


def norm(s: str) -> str:
    """归一化到可比较的键。"""
    if not s:
        return ""
    s = unicodedata.normalize("NFKD", str(s))
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    s = unicodedata.normalize("NFKC", s).upper()
    s = _PUNCT_RE.sub(" ", s)
    s = " ".join(s.split())
    # 法人后缀可能叠加（"XX CO LTD"），最多剥两层
    for _ in range(2):
        new = _SUFFIX_RE.sub("", s).strip()
        if new == s or not new:
            break
        s = new
    return s


def bigrams(s: str):
    """二元组集合；单字符返回空集，避免短词靠单字幸免。"""
    return {s[i:i + 2] for i in range(len(s) - 1)} if len(s) > 1 else set()
