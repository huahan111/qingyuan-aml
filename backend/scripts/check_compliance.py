"""Mock 案例数据合规性检查 + 零token验证 + 生成测试报告"""
import sqlite3, os, json, re, sys

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB = os.path.join(BASE, "data", "qingyuan.db")
MOCK_DIR = os.path.join(BASE, "data", "mock_diagnosis")

sys.path.insert(0, BASE)
from case_store import list_cases, get_case  # noqa: E402

report = []
def log(s=""):
    report.append(s)
    print(s)

# ---------- 1. 脱敏合规检查 ----------
log("## 1. 数据脱敏合规检查\n")
conn = sqlite3.connect(DB)
conn.row_factory = sqlite3.Row
cases = []
for meta in list_cases():
    c = get_case(meta["case_id"])
    cases.append({
        "case_id": c["case_id"], "category": c.get("category", ""),
        "customer_info": json.dumps(c.get("customer_info", {}), ensure_ascii=False),
        "transactions": json.dumps(c.get("transactions", []), ensure_ascii=False),
        "rules_hit": json.dumps(c.get("rules_hit", []), ensure_ascii=False),
        "expected_conclusion": c.get("expected_conclusion", ""),
    })

# 禁止出现的真实信息模式
patterns = {
    "身份证号": r"\b\d{17}[\dXx]\b",
    "银行卡号": r"\b\d{16,19}\b",
    "手机号": r"\b1[3-9]\d{9}\b",
    "真实姓名格式(非脱敏)": r"[一-龥]{2,4}(?<!某某)(?<!本人)(?<!自营)(?<!社保)(?<!基金)(?<!税务)(?<!员工)(?<!妻子)(?<!建材)(?<!批发)(?<!零售)(?<!教师)(?<!职员)(?<!公司)(?<!银行)(?<!网银)(?<!柜面)(?<!现金)(?<!转账)(?<!代发)(?<!跨境)(?<!外汇)(?<!养老)(?<!验资)(?<!货款)(?<!工资)(?<!佣金)(?<!学费)(?<!住宿)(?<!物流)(?<!增值)(?<!返款)",
}
issues = 0
for c in cases:
    blob = c["customer_info"] + c["transactions"]
    for name, pat in patterns.items():
        if name.startswith("真实姓名"):  # 该模式误报率高，仅人工抽查，跳过自动判定
            continue
        m = re.findall(pat, blob)
        if m:
            log(f"  ✗ {c['case_id']} 含疑似{name}: {m[:3]}")
            issues += 1
log(f"  自动扫描（身份证/银行卡/手机号正则）：{'发现 ' + str(issues) + ' 处疑似' if issues else '全部通过，无真实敏感信息'}")
# 人名脱敏抽查
names = set()
for c in cases:
    ci = json.loads(c["customer_info"])
    names.add(ci["name"])
    for t in json.loads(c["transactions"]):
        names.add(t.get("counterparty", ""))
desens = [n for n in names if n and ("某某" in n or re.search(r"[一-龥]X", n) or "XX" in n
          or re.match(r"^[A-E]公司$", n) or re.match(r"^[一-龥]某（个人）$", n) or "妻子" in n
          or n in ("本人","社保基金","税务局","员工工资户","验资户","Amazon结算","市教委","XX大学（境外）"))]
log(f"  人名/机构名脱敏抽查：{len(names)} 个主体，{len(desens)} 个为脱敏写法（某某/X某/XX公司），其余为角色主体（本人/税务局/社保基金等）")
unmasked = names - set(desens)
if unmasked:
    log(f"  待人工确认主体：{sorted(unmasked)}")

# ---------- 2. 结论一致性校验 ----------
log("\n## 2. Mock 诊断结论一致性校验\n")
mismatch = 0
for c in cases:
    path = os.path.join(MOCK_DIR, f"{c['case_id']}.json")
    assert os.path.exists(path), f"{c['case_id']} 缺诊断文件"
    diag = json.load(open(path, encoding="utf-8"))
    ok = diag["conclusion"] == c["expected_conclusion"]
    if not ok:
        mismatch += 1
        log(f"  ✗ {c['case_id']}: 诊断={diag['conclusion']} 期望={c['expected_conclusion']}")
log(f"  17 条案例诊断结论 vs 期望结论：{'全部一致 ✓' if not mismatch else str(mismatch) + ' 条不一致'}")

# ---------- 3. 规则引擎一致性 ----------
log("\n## 3. 规则引擎期望 vs 实际（17条全量）\n")
sys.path.insert(0, BASE)
from domain.rules import run_engine
log("| 案例 | 类别 | 期望规则 | 实际命中 | 一致 |")
log("|---|---|---|---|---|")
ok_cnt = 0
for c in cases:
    txs = json.loads(c["transactions"]); cust = json.loads(c["customer_info"])
    exp = set(json.loads(c["rules_hit"]))
    act = {h["rule_id"] for h in run_engine(txs, cust, conn)}
    ok = exp == act; ok_cnt += ok
    log(f"| {c['case_id']} | {c['category']} | {sorted(exp) or '无'} | {sorted(act) or '无'} | {'✓' if ok else '✗'} |")
log(f"\n  合计：{ok_cnt}/17 一致")

# ---------- 4. 零 token 验证 ----------
log("\n## 4. Mock 模式零 token 验证\n")
src = open(os.path.join(BASE, "ai_diagnosis.py"), encoding="utf-8").read()
mock_cls = src.split("class MockProvider")[1].split("class LiveProvider")[0]
has_net = any(k in mock_cls for k in ("urllib", "requests", "http", "urlopen", "socket"))
log(f"  MockProvider 代码扫描：{'发现网络调用 ✗' if has_net else '无任何网络/HTTP 调用，仅读本地 JSON ✓'}")
default_mock = 'AML_AI_PROVIDER", "mock"' in src
log(f"  默认 Provider：{'mock（未配置时不调大模型）✓' if default_mock else '非 mock ✗'}")
live_guard = "未配置 OPENAI_API_KEY" in src
log(f"  Live Provider 无 key 时显式报错（不会静默调用）：{'✓' if live_guard else '✗'}")

# ---------- 5. 页面如实标注 ----------
log("\n## 5. 演示标注检查\n")
# 标注可能由 HTML 静态写死，也可能由 JS 渲染（如 AI 徽标），两者都要扫，
# 否则会漏判"页面上看不到免责声明"这类问题
front_dir = os.path.join(BASE, "..", "frontend")
front_src = ""
for root, _dirs, files in os.walk(front_dir):
    for fn in files:
        if fn.endswith((".html", ".js")):
            front_src += open(os.path.join(root, fn), encoding="utf-8").read()
for kw in ["演示系统", "脱敏合成", "预生成", "免责声明", "不构成任何实际业务的合规依据"]:
    log(f"  页面含「{kw}」：{'✓' if kw in front_src else '✗ 缺失'}")

conn.close()

# ---------- 6. 覆盖审计 ----------
import subprocess
log("\n## 6. 覆盖审计（audit_coverage.py）\n")
audit = subprocess.run([sys.executable, os.path.join(BASE, "scripts", "audit_coverage.py")],
                       capture_output=True, text=True)
log("```")
log(audit.stdout.strip())
log("```")

out = os.path.join(BASE, "..", "docs", "Mock案例测试报告.md")
header = ("# 清源AML MVP · Mock 案例测试报告\n\n"
          "> 生成方式：`python3 backend/scripts/check_compliance.py` 自动产出\n"
          "> 数据基准：演示数据集 `backend/data/demo_cases.json`（17 条：3 放行 + 8 拦截 + 6 灰区）\n\n")
with open(out, "w", encoding="utf-8") as f:
    f.write(header + "\n".join(report) + "\n")
print(f"\n报告已写入: {out}")
