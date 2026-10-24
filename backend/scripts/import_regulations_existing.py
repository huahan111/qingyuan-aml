"""把已有2份监管原文 txt 切块入库。
切块依据：已通读全文，按类型/部分的起止行号区间切（cat -n 行号，1-based）。
"""
import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "qingyuan.db")
SRC_DIR = "docs/regulations"

def read_lines(path):
    with open(path, encoding="utf-8") as f:
        return f.readlines()

def clean(block_lines):
    """去掉 PAGE 分隔行，合并为单条文本"""
    out = []
    for ln in block_lines:
        s = ln.strip()
        if s.startswith("===== PAGE") or s.startswith("===PAGE"):
            continue
        out.append(s)
    return "\n".join([x for x in out if x])

def insert_reg(conn, code, name, issuer, doc_number, eff, source):
    conn.execute(
        "INSERT OR IGNORE INTO regulations(reg_code,name,issuer,doc_number,effective_date,source) VALUES(?,?,?,?,?,?)",
        (code, name, issuer, doc_number, eff, source))
    return conn.execute("SELECT id FROM regulations WHERE reg_code=?", (code,)).fetchone()[0]

def insert_clause(conn, reg_id, chapter, clause_no, content, tags=""):
    conn.execute(
        "INSERT OR REPLACE INTO clauses(regulation_id,chapter,clause_no,content,topic_tags) VALUES(?,?,?,?,?)",
        (reg_id, chapter, clause_no, content, tags))

def import_type_table(conn):
    """《可疑交易类型和识别点对照表（银行业参考版）》——按 14 类切块"""
    lines = read_lines(os.path.join(SRC_DIR, "可疑交易类型和识别点对照表.txt"))
    rid = insert_reg(conn, "PBOC_TYPE_TABLE", "可疑交易类型和识别点对照表（银行业参考版）",
                     "中国人民银行反洗钱局", "—", "2012年版（随洗钱活动变化调整）",
                     "监管公开参考文件；R009-R016 规则与AI官方类型清单的设计依据")
    # (clause_no, 类型名称, 起始行, 终止行, tags)  行号为 cat -n 1-based，区间为 [start, end)
    # 该 txt 为 PDF 双栏混排，类型编号嵌在内容块中间。
    # 切法：以编号行为锚点，块区间=[本编号行, 下一编号行)，保证该类型识别点完整。
    # 编号行号（grep 实测，1-based）：1-1→22, 1-2→64, 2→95, 3→116, 4→154, 5→170,
    #   6→188, 7→202, 8→222, 9→247, 10→265, 11→279, 12→304
    blocks = [
        ("类型1-1", "疑似非法汇兑型地下钱庄", 1,   64,  "地下钱庄,汇兑,资金交易识别点,账户资料识别点"),
        ("类型1-2", "疑似非法结算型地下钱庄", 64,  95,  "地下钱庄,结算,空壳公司,网银快进快出"),
        ("类型2",   "疑似腐败",            95,  116, "腐败,公职人员,身份不符,亲属账户"),
        ("类型3",   "疑似毒品犯罪",         116, 154, "毒品,ATM,无卡存款,整数倍,凌晨"),
        ("类型4",   "疑似走私",            154, 170, "走私,地下钱庄,报关价格,外贸"),
        ("类型5",   "疑似诈骗",            170, 188, "诈骗,开户试卡,沉睡期,陪同开户"),
        ("类型6",   "疑似集资",            188, 202, "集资,分散转入集中转出,返款,三段式"),
        ("类型7",   "疑似传销",            202, 222, "传销,金字塔,返利,周期"),
        ("类型8",   "疑似套现",            222, 247, "套现,POS,商户,刷卡规律"),
        ("类型9",   "疑似涉税犯罪",         247, 265, "涉税,公转私,批量存单,过渡性交易"),
        ("类型10",  "疑似恐怖融资",         265, 279, "恐怖融资,集中转入分散转出,现金,异地ATM"),
        ("类型11",  "疑似赌博",            279, 304, "赌博,网站,交易时间,整数倍"),
        ("类型12",  "疑似虚假出资、抽逃出资", 304, len(lines) + 1, "验资,抽逃出资,集中开立,速转"),
    ]
    for no, name, s, e, tags in blocks:
        content = f"【{no} {name}】\n" + clean(lines[s - 1:e - 1])
        insert_clause(conn, rid, "可疑交易类型", f"{no} {name}", content, tags)
    print(f"对照表入库完成：{len(blocks)} 类")

def import_report_elements(conn):
    """《金融机构大额交易和可疑交易报告要素内容》(3号令附件)——按 5 大列表切块"""
    lines = read_lines(os.path.join(SRC_DIR, "报告要素内容_2016修订.txt"))
    rid = insert_reg(conn, "PBOC_3_2016_ATTACH", "金融机构大额交易和可疑交易报告要素内容",
                     "中国人民银行", "人民银行令〔2016〕第3号 附件", "2017-07-01",
                     "3号令附件；STR 62项要素结构依据")
    blocks = [
        ("大额交易报告要素", "大额45项", 1, 55,   "大额交易,45项,报告要素"),
        ("银行业可疑交易报告要素", "银行业62项", 55, 124, "可疑交易,银行业,62项,STR"),
        ("证券期货业可疑交易报告要素", "证券期货48项", 124, 152, "可疑交易,证券期货,48项"),
        ("保险业可疑交易报告要素", "保险业53项", 152, 242, "可疑交易,保险业,53项"),
        ("通用可疑交易报告要素", "通用29项", 242, 279, "可疑交易,通用,29项"),
    ]
    for chapter, no, s, e, tags in blocks:
        content = f"【{chapter}】\n" + clean(lines[s - 1:e - 1])
        insert_clause(conn, rid, chapter, no, content, tags)
    print(f"报告要素入库完成：{len(blocks)} 块")

if __name__ == "__main__":
    conn = sqlite3.connect(DB_PATH)
    import_type_table(conn)
    import_report_elements(conn)
    conn.commit()
    n = conn.execute("SELECT COUNT(*) FROM clauses").fetchone()[0]
    print(f"clauses 总数: {n}")
    conn.close()
