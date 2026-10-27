"""三向分流领域服务：名单 > 身份不明 > 命中-排除留痕 > 灰区 > AI拦截 > 放行。"""


def _sanction_reason(h):
    """按命中的名单来源给处置口径：联合国=法定冻结；OFAC=审查+清算行确认。"""
    p = h.get("params_found") or {}
    src = p.get("list", "")
    entry = " ".join(x for x in (p.get("entry_id", ""), p.get("matched", "")) if x)
    if "联合国" in src:
        return ("名单拦截 · 定向金融制裁",
                f"命中{src}（{entry}）：立即冻结并停止金融服务，无金额门槛、不得事先通知，"
                "24 小时内人工复核（不经 AI 诊断）")
    return ("名单拦截 · 单边制裁",
            f"命中{src}（{entry}）：属单边制裁，中国法下不当然产生冻结义务；"
            "加强审查、拒绝办理并与清算行/合规确认后留痕")


def triage(rule_hits, ai_result, case):
    # 1. 名单命中 → 直接拦截（不经 AI）
    for h in rule_hits:
        if h["rule_id"] == "R005":
            path, reason = _sanction_reason(h)
            return {"decision": "拦截", "path": path, "reason": reason}

    # 1.5 客户身份不明/证件缺失 → 拒办拒交易（CDD 条线，不是名单命中）
    for h in rule_hits:
        if h["rule_id"] == "R017":
            return {"decision": "拦截", "path": "身份不明拒办",
                    "reason": "客户身份不明/证件缺失：不得为其提供服务或与其交易"
                              "（反洗钱法第28条、11号令第8条）；按 11 号令第四十一条（一）报送"}

    ai_conclusion = ai_result.get("conclusion", "人工复核")

    # 2. 规则命中但 AI 排除 → 人工确认排除理由，保留命中-排除留痕
    if rule_hits and ai_conclusion == "放行":
        return {"decision": "人工复核", "path": "命中-排除留痕",
                "reason": "规则命中但 AI 依据材料排除，转人工复核确认排除理由（全程留痕）"}

    # 3. 灰区案例或 AI 输出需人工核验 → 人工复核
    if case["category"] == "grey" or ai_conclusion == "人工复核":
        return {"decision": "人工复核", "path": "灰区分流",
                "reason": "存在疑点但证据不足，或AI输出需人工核验，转人工复核队列",
                "grey_zone": case["grey_zone"]}

    # 4. AI 确认拦截
    if ai_conclusion == "拦截":
        return {"decision": "拦截", "path": "规则+AI双重确认",
                "reason": f"规则命中 {len(rule_hits)} 条，AI 研判确认可疑（{ai_result.get('official_type_name', '')}）"}

    # 5. 放行
    return {"decision": "放行", "path": "无命中+AI排除", "reason": "未命中监测规则，AI 排除可疑"}
