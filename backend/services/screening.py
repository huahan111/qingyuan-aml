"""名单筛查服务：当前使用模拟名单库，命中不经 AI，先限制后核验。

匹配规则：仅支持"名单项包含在查询串中"或"查询串（≥2 字符）包含在名单项中"。
单字符查询一律拒绝——历史上 1 个字符就能命中「恐怖组织A」（任何字符串都包含单字符），
属于匹配过宽，不是业务命中。
"""
from domain.rules.sanctions import MOCK_SANCTION_LIST

MIN_QUERY_LEN = 2


def screen(q: str):
    q = (q or "").strip()
    if not q:
        raise ValueError("请输入筛查对象")
    if len(q) < MIN_QUERY_LEN:
        raise ValueError(f"筛查对象至少 {MIN_QUERY_LEN} 个字符")
    matches = []
    for s in MOCK_SANCTION_LIST:
        if s in q or q in s:
            matches.append({"name": s, "list": "境内法定名单（模拟）", "match_type": "名称包含"})
    return {
        "query": q,
        "hit": bool(matches),
        "matches": matches,
        "list_size": len(MOCK_SANCTION_LIST),
        "action": "命中即冻结账户，24 小时内人工复核，不经 AI 诊断" if matches else "未命中，筛查过程已留痕",
    }
