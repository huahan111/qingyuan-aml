"""构建 12 条 MVP 演示案例，输出为独立 JSON 数据集（不写入 SQLite）。
放行/拦截/灰区三类，溯源链关联法规库真实条款。
"""
import sqlite3, os, json

DB_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "qingyuan.db")
DEMO_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "demo_cases.json")

def get_clause_quote(conn, reg_code, clause_no):
    r = conn.execute(
        "SELECT c.content FROM clauses c JOIN regulations r ON r.id=c.regulation_id WHERE r.reg_code=? AND c.clause_no=?",
        (reg_code, clause_no)).fetchone()
    return r[0] if r else ""

def make_trace(rule_id, trigger_desc, legal_refs, official_type_no, official_type_name, type_clause_no, penalty):
    """legal_refs: [(reg_code, clause_no, note)] —— note 是该条款在本案中的适用说明，
    不是逐字原文；条文原文以 clauses 表的 content 为准（前端展示的也是 content）。"""
    return {
        "rule_id": rule_id, "trigger_desc": trigger_desc,
        "legal_clauses": [{"reg_code": rc, "clause_no": cn, "note": n} for rc, cn, n in legal_refs],
        "official_type_no": official_type_no,
        "official_type_name": official_type_name,
        "type_clause_no": type_clause_no,
        "penalty_ref": penalty
    }

CASES = []

# ============================================================
# PASS 放行 3 条
# ============================================================
CASES.append({
    "case_id": "PASS-01", "title": "医药销售岗工资代发", "category": "pass",
    "customer_info": {
        "name": "刘某某（个人）", "age": 41, "occupation": "医药企业销售岗", "employer": "XX医药公司",
        "income": "月薪15,000元+绩效提成", "open_date": "2020-03", "risk_level": "低",
        "tags": ["在职6年", "固定工资客群", "工资代发"]
    },
    "transactions": [
        {"date":"2026-09-05","time":"14:30","type":"转账收入","amount":32000,"counterparty":"XX医药公司","channel":"代发","summary":"工资+绩效"},
        {"date":"2026-09-05","time":"15:00","type":"转账支出","amount":12500,"counterparty":"XX银行房贷","channel":"网银","summary":"月供"},
        {"date":"2026-09-12","time":"10:20","type":"转账支出","amount":5800,"counterparty":"XX信用卡中心","channel":"网银","summary":"信用卡还款"},
    ],
    "expected_conclusion": "放行",
    "rules_hit": [],
    "official_type_no": "", "official_type_name": "",
    "trace_chain": [
        make_trace("", "未命中任何监测规则",
            [("PBOC_3_2016", "第十二条", "金融机构应当制定本机构的交易监测标准，并对其有效性负责。"),
             ("PBOC_2_2006", "第二十条", "'正常'指交易行为符合客户的身份、职业、收入状况和交易背景。"),
             ("PBOC_TYPE_TABLE", "类型6 疑似集资", "正常工资代发有劳动合同、工资表、绩效制度等凭证支撑。")],
            "", "", "", ""),
    ],
    "grey_zone": {}
})

CASES.append({
    "case_id": "PASS-02", "title": "退休人员养老金取现", "category": "pass",
    "customer_info": {
        "name": "张某（个人）", "age": 68, "occupation": "退休教师", "employer": "市教委",
        "income": "养老金4,200元/月", "open_date": "2018-01", "risk_level": "低",
        "tags": ["退休", "固定金额", "同模式持续26个月"]
    },
    "transactions": [
        {"date":"2026-10-03","time":"09:00","type":"养老金入账","amount":4200,"counterparty":"社保基金","channel":"代发","summary":"月养老金"},
        {"date":"2026-10-03","time":"09:30","type":"取现","amount":4200,"counterparty":"本人","channel":"ATM","summary":"取现"},
    ],
    "expected_conclusion": "放行",
    "rules_hit": [],
    "official_type_no": "", "official_type_name": "",
    "trace_chain": [
        make_trace("", "养老金全额取现属规律性生活行为",
            [("PBOC_2_2006", "第二十条", "长期指1年以上；持续26个月稳定模式，与老年客户收支习惯一致。"),
             ("PBOC_3_2016", "第十二条", "机构应参考客户历史基线评估交易异常程度。")],
            "", "", "", ""),
    ],
    "grey_zone": {}
})

CASES.append({
    "case_id": "PASS-03", "title": "新设公司正常货款支付", "category": "pass",
    "customer_info": {
        "name": "XX商贸有限公司（对公）", "age": None, "occupation": "批发零售", "employer": "—",
        "income": "注册资本500万", "open_date": "2026-05", "risk_level": "低",
        "tags": ["新设公司", "验资后有真实经营", "合同发票齐备"]
    },
    "transactions": [
        {"date":"2026-06-15","time":"09:00","type":"验资转入","amount":5000000,"counterparty":"验资户","channel":"柜面","summary":"验资款转入基本户"},
        {"date":"2026-07-02","time":"10:00","type":"对公转账","amount":3800000,"counterparty":"XX建材供应商","channel":"网银","summary":"支付货款（合同编号C20260701）"},
        {"date":"2026-08-10","time":"14:30","type":"代发工资","amount":600000,"counterparty":"员工工资户","channel":"网银","summary":"发放工资"},
        {"date":"2026-09-01","time":"11:00","type":"增值税缴纳","amount":45000,"counterparty":"税务局","channel":"网银","summary":"增值税申报"},
    ],
    "expected_conclusion": "放行",
    "rules_hit": [],
    "official_type_no": "", "official_type_name": "",
    "trace_chain": [
        make_trace("", "新设公司验资后3个月内发生正常经营支付",
            [("PBOC_CDD_2025_11", "第十条", "建立业务关系后，客户正常经营流水有合同、发票、社保等凭证支撑。"),
             ("PBOC_TYPE_TABLE", "类型12 疑似虚假出资、抽逃出资", "验资资金用于支付货款和发放工资，非'验资后立即全额转划同名他行'。")],
            "", "", "", ""),
    ],
    "grey_zone": {}
})

# ============================================================
# BLOCK 拦截 4 条
# ============================================================
CASES.append({
    "case_id": "BLOCK-01", "title": "大额转入分批转出（贴线分拆）", "category": "intercept",
    "customer_info": {
        "name": "李某某（个人）", "age": 34, "occupation": "个体工商户（建材零售）",
        "employer": "自营", "income": "月均流水约8.6万元", "open_date": "2019-03", "risk_level": "中",
        "tags": ["个体工商户", "行为突变", "2年内无预警"]
    },
    "transactions": [
        {"date":"2026-10-08","time":"09:42","type":"现金存入","amount":49100,"counterparty":"本人","channel":"柜面","summary":""},
        {"date":"2026-10-09","time":"10:15","type":"现金存入","amount":49200,"counterparty":"本人","channel":"柜面","summary":""},
        {"date":"2026-10-10","time":"14:03","type":"现金存入","amount":49400,"counterparty":"本人","channel":"柜面","summary":""},
        {"date":"2026-10-11","time":"09:31","type":"现金存入","amount":49050,"counterparty":"本人","channel":"柜面","summary":""},
        {"date":"2026-10-13","time":"09:20","type":"现金存入","amount":49350,"counterparty":"本人","channel":"柜面","summary":""},
        {"date":"2026-10-14","time":"11:05","type":"现金存入","amount":49250,"counterparty":"本人","channel":"柜面","summary":""},
        {"date":"2026-10-15","time":"15:47","type":"现金存入","amount":49150,"counterparty":"本人","channel":"柜面","summary":""},
        {"date":"2026-10-16","time":"16:20","type":"现金存入","amount":49500,"counterparty":"本人","channel":"柜面","summary":""},
        {"date":"2026-10-17","time":"10:00","type":"转账转出","amount":394000,"counterparty":"XX贸易有限公司","channel":"网银","summary":"货款"},
    ],
    "expected_conclusion": "拦截",
    "rules_hit": ["R002"],
    # 官方对照表（银行业参考版）共 12 类、13 个编号条目（1-1、1-2、2~12），没有"类型13"。
    # 本案例的贴线分拆特征对应类型1-1 的『规避』识别点（频繁出现低于报告标准的特殊金额）。
    "official_type_no": "官方第1-1类", "official_type_name": "疑似非法汇兑型地下钱庄",
    "trace_chain": [
        make_trace("R002", "7个工作日8笔现金存入，单笔49,050–49,500元（现金大额标准5万的98.1%–99%），8 笔金额高度趋同（最高 49,500 / 最低 49,050，波动不足 1%），随后一次性转出 39.4 万",
            [("PBOC_3_2016", "第五条", "当日单笔或者累计交易人民币5万元以上的现金缴存…应当报告。"),
             ("PBOC_3_2016", "第十一条", "金融机构发现或者有合理理由怀疑客户…应当提交可疑交易报告。"),
             ("PBOC_TYPE_TABLE", "类型1-1 疑似非法汇兑型地下钱庄", "规避：交易金额或形式规避反洗钱监测或其他措施（如频繁出现低于报告标准的特殊金额）。")],
            "官方第1-1类", "疑似非法汇兑型地下钱庄", "类型1-1 疑似非法汇兑型地下钱庄",
            "未按规定报送大额交易报告或者可疑交易报告"),
    ],
    "grey_zone": {}
})

CASES.append({
    "case_id": "BLOCK-02", "title": "小额分散归集后统一转出（集资特征）", "category": "intercept",
    "customer_info": {
        "name": "王某某（个人）", "age": 38, "occupation": "无固定职业", "employer": "—",
        "income": "自述经营电商", "open_date": "2023-01", "risk_level": "高",
        "tags": ["无固定职业", "大量个人账户", "资金归集", "凌晨操作"]
    },
    "transactions": [
        {"date":"2026-10-01","time":"20:00","type":"转账收入","amount":2980,"counterparty":"张X","channel":"网银","summary":""},
        {"date":"2026-10-01","time":"20:05","type":"转账收入","amount":2980,"counterparty":"李X","channel":"网银","summary":""},
        {"date":"2026-10-02","time":"21:00","type":"转账收入","amount":2980,"counterparty":"王X","channel":"网银","summary":""},
        {"date":"2026-10-03","time":"20:30","type":"转账收入","amount":2980,"counterparty":"赵X","channel":"网银","summary":""},
        {"date":"2026-10-04","time":"01:00","type":"转账收入","amount":2980,"counterparty":"陈X","channel":"网银","summary":""},
        {"date":"2026-10-04","time":"01:05","type":"转账收入","amount":2980,"counterparty":"钱X","channel":"网银","summary":""},
        {"date":"2026-10-05","time":"01:30","type":"转账收入","amount":2980,"counterparty":"孙X","channel":"网银","summary":""},
        {"date":"2026-10-05","time":"01:35","type":"转账收入","amount":2980,"counterparty":"周X","channel":"网银","summary":""},
        {"date":"2026-10-06","time":"02:00","type":"转账转出","amount":23840,"counterparty":"XX理财公司","channel":"网银","summary":""},
        {"date":"2026-10-12","time":"20:00","type":"转账转出","amount":238.4,"counterparty":"张X","channel":"网银","summary":"返款"},
        {"date":"2026-10-12","time":"20:01","type":"转账转出","amount":238.4,"counterparty":"李X","channel":"网银","summary":"返款"},
        {"date":"2026-10-12","time":"20:02","type":"转账转出","amount":238.4,"counterparty":"王X","channel":"网银","summary":"返款"},
        {"date":"2026-10-12","time":"20:03","type":"转账转出","amount":238.4,"counterparty":"赵X","channel":"网银","summary":"返款"},
    ],
    "expected_conclusion": "拦截",
    "rules_hit": ["R009"],
    "official_type_no": "官方第6类", "official_type_name": "疑似集资",
    "trace_chain": [
        make_trace("R009", "三段式资金结构：8个不同个人各转入2,980元（基数倍数关系）→集中转出23,840元至理财公司→6日后按8%固定比例向原转入人分散返款",
            [("PBOC_TYPE_TABLE", "类型6 疑似集资", "收款账户'分散转入、集中转出'；中转账户'快进快出、频繁收付'；返款账户'集中转入、分散转出'。"),
             ("PBOC_TYPE_TABLE", "类型6 疑似集资", "单笔金额呈规律性，转账一般以某金额为基数，呈倍数关系；返利资金也呈对应的倍数关系。"),
             ("PBOC_3_2016", "第十一条", "金融机构发现或者有合理理由怀疑客户交易与洗钱犯罪相关，应当提交可疑交易报告。")],
            "官方第6类", "疑似集资", "类型6 疑似集资",
            "未按规定报送可疑交易报告"),
    ],
    "grey_zone": {}
})

CASES.append({
    "case_id": "BLOCK-03", "title": "快进快出资金过账", "category": "intercept",
    "customer_info": {
        "name": "王某（个人）", "age": 28, "occupation": "公司职员", "employer": "XX科技",
        "income": "月薪12,000元", "open_date": "2017-08", "risk_level": "中",
        "tags": ["普通职员", "收入与交易规模严重不符", "累犯型账户"]
    },
    "transactions": [
        {"date":"2026-10-06","time":"10:21","type":"转账收入","amount":950000,"counterparty":"赵X","channel":"网银","summary":"个人转入"},
        {"date":"2026-10-06","time":"10:22","type":"转账收入","amount":850000,"counterparty":"钱X","channel":"网银","summary":"个人转入"},
        {"date":"2026-10-06","time":"10:23","type":"转账收入","amount":1000000,"counterparty":"孙X","channel":"网银","summary":"个人转入"},
        {"date":"2026-10-06","time":"10:24","type":"转账收入","amount":1000000,"counterparty":"李X","channel":"网银","summary":"个人转入"},
        {"date":"2026-10-06","time":"11:02","type":"转账转出","amount":780000,"counterparty":"A公司","channel":"网银","summary":""},
        {"date":"2026-10-06","time":"11:30","type":"转账转出","amount":760000,"counterparty":"B公司","channel":"网银","summary":""},
        {"date":"2026-10-06","time":"12:10","type":"转账转出","amount":800000,"counterparty":"C公司","channel":"网银","summary":""},
        {"date":"2026-10-06","time":"13:00","type":"转账转出","amount":820000,"counterparty":"D公司","channel":"网银","summary":""},
        {"date":"2026-10-06","time":"14:05","type":"转账转出","amount":10000,"counterparty":"E公司","channel":"网银","summary":""},
    ],
    "expected_conclusion": "拦截",
    "rules_hit": ["R003"],
    "official_type_no": "官方第1-2类关联", "official_type_name": "资金快进快出（过账通道特征）",
    "trace_chain": [
        make_trace("R003", "当日收到4个个人账户转入合计380万，4小时内分5笔转出至5个不同公司，转出 317 万（占 83%），余额余 63 万；转入转出对手方无一重复",
            [("PBOC_3_2016", "第十一条", "金融机构发现或者有合理理由怀疑客户交易与洗钱、恐怖融资等犯罪活动相关…"),
             ("PBOC_TYPE_TABLE", "类型1-2 疑似非法结算型地下钱庄", "公司账户突然大进大出，每天不留余额；资金快进快出，过渡性质明显。"),
             ("PBOC_2_2006", "第二十条", "'频繁'指交易行为营业日每天发生3次以上或者营业日每天持续3天以上。")],
            "官方第1-2类关联", "资金快进快出（过账通道特征）", "类型1-2 疑似非法结算型地下钱庄",
            "未按规定报送可疑交易报告"),
    ],
    "grey_zone": {}
})

CASES.append({
    "case_id": "BLOCK-04", "title": "夜间高频集中入账（赌博特征）", "category": "intercept",
    "customer_info": {
        "name": "陈某（个人）", "age": 25, "occupation": "自由职业", "employer": "—",
        "income": "自述自媒体收入", "open_date": "2024-03", "risk_level": "高",
        "tags": ["无固定收入", "账户更换频繁"]
    },
    # 金额尾数统一为 .99：这是对照表类型11 的识别点（"金额尾数带某个特定数字，如.99"）。
    # 附言字段只放客户/渠道真实填写的附言，本例 11 笔均无附言（分析结论写在触发说明里，不写进附言）。
    "transactions": [
        {"date":"2026-10-05","time":"22:30","type":"转账收入","amount":500.99,"counterparty":"周X","channel":"网银","summary":""},
        {"date":"2026-10-05","time":"22:45","type":"转账收入","amount":1000.99,"counterparty":"吴X","channel":"网银","summary":""},
        {"date":"2026-10-05","time":"23:00","type":"转账收入","amount":1500.99,"counterparty":"郑X","channel":"网银","summary":""},
        {"date":"2026-10-05","time":"23:30","type":"转账收入","amount":2000.99,"counterparty":"何X","channel":"网银","summary":""},
        {"date":"2026-10-06","time":"22:10","type":"转账收入","amount":1000.99,"counterparty":"林X","channel":"网银","summary":""},
        {"date":"2026-10-06","time":"22:40","type":"转账收入","amount":500.99,"counterparty":"高X","channel":"网银","summary":""},
        {"date":"2026-10-06","time":"23:20","type":"转账收入","amount":1500.99,"counterparty":"罗X","channel":"网银","summary":""},
        {"date":"2026-10-06","time":"23:55","type":"转账收入","amount":500.99,"counterparty":"宋X","channel":"网银","summary":""},
        {"date":"2026-10-07","time":"22:05","type":"转账收入","amount":1000.99,"counterparty":"唐X","channel":"网银","summary":""},
        {"date":"2026-10-07","time":"22:50","type":"转账收入","amount":2000.99,"counterparty":"许X","channel":"网银","summary":""},
        {"date":"2026-10-07","time":"23:40","type":"转账收入","amount":500.99,"counterparty":"韩X","channel":"网银","summary":""},
    ],
    "expected_conclusion": "拦截",
    "rules_hit": ["R004"],
    "official_type_no": "官方第11类", "official_type_name": "疑似赌博",
    "trace_chain": [
        make_trace("R004", "连续3天夜间22:00后高频入账（10-05四笔/10-06四笔/10-07三笔，夜间占比100%），11笔金额均为500–2000元档且尾数统一为 .99，对手方为11个不同个人",
            [("PBOC_3_2016", "第十一条", "交易时间、频率异常，有合理理由怀疑与赌博等犯罪活动相关。"),
             ("PBOC_2_2006", "第二十条", "'频繁'指交易行为营业日每天发生3次以上或者营业日每天持续3天以上。"),
             ("PBOC_TYPE_TABLE", "类型11 疑似赌博", "交易金额一般不大，频繁出现100元及其整数倍，或金额尾数带某个特定数字（如.99）；账户分散使用，更换比较频繁，一般3个月左右更换。")],
            "官方第11类", "疑似赌博", "类型11 疑似赌博",
            "未按规定报送可疑交易报告"),
    ],
    "grey_zone": {}
})

# ============================================================
# GREY 灰区人工复核 4 条
# ============================================================
CASES.append({
    "case_id": "GREY-01", "title": "留学学费跨境汇款", "category": "grey",
    "customer_info": {
        "name": "李某（个人）", "age": 46, "occupation": "教师", "employer": "市中学",
        "income": "月薪8,000元", "open_date": "2015-02", "risk_level": "低",
        "tags": ["教职工", "首次跨境大额", "用途明确"]
    },
    "transactions": [
        {"date":"2026-09-10","time":"10:00","type":"跨境汇款","amount":49000,"counterparty":"XX大学（境外）","channel":"柜面","summary":"学费"},
        {"date":"2026-10-05","time":"10:00","type":"跨境汇款","amount":49000,"counterparty":"XX大学（境外）","channel":"柜面","summary":"学费"},
        {"date":"2026-10-15","time":"10:00","type":"跨境汇款","amount":49000,"counterparty":"XX大学（境外）","channel":"柜面","summary":"住宿费"},
    ],
    "expected_conclusion": "人工复核",
    "rules_hit": [],
    "official_type_no": "", "official_type_name": "",
    "trace_chain": [
        make_trace("", "未直接命中基础规则；跨境大额+首次发生，需强化尽职调查核验材料",
            [("PBOC_3_2016", "第五条", "自然人客户跨境款项划转：人民币20万元以上（含20万元）或外币等值1万美元以上。"),
             ("PBOC_CDD_2025_11", "第十条", "高风险情形应采取强化尽职调查：了解跨境交易的合理目的、资金来源与用途。")],
            "", "", "",
            "未按规定履行客户身份识别义务"),
    ],
    "grey_zone": {
        "default_path": "人工复核",
        "pass_if": "提供学校录取通知书、学费/住宿费缴费通知单、学生与汇款人亲属关系证明，且收款账户为学校官方对公账户",
        "intercept_if": "无法提供录取/缴费材料，或收款账户为个人账户/非教育机构，或汇款用途与学费明显不符",
        "human_check_points": ["核对学校官方账户信息（SWIFT/账号）", "录取材料真伪", "汇款人与学生关系（出生医学证明或户口本）", "金额与学费通知单一致性"]
    }
})

CASES.append({
    "case_id": "GREY-02", "title": "跨境电商货款收汇", "category": "grey",
    "customer_info": {
        "name": "赵某（个人）", "age": 32, "occupation": "跨境电商卖家", "employer": "自营",
        "income": "月均收款约9万", "open_date": "2026-05-05", "risk_level": "中",
        "tags": ["新开户", "跨境收款", "71天"]
    },
    "transactions": [
        {"date":"2026-07-15","time":"14:00","type":"跨境收入","amount":40000,"counterparty":"Amazon结算","channel":"网银","summary":"平台结算单号AMZ-20260715001"},
        {"date":"2026-07-20","time":"10:00","type":"转账转出","amount":150000,"counterparty":"XX服装厂","channel":"网银","summary":"支付供应商货款（合同编号C20260710）"},
        {"date":"2026-08-05","time":"11:00","type":"转账转出","amount":80000,"counterparty":"XX物流公司","channel":"网银","summary":"物流费（发票编号F20260802）"},
    ],
    "expected_conclusion": "人工复核",
    "rules_hit": ["R006"],
    # 官方对照表 12 类中没有"新开户短期大额跨境"这一类（R006 为行内归纳维度）。
    # 本案例为灰区核验：依据 3 号令第五条（跨境标准）+ 11 号令第十条（强化尽调），
    # 不套用任何官方类型，由覆盖矩阵"无法归类"出口承接。
    "official_type_no": "", "official_type_name": "",
    "trace_chain": [
        make_trace("R006", "开户71天，3个月内跨境收款28万元；资金到账后用于支付境内供应商货款",
            [("PBOC_3_2016", "第五条", "自然人跨境款项划转≥20万人民币/等值1万美元…"),
             ("PBOC_CDD_2025_11", "第十条", "高风险客户强化尽职调查（EDD）：了解跨境交易的合理目的、资金来源与用途。")],
            "", "", "",
            "未按规定报送大额交易报告"),
    ],
    "grey_zone": {
        "default_path": "人工复核",
        "pass_if": "提供电商平台结算单、出口合同、增值税发票、境内供应商发票与合同，资金流与货物流一致",
        "intercept_if": "无法提供平台结算单或出口合同，或收款方与供应商不一致，或资金来源无法解释",
        "human_check_points": ["核对电商平台结算单真实性", "出口合同与报关单一致性", "供应商发票与合同对应关系", "资金流与货物流匹配性"]
    }
})

CASES.append({
    "case_id": "GREY-03", "title": "医药代表收境外佣金", "category": "grey",
    "customer_info": {
        "name": "孙某（个人）", "age": 35, "occupation": "医药代表", "employer": "XX医药代理",
        "income": "底薪6,000元+佣金", "open_date": "2019-01", "risk_level": "中",
        "tags": ["医药行业", "境外外汇", "佣金性质"]
    },
    "transactions": [
        {"date":"2026-09-01","time":"09:00","type":"外汇收入","amount":2000,"counterparty":"XX Pharma GmbH","channel":"网银","summary":"佣金（EUR等值）"},
        {"date":"2026-09-15","time":"10:00","type":"外汇收入","amount":3000,"counterparty":"XX Pharma GmbH","channel":"网银","summary":"咨询费（EUR等值）"},
        {"date":"2026-10-01","time":"09:30","type":"外汇收入","amount":2500,"counterparty":"XX Pharma GmbH","channel":"网银","summary":"推广费（EUR等值）"},
    ],
    "expected_conclusion": "人工复核",
    "rules_hit": [],
    "official_type_no": "", "official_type_name": "",
    "trace_chain": [
        make_trace("", "未直接命中规则，但医药行业+境外外汇佣金需核验业务真实性",
            [("PBOC_CDD_2025_11", "第十条", "当客户交易行为、资金来源或用途与客户身份、风险状况不符时，应进行强化尽职调查。"),
             ("PBOC_3_2016", "第十二条", "交易监测标准应参考客户的身份、行为，交易的资金来源、金额、频率、流向、性质等存在异常的情形。")],
            "", "", "", "未按规定履行客户身份识别义务"),
    ],
    "grey_zone": {
        "default_path": "人工复核",
        "pass_if": "提供境外药企服务合同/佣金协议、发票、完税证明，且收款对手方为正规药企官方账户",
        "intercept_if": "无法提供合同/发票，或收款方为个人账户/中间商，或金额与合同约定严重不符，或频率远超合理范围",
        "human_check_points": ["核对服务合同与发票真实性", "境外药企资质与付款授权", "完税情况", "佣金比例与行业惯例对比"]
    }
})

CASES.append({
    "case_id": "GREY-04", "title": "海外务工赡家款", "category": "grey",
    "customer_info": {
        "name": "周某（个人）", "age": 42, "occupation": "建筑工人（海外）", "employer": "XX建筑（中东）",
        "income": "月薪2,500美元", "open_date": "2015-06", "risk_level": "低",
        "tags": ["海外务工", "定期汇款", "赡家性质"]
    },
    "transactions": [
        {"date":"2026-09-05","time":"08:00","type":"跨境汇款","amount":12000,"counterparty":"妻子张某","channel":"网银","summary":"月度赡家款"},
        {"date":"2026-09-20","time":"08:00","type":"跨境汇款","amount":12000,"counterparty":"妻子张某","channel":"网银","summary":"月度赡家款"},
        {"date":"2026-10-05","time":"08:00","type":"跨境汇款","amount":12000,"counterparty":"妻子张某","channel":"网银","summary":"月度赡家款"},
    ],
    "expected_conclusion": "人工复核",
    "rules_hit": [],
    "official_type_no": "", "official_type_name": "",
    "trace_chain": [
        make_trace("", "定期跨境汇款赡家属合理情形，但需核验海外雇佣关系真实性",
            [("PBOC_3_2016", "第五条", "自然人跨境款项划转≥20万人民币需报告；单笔1.2万未达标准，但连续多笔累计需关注。"),
             ("PBOC_CDD_2025_11", "第十条", "强化尽职调查应覆盖客户收入来源的合理性。")],
            "", "", "", "未按规定履行客户身份识别义务"),
    ],
    "grey_zone": {
        "default_path": "人工复核",
        "pass_if": "提供海外劳务合同、工资单、工作单位在留证明，收款人为直系亲属且关系可证，汇款频率与合同周期一致",
        "intercept_if": "无法提供海外雇佣证明，或收款人非直系亲属，或汇款频率/金额远超合同薪酬，或资金来源无法解释",
        "human_check_points": ["核对海外劳务合同与工资单", "工作单位在留证明或签证", "收款人与汇款人亲属关系", "汇款周期与发薪周期一致性"]
    }
})

CASES.append({
    "case_id": "EXCLUDE-01", "title": "批发货款归集后支付供应商（规则命中但排除）", "category": "grey",
    "customer_info": {
        "name": "YY建材贸易有限公司（对公）", "age": None, "occupation": "建材批发", "employer": "—",
        "income": "年营业额约1200万元", "open_date": "2016-05", "risk_level": "低",
        "tags": ["经营10年", "固定上下游", "合同发票齐备"]
    },
    "transactions": [
        {"date":"2026-10-08","time":"09:10","type":"转账收入","amount":120000,"counterparty":"A建材客户","channel":"网银","summary":"货款"},
        {"date":"2026-10-08","time":"10:20","type":"转账收入","amount":90000,"counterparty":"B装饰公司","channel":"网银","summary":"货款"},
        {"date":"2026-10-08","time":"11:05","type":"转账收入","amount":60000,"counterparty":"C工程队","channel":"手机银行","summary":"货款"},
        {"date":"2026-10-08","time":"14:00","type":"转账支出","amount":100000,"counterparty":"W水泥厂","channel":"网银","summary":"采购货款"},
        {"date":"2026-10-08","time":"15:10","type":"转账支出","amount":85000,"counterparty":"X钢材供应商","channel":"网银","summary":"采购货款"},
        {"date":"2026-10-09","time":"09:30","type":"转账支出","amount":78000,"counterparty":"Y物流公司","channel":"网银","summary":"运费"},
    ],
    "expected_conclusion": "放行",
    "rules_hit": ["R003"],
    "official_type_no": "官方第1-2类关联", "official_type_name": "资金快进快出（过账通道特征）",
    "trace_chain": [
        make_trace("R003", "当日3个长期客户转入货款27万，当日至次日向3家固定供应商支付26.3万（97%）；交易附言、对手方与经营背景可解释，属批发行业正常结算",
            [("PBOC_3_2016", "第十一条", "金融机构发现或者有合理理由怀疑客户交易与洗钱、恐怖融资等犯罪活动相关…"),
             ("PBOC_TYPE_TABLE", "类型1-2 疑似非法结算型地下钱庄", "公司账户突然大进大出，每天不留余额；资金快进快出，过渡性质明显。"),
             ("PBOC_2_2006", "第二十条", "'频繁'指交易行为营业日每天发生3次以上或者营业日每天持续3天以上。")],
            "官方第1-2类关联", "资金快进快出（过账通道特征）", "类型1-2 疑似非法结算型地下钱庄", "未按规定报送可疑交易报告"),
    ],
    "grey_zone": {
        "default_path": "人工复核",
        "pass_if": "提供采购合同、发票、固定供应商与客户记录，且流水规模与经营规模匹配",
        "intercept_if": "无真实贸易背景、资金来源不明、向个人账户回流或出现夜间高频",
        "human_check_points": ["采购合同与增值税发票", "上下游长期合作记录", "经营规模与流水匹配度", "是否存在个人账户回流"]
    }
})

# ============================================================
# 补充案例：为 R001 / R005 / R007 / R008 / R017 各补一条可演示样本
# （此前这 5 条规则只有审计夹具、无演示案例，规则有效性页显示"—"）
# ============================================================
CASES.append({
    "case_id": "GREY-05", "title": "单日大额现金存入待核验（大额应报，可疑待定）", "category": "grey",
    "customer_info": {
        "name": "孙某某（个人）", "age": 45, "occupation": "个体工商户（建材零售）", "employer": "自营",
        "income": "月均流水约6万元", "open_date": "2018-05", "risk_level": "中",
        "tags": ["个体工商户", "单笔大额现金", "无分拆特征"]
    },
    "transactions": [
        {"date":"2026-10-12","time":"10:20","type":"现金存入","amount":62000,"counterparty":"本人","channel":"柜面","summary":"货款回笼"},
    ],
    "expected_conclusion": "人工复核",
    "rules_hit": ["R001"],
    "official_type_no": "", "official_type_name": "",
    "trace_chain": [
        make_trace("R001", "单日现金存入 6.2 万元，达 3 号令 5 万元大额现金标准；单笔发生、无多笔贴线分拆特征，可疑性取决于资金来源",
            [("PBOC_3_2016", "第五条", "当日单笔或者累计交易人民币5万元以上的现金缴存…应当报告。"),
             ("PBOC_3_2016", "第十一条", "金融机构发现或者有合理理由怀疑客户…应当提交可疑交易报告。"),
             ("PBOC_CDD_2025_11", "第十条", "高风险情形应采取强化尽职调查：了解资金来源与用途。")],
            "", "", "",
            "未按规定报送大额交易报告或者可疑交易报告"),
    ],
    "grey_zone": {
        "default_path": "人工复核",
        "pass_if": "提供销售合同、进货单据或完税凭证，能说明 6.2 万元现金来源且与经营规模匹配；历史现金流基线一致",
        "intercept_if": "无法说明现金来源，或与申报收入/经营规模明显不符，或短期内反复出现同类大额现金存入",
        "human_check_points": ["大额交易报告（CTR）是否已按 3 号令第五条报送",
                               "现金来源凭证（销售合同/进货单/完税凭证）",
                               "与客户历史现金交易基线对比",
                               "是否存在拆分为多笔贴线的迹象"]
    }
})

CASES.append({
    "case_id": "BLOCK-05", "title": "客户名称命中制裁/涉恐名单", "category": "intercept",
    "customer_info": {
        "name": "恐怖组织A关联人某某（个人）", "age": 39, "occupation": "无固定职业", "employer": "—",
        "income": "无固定收入", "open_date": "2026-08", "risk_level": "高",
        "tags": ["名单命中", "新开户", "无固定职业"]
    },
    "transactions": [
        {"date":"2026-10-09","time":"15:30","type":"转账收入","amount":1000,"counterparty":"张某","channel":"手机银行","summary":"个人转入"},
    ],
    "expected_conclusion": "拦截",
    "rules_hit": ["R005"],
    "official_type_no": "", "official_type_name": "",
    "trace_chain": [
        make_trace("R005", "客户名称命中模拟制裁/涉恐名单「恐怖组织A」，按特别预防措施先冻结、后核验，不经 AI 研判",
            [("AML_LAW_2025", "第四十条", "金融机构应当对涉嫌恐怖活动的名单进行监测，发现名单所列对象…"),
             ("PBOC_AML_SP_2026_1", "第三条", "金融机构应当对名单所列对象采取特别预防措施。"),
             ("PBOC_AML_SP_2026_1", "第七条", "金融机构应当立即停止为名单所列对象提供金融服务…")],
            "", "", "",
            "未按规定履行反洗钱特别预防措施义务"),
    ],
    "grey_zone": {}
})

CASES.append({
    "case_id": "BLOCK-06", "title": "对公账户月内密集转个人（公转私空壳特征）", "category": "intercept",
    "customer_info": {
        "name": "ZZ供应链有限公司（对公）", "age": None, "occupation": "批发零售（供应链）", "employer": "—",
        "income": "年营业额约300万元", "open_date": "2025-11", "risk_level": "高",
        "tags": ["新设公司", "公转私密集", "无社保缴纳记录"]
    },
    "transactions": [
        {"date":f"2026-10-{i+1:02d}","time":"11:00","type":"转账支出","amount":20300,
         "counterparty":["张某个","李某个","王某个","赵某个"][i % 4],"channel":"网银","summary":"往来款"}
        for i in range(12)
    ],
    "expected_conclusion": "拦截",
    "rules_hit": ["R007"],
    "official_type_no": "", "official_type_name": "",
    "trace_chain": [
        make_trace("R007", "成立不足 1 年的对公账户，单月 12 笔向 4 个个人账户转出（每笔 2.03 万元），无工资/社保/发票支撑，呈空壳公司转移资金特征",
            [("PBOC_3_2016", "第十一条", "金融机构发现或者有合理理由怀疑客户…应当提交可疑交易报告。"),
             ("PBOC_CDD_2025_11", "第十条", "高风险情形应采取强化尽职调查：核实交易背景与资金用途。")],
            "", "", "",
            "未按规定报送可疑交易报告"),
    ],
    "grey_zone": {}
})

CASES.append({
    "case_id": "BLOCK-07", "title": "虚拟货币 OTC 交易（USDT 买入）", "category": "intercept",
    "customer_info": {
        "name": "李某（个人）", "age": 27, "occupation": "自由职业", "employer": "—",
        "income": "自述网店经营，无纳税记录", "open_date": "2024-08", "risk_level": "高",
        "tags": ["无固定收入", "OTC 商户对手方", "整数单金额"]
    },
    # 附言为客户真实填写的备注（OTC 场景常见写法，不会 6 笔一字不差）；
    # 其中 4 笔含 USDT/买U，2 笔无附言——系统按附言+对手方关键词识别，不依赖每笔都写
    "transactions": [
        {"date":f"2026-10-{i+5:02d}","time":"23:20","type":"转账支出","amount":8000,
         "counterparty":"某OTC商户","channel":"手机银行","summary":memo}
        for i, memo in enumerate(["USDT", "买U", "", "USDT买入", "买U 8000", ""])
    ],
    "expected_conclusion": "拦截",
    "rules_hit": ["R008"],
    "official_type_no": "", "official_type_name": "",
    "trace_chain": [
        make_trace("R008", "6 笔转账中 4 笔附言含「USDT」「买U」（另 2 笔无附言），对手方均为 OTC 商户，金额为 8,000 元整数单，交易集中于深夜；客户自述网店经营但无纳税与平台结算记录",
            [("PBOC_3_2016", "第十一条", "金融机构发现或者有合理理由怀疑客户…应当提交可疑交易报告。"),
             ("PBOC_CDD_2025_11", "第十条", "高风险情形应采取强化尽职调查：了解资金来源与用途。")],
            "", "", "",
            "未按规定报送可疑交易报告"),
    ],
    "grey_zone": {}
})

CASES.append({
    "case_id": "BLOCK-08", "title": "客户拒不出示身份证件（身份不明）", "category": "intercept",
    "customer_info": {
        "name": "赵某（个人）", "age": 33, "occupation": "待核实", "employer": "—",
        "income": "客户未提供", "open_date": "2026-09", "risk_level": "高",
        "id_type": "", "id_no": "",
        "tags": ["拒不提供身份证件", "身份不明", "新开户"]
    },
    "transactions": [
        {"date":"2026-10-10","time":"11:00","type":"转账收入","amount":1000,"counterparty":"张某","channel":"手机银行","summary":"个人转入"},
    ],
    "expected_conclusion": "拦截",
    "rules_hit": ["R017"],
    "official_type_no": "", "official_type_name": "客户身份不明/证件缺失（CDD 条线 · 非交易型）",
    "trace_chain": [
        make_trace("R017", "客户在建立业务关系时拒不提供有效身份证件，证件类型与号码均为空；不属于制裁名单命中，属 CDD 条线身份不明",
            [("AML_LAW_2025", "第二十八条", "金融机构不得为身份不明的客户提供服务或者与其进行交易。"),
             ("PBOC_CDD_2025_11", "第八条", "金融机构不得为身份不明的客户提供服务或者与其进行交易。"),
             ("PBOC_CDD_2025_11", "第四十一条", "客户拒绝提供有效身份证件或者其他身份证明文件的，应当向中国反洗钱监测分析中心报告。")],
            "", "客户身份不明/证件缺失（CDD 条线 · 非交易型）", "",
            "为身份不明的客户提供服务或者与其进行交易"),
    ],
    "grey_zone": {}
})

# ============================================================
# 交易字段规范化：type / purpose / summary 三分
#   type    = 交易类型，只描述"钱怎么走"（转账/现金/跨境/结汇…）
#   purpose = 交易摘要/用途（工资、货款、税费、学费…）
#   summary = 交易附言，客户自己填的备注（可空）
# 旧数据把业务用途写进了 summary、type 里也混着"养老金入账""增值税缴纳"这类用途词，
# 这里统一拆开；规则与报告都按新字段取值。
# ============================================================
TYPE_MAP = {
    "转账收入": "转账收入", "转账支出": "转账支出", "转账转出": "转账支出",
    "现金存入": "现金存入", "取现": "现金支取",
    "养老金入账": "转账收入", "验资转入": "转账收入", "对公转账": "转账支出",
    "代发工资": "代发工资支出", "增值税缴纳": "代扣代缴支出",
    "跨境汇款": "跨境支出", "跨境收入": "跨境收入", "外汇收入": "结汇收入",
}

# (case_id, 旧 summary) -> (purpose, 新 summary)
PURPOSE_SPLIT = {
    ("PASS-01", "工资+绩效"): ("工资", ""),
    ("PASS-01", "月供"): ("房贷还款", ""),
    ("PASS-01", "信用卡还款"): ("信用卡还款", ""),
    ("PASS-02", "月养老金"): ("养老金", ""),
    ("PASS-02", "取现"): ("日常支取", ""),
    ("PASS-03", "验资款转入基本户"): ("验资款", ""),
    ("PASS-03", "支付货款（合同编号C20260701）"): ("货款", "合同编号C20260701"),
    ("PASS-03", "发放工资"): ("工资", ""),
    ("PASS-03", "增值税申报"): ("增值税", ""),
    ("BLOCK-01", ""): ("货款", ""),
    ("BLOCK-01", "货款"): ("货款", ""),
    ("BLOCK-02", ""): ("投资款", ""),
    ("BLOCK-02", "返款"): ("返利", "返款"),
    ("BLOCK-03", "个人转入"): ("个人转入", ""),
    ("BLOCK-04", ""): ("", ""),
    ("GREY-01", "学费"): ("学费", ""),
    ("GREY-01", "住宿费"): ("住宿费", ""),
    ("GREY-02", "平台结算单号AMZ-20260715001"): ("平台货款结算", "AMZ-20260715001"),
    ("GREY-02", "支付供应商货款（合同编号C20260710）"): ("货款", "合同编号C20260710"),
    ("GREY-02", "物流费（发票编号F20260802）"): ("物流费", "发票编号F20260802"),
    ("GREY-03", "佣金（EUR等值）"): ("佣金", ""),
    ("GREY-03", "咨询费（EUR等值）"): ("咨询费", ""),
    ("GREY-03", "推广费（EUR等值）"): ("推广费", ""),
    ("GREY-04", "月度赡家款"): ("赡家款", ""),
    ("EXCLUDE-01", "货款"): ("货款", ""),
    ("EXCLUDE-01", "采购货款"): ("采购货款", ""),
    ("EXCLUDE-01", "运费"): ("运费", ""),
    ("GREY-05", "货款回笼"): ("货款", "货款回笼"),
    ("BLOCK-05", "个人转入"): ("个人转入", ""),
    ("BLOCK-06", "往来款"): ("往来款", ""),
    ("BLOCK-07", "USDT"): ("虚拟货币交易", "USDT"),
    ("BLOCK-07", "买U"): ("虚拟货币交易", "买U"),
    ("BLOCK-07", ""): ("虚拟货币交易", ""),
    ("BLOCK-07", "USDT买入"): ("虚拟货币交易", "USDT买入"),
    ("BLOCK-07", "买U 8000"): ("虚拟货币交易", "买U 8000"),
    ("BLOCK-08", "个人转入"): ("个人转入", ""),
}

# 外币交易：case_id -> 币种；amount 记原币，amount_cny 按 fx_rates.json 的取整汇率折算
# （汇率文件同时给前端展示用，界面上的"演示折算汇率"与数据里的金额永远一致）
FX = {"GREY-02": "USD", "GREY-03": "EUR"}


def _fx_rate(currency):
    with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data",
                           "fx_rates.json"), encoding="utf-8") as f:
        return json.load(f)["rates"][currency]


# 只有跨境/结汇类交易按外币记；同一案例里的境内收付仍是人民币
FX_TYPES = ("跨境收入", "跨境支出", "结汇收入", "购汇支出")


def normalize(cases):
    for c in cases:
        for t in c["transactions"]:
            key = (c["case_id"], t.get("summary", ""))
            pr, summ = PURPOSE_SPLIT.get(key, ("", t.get("summary", "")))
            t["type"] = TYPE_MAP.get(t["type"], t["type"])
            t["purpose"] = pr
            t["summary"] = summ
            if c["case_id"] in FX and t["type"] in FX_TYPES:
                cur = FX[c["case_id"]]
                t["currency"] = cur
                t["amount_cny"] = round(t["amount"] * _fx_rate(cur), 2)
            else:
                t["currency"], t["amount_cny"] = "CNY", t["amount"]
    return cases


normalize(CASES)

# ============================================================
# 输出：演示数据集独立文件（不写入 SQLite）
# ============================================================
if __name__ == "__main__":
    payload = {
        "dataset": "demo",
        "name": "清源AML 演示数据集",
        "version": "1.1",
        "synthetic": True,
        "notice": "仅用于功能演示与案例展示。全部为脱敏合成数据，不指向任何真实客户，不构成合规依据。",
        "cases": CASES,
    }
    with open(DEMO_PATH, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    print(f"演示数据集已生成：{DEMO_PATH}（{len(CASES)} 条）")
    for cat in ("intercept", "grey", "pass"):
        n = sum(1 for c in CASES if c["category"] == cat)
        print(f"  {cat}: {n} 条")
    # 演示案例只写 JSON；不触碰已定性案例库
    conn = sqlite3.connect(DB_PATH)
    try:
        conn.execute("DELETE FROM cases WHERE source='demo'")
        conn.commit()
        print("SQLite cases 表未写入演示案例（已定性案例库保留）")
    except sqlite3.OperationalError:
        pass
    conn.close()
