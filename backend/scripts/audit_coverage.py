"""覆盖度审计 + 规则回归测试。

两件事：
1. 法规条款覆盖：239 条里有多少被规则引用、哪些法规一条都没被引用。
2. 规则覆盖：17 条规则定义中多少条有代码实现、多少条被演示案例或测试夹具实际触发。

测试夹具只用于回归验证，不写入 demo 案例库（避免破坏 10–12 条的冻结范围）。
"""
import json
import os
import sqlite3
import sys
from collections import OrderedDict

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB = os.path.join(BASE, "data", "qingyuan.db")
sys.path.insert(0, BASE)
from domain.rules import RULE_FUNCS, run_engine  # noqa: E402
from case_store import list_cases  # noqa: E402


def tx(date, time, type_, amount, counterparty="—", channel="网银", summary=""):
    return {"date": date, "time": time, "type": type_, "amount": amount,
            "counterparty": counterparty, "channel": channel, "summary": summary}


# 只为触发单条规则而构造的最小夹具，不对应业务案例
FIXTURES = [
    {
        "id": "T-R001",
        "target": "R001",
        "desc": "单日现金存入 6 万元（大额现金标准 5 万）",
        "customer": {"name": "测试客户甲（个人）", "open_date": "2020-01"},
        "txs": [tx("2026-10-12", "10:20", "现金存入", 60000, "柜面", "柜面", "现金存款")],
    },
    {
        "id": "T-R005",
        "target": "R005",
        "desc": "客户名称命中模拟制裁名单",
        "customer": {"name": "恐怖组织A（个人）", "open_date": "2018-03"},
        "txs": [tx("2026-10-12", "14:10", "转账收入", 1000, "个人", "网银", "日常往来")],
    },
    {
        "id": "T-R007",
        "target": "R007",
        "desc": "对公客户单月 12 笔向个人账户转出（空壳特征）",
        "customer": {"name": "某某贸易有限公司", "open_date": "2025-01"},
        "txs": [tx("2026-10-%02d" % (i + 1), "11:00", "转账支出", 20300,
                   ["张某个", "李某个", "王某个", "赵某个"][i % 4], "网银", "往来款")
                for i in range(12)],
    },
    {
        "id": "T-R008",
        "target": "R008",
        "desc": "交易附言含虚拟货币关键词 USDT",
        "customer": {"name": "测试客户乙（个人）", "open_date": "2021-06"},
        "txs": [tx("2026-10-12", "23:30", "转账支出", 8000, "某OTC商户", "手机银行", "USDT 买入")],
    },
    {
        "id": "T-R017",
        "target": "R017",
        "desc": "客户姓名为空（身份不明）→ CDD 条线拦截，不套制裁名单",
        "customer": {"open_date": "2020-01"},
        "txs": [tx("2026-10-12", "10:00", "转账收入", 1000, "张某", "网银", "日常往来")],
    },
]


def section(title):
    print("\n" + "=" * 78)
    print(title)
    print("=" * 78)


def clause_coverage(conn):
    section("一、法规条款覆盖")
    rows = conn.execute("""
        SELECT r.reg_code, r.name, c.id AS cid
        FROM regulations r JOIN clauses c ON c.regulation_id = r.id
        ORDER BY r.id, c.id
    """).fetchall()
    ref = set()
    for row in conn.execute("SELECT legal_clause_ids FROM rules"):
        ref.update(json.loads(row[0] or "[]"))

    grouped = OrderedDict()
    for code, name, cid in rows:
        grouped.setdefault((code, name), []).append(cid)

    print(f"{'法规':<30}{'条款':>6}{'被规则引用':>10}{'未引用':>8}")
    for (code, name), cids in grouped.items():
        used = sum(1 for c in cids if c in ref)
        print(f"{name[:28]:<32}{len(cids):>6}{used:>10}{len(cids) - used:>8}")
    print(f"\n合计：{len(rows)} 条条款，被规则引用 {len(ref)} 条，"
          f"未引用 {len(rows) - len(ref)} 条（{(len(rows)-len(ref))/len(rows)*100:.1f}%）")
    print("说明：报告要素字段表、已废止法规、程序性条款本身不应被规则引用；")
    print("      但 CDD（52 条）0 引用、反洗钱法 65 条仅 1 引用，属于实质性缺口。")


def rule_coverage(conn):
    section("二、规则覆盖")
    defined = [r[0] for r in conn.execute("SELECT rule_id FROM rules ORDER BY rule_id")]
    implemented = sorted(RULE_FUNCS)

    demo_hits = {}
    for c in list_cases():
        for rid in c.get("rules_hit", []):
            demo_hits.setdefault(rid, []).append(c["case_id"])

    fixture_hits = {}
    fixture_ok = []
    for f in FIXTURES:
        hits = run_engine(f["txs"], f["customer"], conn)
        ids = [h["rule_id"] for h in hits]
        fixture_hits[f["id"]] = ids
        fixture_ok.append(f["target"] in ids)
        ok = f["target"] in ids
        print(f"  [{'PASS' if ok else 'FAIL'}] {f['id']} → {f['target']}：{f['desc']}"
              f"（实际命中：{', '.join(ids) or '无'}）")

    print(f"\n{'规则':<8}{'名称':<22}{'有代码':>6}{'演示案例':>8}{'测试夹具':>8}")
    for rid in defined:
        name = conn.execute("SELECT name FROM rules WHERE rule_id=?", (rid,)).fetchone()[0]
        has_code = "是" if rid in implemented else "否"
        demo = len(demo_hits.get(rid, []))
        fix = sum(1 for v in fixture_hits.values() if rid in v)
        print(f"{rid:<8}{name[:20]:<22}{has_code:>6}{demo:>8}{fix:>8}")

    missing_code = [r for r in defined if r not in implemented]
    print(f"\n定义 {len(defined)} 条 / 有代码 {len(implemented)} 条 / "
          f"演示案例触发 {len(demo_hits)} 条 / 夹具补齐后触发 "
          f"{len(set(demo_hits) | {f['target'] for f in FIXTURES})} 条")
    if missing_code:
        print(f"无代码实现（规则库是死数据）：{', '.join(missing_code)}")
    return all(fixture_ok)


def type_coverage(conn):
    section("三、官方类型覆盖")
    rows = conn.execute("""
        SELECT rule_id, official_type_no, official_type_name FROM rules
        WHERE official_type_no IS NOT NULL AND official_type_no != ''
    """).fetchall()

    def code_of(value):
        import re
        m = re.search(r"第([0-9]+(?:-[0-9]+)?)类", value or "")
        return m.group(1) if m else ""

    covered = {code_of(r[1]) for r in rows if code_of(r[1])}
    # 官方对照表（银行业参考版）共 12 类、13 个编号条目（1-1、1-2、2~12）；
    # "第13~16类"是行内归纳维度，不是官方类型
    standard = ["1-1", "1-2", "2", "3", "4", "5", "6", "7", "8", "9", "10", "11", "12"]
    print("有规则对应的官方类型：" + "、".join(f"官方第{c}类" for c in sorted(covered)))
    print("无规则对应的官方类型：" + ("、".join(f"官方第{c}类" for c in standard if c not in covered) or "无"))
    print("演示案例实际覆盖的类型：" + "、".join(sorted({
        c.get("official_type_no", "") for c in list_cases() if c.get("official_type_no")
    })))
    print("说明：行内归纳维度（分拆/新户跨境/虚拟货币/名单匹配）不占官方类型编号；"
          "非交易型可疑行为（客户身份不明）由 R017 承接，走覆盖矩阵「无法归类」出口。")


def main():
    conn = sqlite3.connect(DB)
    clause_coverage(conn)
    ok = rule_coverage(conn)
    type_coverage(conn)
    section("结论")
    print("规则回归：" + ("全部通过" if ok else "存在失败项"))
    conn.close()
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
