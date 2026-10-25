"""把 4 份新法规 txt 按"第X条"切块入库。
条款号匹配行首中文数字；章节标题"第X章"提取为 chapter。
"""
import sqlite3, os, re

DB_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "qingyuan.db")
# 监管原文默认取仓库内 docs/regulations/（公开法规全文，随仓库分发）；
# 也可用环境变量 QINGYUAN_REG_SRC 指向自备目录。
SRC_DIR = os.getenv("QINGYUAN_REG_SRC") or os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "docs", "regulations"))
if not os.path.isdir(SRC_DIR):
    raise SystemExit(f"找不到监管原文目录：{SRC_DIR}\n"
                     f"请把法规 txt 放到 docs/regulations/，或用 QINGYUAN_REG_SRC 指定目录。")

CLAUSE_RE = re.compile(r"^(第[一二三四五六七八九十百零]+条)")
CHAPTER_RE = re.compile(r"^(第[一二三四五六七八九十百零]+章)")

# 各法规的关键条款标签（供检索与溯源）
TAG_MAP = {
    "AML_LAW_2025": {
        "第四条": "风险为本,措施与风险相适应",
        "第十九条": "受益所有人,穿透识别",
        "第二十八条": "拒绝业务,身份不明",
        "第三十条": "措施匹配,风险相称",
        "第三十四条": "保存10年,记录保存",
        "第三十六条": "特别预防措施,涉恐冻结",
    },
    "PBOC_3_2016": {
        "第五条": "大额标准,5万,20万,50万,200万",
        "第十一条": "可疑交易,合理怀疑",
        "第十二条": "机构自定标准,有效性",
        "第十四条": "人工分析,排除理由",
        "第十八条": "名单回溯,回溯筛查",
    },
    "PBOC_CDD_2025_11": {
        "第一条": "适用范围,客户尽职调查",
        "第九条": "简化尽职调查,低风险",
        "第十条": "强化尽职调查,EDD,高风险",
        "第十九条": "受益所有人,穿透识别",
        "第三十九条": "保存10年",
    },
    "TERROR_FREEZE_2014": {
        "第三条": "涉恐名单,公安部公布",
        "第四条": "立即冻结,资产冻结",
        "第六条": "冻结通知,告知义务",
    },
}

def read_lines(path):
    with open(path, encoding="utf-8") as f:
        return f.readlines()

def find_start(lines):
    for i, line in enumerate(lines):
        s = line.strip()
        if CHAPTER_RE.match(s):
            return i
        if CLAUSE_RE.match(s):
            return i
    return 0

def parse_blocks(lines):
    start = find_start(lines)
    chapter = ""
    blocks = []
    cur_no = None
    cur_buf = []
    for line in lines[start:]:
        s = line.rstrip()
        if not s:
            continue
        if s == "目录":
            continue
        if CHAPTER_RE.match(s):
            chapter = s
            continue
        m = CLAUSE_RE.match(s)
        if m:
            if cur_no:
                blocks.append((chapter, cur_no, "\n".join(cur_buf)))
            cur_no = m.group(1)
            cur_buf = [s]
        else:
            if cur_buf:
                cur_buf.append(s)
    if cur_no:
        blocks.append((chapter, cur_no, "\n".join(cur_buf)))
    return blocks

def insert_reg(conn, code, name, issuer, doc, eff, source):
    conn.execute(
        "INSERT OR IGNORE INTO regulations(reg_code,name,issuer,doc_number,effective_date,source) VALUES(?,?,?,?,?,?)",
        (code, name, issuer, doc, eff, source))
    return conn.execute("SELECT id FROM regulations WHERE reg_code=?", (code,)).fetchone()[0]

def import_file(conn, filepath, reg_code, reg_name, issuer, doc, eff, source):
    rid = insert_reg(conn, reg_code, reg_name, issuer, doc, eff, source)
    lines = read_lines(filepath)
    blocks = parse_blocks(lines)
    tags = TAG_MAP.get(reg_code, {})
    for chapter, clause_no, content in blocks:
        tag = tags.get(clause_no, "")
        conn.execute(
            "INSERT OR REPLACE INTO clauses(regulation_id,chapter,clause_no,content,topic_tags) VALUES(?,?,?,?,?)",
            (rid, chapter, clause_no, content, tag))
    print(f"  {reg_name}: {len(blocks)} 条")

if __name__ == "__main__":
    conn = sqlite3.connect(DB_PATH)
    files = [
        ("反洗钱法_2025施行.txt", "AML_LAW_2025", "中华人民共和国反洗钱法",
         "全国人大常委会", "主席令第三十八号", "2025-01-01",
         "2024年11月修订通过，2025年1月1日施行；含特别预防措施、受益所有人等新规"),
        ("大额交易和可疑交易报告管理办法_2016_3号令.txt", "PBOC_3_2016",
         "金融机构大额交易和可疑交易报告管理办法",
         "中国人民银行", "人民银行令〔2016〕第3号", "2017-07-01",
         "大额交易标准、可疑交易报告义务、机构自定监测标准"),
        ("客户尽职调查管理办法_2025_11号令.txt", "PBOC_CDD_2025_11",
         "金融机构客户尽职调查和客户身份资料及交易记录保存管理办法",
         "人民银行/金融监管总局/证监会", "〔2025〕第11号令", "2026-01-01",
         "CDD触发情形、简化/强化尽调分级、受益所有人穿透"),
        ("涉及恐怖活动资产冻结管理办法.txt", "TERROR_FREEZE_2014",
         "涉及恐怖活动资产冻结管理办法",
         "中国人民银行等", "多部门联合令", "2014-01-10",
         "涉恐名单命中立即冻结、通知义务；注：已被〔2026〕第1号令废止"),
    ]
    for fn, code, name, issuer, doc, eff, src in files:
        import_file(conn, os.path.join(SRC_DIR, fn), code, name, issuer, doc, eff, src)
    conn.commit()
    n = conn.execute("SELECT COUNT(*) FROM regulations").fetchone()[0]
    c = conn.execute("SELECT COUNT(*) FROM clauses").fetchone()[0]
    print(f"法规库总计：{n} 份法规，{c} 条条款")
    conn.close()
