"""填充规则表 R001-R016（定义来自 PRD 4.1），legal_clause_ids 动态查询 clauses 表"""
import sqlite3, os, json

DB_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "qingyuan.db")

def cid(conn, reg_code, clause_no):
    row = conn.execute(
        "SELECT c.id FROM clauses c JOIN regulations r ON r.id=c.regulation_id WHERE r.reg_code=? AND c.clause_no=?",
        (reg_code, clause_no)).fetchone()
    return row[0] if row else None

RULES = [
    # (id, name, category, [(reg_code, clause_no)...], legal_desc, official_type_no/name, crime_code/name, params, penalty_ref)
    ("R001", "大额现金交易监测", "base",
     [("PBOC_3_2016", "第五条")],
     "3号令第五条：当日单笔或累计人民币5万元以上现金缴存/支取",
     "", "", "", "",
     {"cash_threshold": 50000},
     "未按规定报送大额交易报告"),
    ("R002", "分拆交易规避大额申报", "base",
     [("PBOC_3_2016", "第五条"), ("PBOC_3_2016", "第十一条")],
     "3号令第五条大额标准+第十一条合理怀疑：规避大额申报的分拆行为；识别点见官方对照表类型1-1『规避』",
     "官方第1-1类", "疑似非法汇兑型地下钱庄", "0801",
     "涉嫌掩饰、隐瞒犯罪所得及其收益",
     {"window_days": 7, "min_count": 8, "ratio_min": 0.85, "ratio_max": 0.99,
      "dispersion_max": 1.5, "span_window_multiple": 2,
      "cash_threshold": 50000, "transfer_threshold": 500000},
     "未按规定报送可疑交易报告"),
    ("R003", "资金快进快出", "base",
     [("PBOC_3_2016", "第十一条")],
     "3号令第十一条：资金流转异常情形",
     "官方第1-2类关联", "资金快进快出（过账通道特征）", "0802",
     "涉嫌其他上游犯罪的掩饰、隐瞒行为",
     {"out_within_days": 1, "out_ratio": 0.8, "min_counterparties": 3, "balance_ratio_max": 0.2},
     "未按规定报送可疑交易报告"),
    ("R004", "夜间高频交易", "base",
     [("PBOC_3_2016", "第十一条")],
     "3号令第十一条：交易时间异常情形",
     "", "", "1302", "交易时间异常",
     {"night_start": "22:00", "night_end": "06:00", "night_ratio": 0.7, "min_days": 3, "min_count_per_day": 3},
     "未按规定报送可疑交易报告"),
    ("R005", "制裁/涉恐名单拦截", "base",
     [("AML_LAW_2025", "第四十条"), ("AML_LAW_2025", "第四十一条"),
      ("PBOC_AML_SP_2026_1", "第三条"), ("PBOC_AML_SP_2026_1", "第七条")],
     "《反洗钱法》第四十条/第四十一条：名单核查与特别预防措施 + 特别预防措施办法：立即停止服务/冻结",
     "", "制裁/涉恐名单匹配（行内归纳）", "", "",
     {},
     "未按规定履行反洗钱特别预防措施义务"),
    ("R006", "新开户短期大额跨境", "base",
     [("PBOC_3_2016", "第五条")],
     "3号令第五条跨境划转标准 + 11号令新户尽调（行内归纳维度，非官方对照表类型）",
     "", "新开户短期大额跨境（行内归纳）", "0610", "跨境款项划转异常",
     {"account_age_days": 90, "cross_border_natural": 200000, "cross_border_corp": 2000000,
      "early_warning_ratio": 0.8},
     "未按规定报送可疑交易报告"),
    ("R007", "公私账户高频互转（空壳特征）", "base",
     [("PBOC_3_2016", "第十一条")],
     "3号令第十一条：交易背景存疑情形；对公账户向个人账户高频转出（空壳特征；行内归纳维度，非官方对照表类型）",
     "", "公转私空壳特征（行内归纳）", "0802", "涉嫌其他上游犯罪的掩饰、隐瞒行为",
     {"monthly_transfers": 10},
     "未按规定报送可疑交易报告"),
    ("R008", "涉虚拟货币交易特征", "base",
     [("PBOC_3_2016", "第十一条")],
     "3号令第十一条：交易性质异常情形（涉虚拟货币风险提示；行内归纳维度，非官方对照表类型）",
     "", "涉虚拟货币交易特征（行内归纳）", "1201", "交易性质异常",
     {"keywords": ["USDT", "OTC", "虚拟货币", "比特币"], "amount_multiple": 1000,
      "amount_min": 5000, "amount_max": 50000, "min_count": 5},
     "未按规定报送可疑交易报告"),
    # 类型化扩展 R009-R016（对齐官方12类）
    ("R009", "收款账户三段式分工", "typed",
     [("PBOC_TYPE_TABLE", "类型6 疑似集资")],
     "官方对照表第6类集资：收款段分散转入集中转出+中转快进快出+返款集中转入分散转出",
     "官方第6类", "疑似集资", "0606", "非法吸收公众存款",
     {"collect_min_count": 5,
      "min_in_counterparties": 3, "amount_spread_max": 3, "concentrated_ratio": 0.5,
      "min_out_counterparties": 3, "min_out_count": 3},
     "未按规定报送可疑交易报告"),
    ("R010", "套现商户异常", "typed",
     [("PBOC_TYPE_TABLE", "类型8 疑似套现")],
     "官方对照表第8类套现：POS累计额超经营规模+多卡规律刷卡+入账即转控制人",
     "官方第8类", "疑似套现", "1102", "非法经营（POS机套现）",
     {"pos_ratio": 5, "min_cards": 10, "to_owner_hours": 2},
     "未按规定报送可疑交易报告"),
    ("R011", "传销资金网络", "typed",
     [("PBOC_TYPE_TABLE", "类型7 疑似传销")],
     "官方对照表第7类传销：金字塔结构+返利时点集中+返利比例固定",
     "官方第7类", "疑似传销", "1101", "组织、领导传销活动",
     {"min_layers": 3, "layer_growth": 3, "rebate_time_concentration": 0.8},
     "未按规定报送可疑交易报告"),
    ("R012", "开户试卡特征", "typed",
     [("PBOC_TYPE_TABLE", "类型5 疑似诈骗")],
     "官方对照表第5类诈骗：开户小额试卡+自助设备全额取现+沉睡后激活",
     "官方第5类", "疑似诈骗", "1201", "诈骗（电信诈骗）",
     {"first_amounts": [100, 200, 500, 1000], "withdraw_hours": 24, "dormant_days": 30},
     "未按规定报送可疑交易报告"),
    ("R013", "涉税资金回流", "typed",
     [("PBOC_TYPE_TABLE", "类型9 疑似涉税犯罪")],
     "官方对照表第9类涉税：对公频繁转个人+批量存单+进出金额基本一致",
     "官方第9类", "疑似涉税犯罪", "1001", "逃税、避税、骗税",
     {"corp_to_person_ratio": 0.6, "transit_diff_tolerance": 0.05, "min_transit_count": 3},
     "未按规定报送可疑交易报告"),
    ("R014", "特定身份规模不符", "typed",
     [("PBOC_TYPE_TABLE", "类型2 疑似腐败")],
     "官方对照表第2类腐败：交易规模与身份收入明显不符+亲属名义集中操作+节日前后集中",
     "官方第2类", "疑似腐败", "0502", "与公职人员身份不符的可疑交易",
     {"income_multiple": 10, "relative_accounts": 3},
     "未按规定报送可疑交易报告"),
    ("R015", "涉毒资金特征", "typed",
     [("PBOC_TYPE_TABLE", "类型3 疑似毒品犯罪")],
     "官方对照表第3类毒品：ATM无卡存款为主+多点流入一次性提现+金额呈零包价格整数倍",
     "官方第3类", "疑似毒品犯罪", "0101", "毒品犯罪",
     {"atm_ratio": 0.8, "withdraw_hours": 48, "amount_multiples": [500, 1000]},
     "未按规定报送可疑交易报告"),
    ("R016", "验资账户速转", "typed",
     [("PBOC_TYPE_TABLE", "类型12 疑似虚假出资、抽逃出资")],
     "官方对照表第12类：验资账户集中开立+验资后基本户资金速转同名他行",
     "官方第12类", "疑似虚假出资、抽逃出资", "0902", "虚假出资、抽逃出资",
     {"min_accounts": 3, "account_window_days": 30, "transfer_out_ratio": 0.9, "transfer_days": 1},
     "未按规定报送可疑交易报告"),
    # CDD 条线：客户身份不明/证件缺失（非交易型可疑行为，走覆盖矩阵"无法归类"出口）
    ("R017", "客户身份不明/证件缺失（CDD 条线）", "cdd",
     [("AML_LAW_2025", "第二十八条"), ("PBOC_CDD_2025_11", "第八条"),
      ("PBOC_CDD_2025_11", "第四十一条")],
     "《反洗钱法》第二十八条 + 11号令第八条：不得为身份不明的客户提供服务或与其交易；"
     "11号令第四十一条（一）：客户拒绝提供有效身份证件的应向反洗钱监测分析中心报告",
     "", "客户身份不明/证件缺失（CDD 条线 · 非交易型）", "", "",
     {},
     "为身份不明的客户提供服务或者与其进行交易"),
]

if __name__ == "__main__":
    conn = sqlite3.connect(DB_PATH)
    for rid, name, cat, clauses, desc, ot_no, ot_name, cc, cn, params, penalty in RULES:
        ids = [cid(conn, rc, cn2) for rc, cn2 in clauses]
        ids = [i for i in ids if i]
        conn.execute(
            "INSERT OR REPLACE INTO rules(rule_id,name,category,legal_clause_ids,legal_desc,"
            "official_type_no,official_type_name,crime_code,crime_name,params,penalty_ref)"
            " VALUES(?,?,?,?,?,?,?,?,?,?,?)",
            (rid, name, cat, json.dumps(ids, ensure_ascii=False), desc,
             ot_no, ot_name, cc, cn, json.dumps(params, ensure_ascii=False), penalty))
    conn.commit()
    n = conn.execute("SELECT COUNT(*) FROM rules").fetchone()[0]
    miss = conn.execute("SELECT rule_id FROM rules WHERE legal_clause_ids='[]'").fetchall()
    print(f"规则入库 {n} 条；缺失法规关联的规则: {[m[0] for m in miss] if miss else '无'}")
    conn.close()
