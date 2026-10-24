"""清源MVP FastAPI 后端：案例库 + 规则引擎 + AI诊断 + 三向分流 + 溯源面板。

演示案例与法规库只读；上报台账（submissions）与已定性案例库持久化到 SQLite。
路由按模块装配：报告见 api/reports.py，台账见 api/submissions.py，案例/联动见 api/cases.py、api/linkage.py。
"""
import json
import os
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse

from domain.rules import RULE_FUNCS, run_engine
from ai_diagnosis import AiUnavailableError, get_provider, LiveProvider
from case_store import dataset_meta, list_cases as demo_list_cases, get_case as demo_get_case
from infra.db import ensure_case_library_schema, ensure_submissions_table, get_db
from infra.security import is_read_only
from services.triage import triage
from services.screening import screen
from services.ctr import build_ctr
from services.similar_cases import similar_for_case
from api.reports import router as reports_router
from api.submissions import router as submissions_router
from api.cases import router as cases_router
from api.linkage import router as linkage_router
from api.admin import router as admin_router
from api.cdd import router as cdd_router

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PORT = int(os.getenv("QINGYUAN_PORT", "8000"))
FRONTEND_DIR = os.path.join(BASE_DIR, "..", "frontend")

app = FastAPI(title="清源AML MVP", version="1.0.0",
              description="反洗钱智能监测平台 MVP：规则引擎+AI诊断+溯源面板。仅供演示与学习。")

# CORS：默认同源（不挂中间件，跨域请求由浏览器拦截）。此前 allow_origins=["*"]
# 会让用户浏览器中的任意网页都能对本机实例发跨域 POST（重置演示/伪造台账）。
# 确需跨域时用 QINGYUAN_CORS_ORIGINS 显式配置白名单（逗号分隔）。
_CORS_ORIGINS = [o.strip() for o in os.getenv("QINGYUAN_CORS_ORIGINS", "").split(",") if o.strip()]
if _CORS_ORIGINS:
    app.add_middleware(CORSMiddleware, allow_origins=_CORS_ORIGINS,
                       allow_methods=["*"], allow_headers=["*"])

# 只读模式：非 GET/HEAD/OPTIONS 请求默认全部拒绝，仅放行"只计算、不落库"的
# 研判 / 报告生成接口（公开演示可看不可写）。新增写接口默认即被拦截（fail-closed），
# 不再依赖事后往黑名单里补路径。
_READ_ONLY_ALLOWED_PREFIX = ("/api/diagnose/", "/api/report/", "/api/cdd/")


@app.middleware("http")
async def read_only_guard(request, call_next):
    if (is_read_only() and request.method not in ("GET", "HEAD", "OPTIONS")
            and not request.url.path.startswith(_READ_ONLY_ALLOWED_PREFIX)):
        return JSONResponse({"detail": "当前为只读演示环境，写入接口已关闭"}, status_code=403)
    return await call_next(request)


app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")
app.include_router(reports_router)
app.include_router(submissions_router)
app.include_router(cases_router)
app.include_router(linkage_router)
app.include_router(admin_router)
app.include_router(cdd_router)


def db():
    return get_db()


ensure_submissions_table()
ensure_case_library_schema()


# ---------------- API ----------------

@app.get("/api/health")
def health():
    provider = get_provider()
    meta = dataset_meta()
    return {"status": "ok", "ai_provider": getattr(provider, "name", "mock"),
            "live_available": LiveProvider().available(), "read_only": is_read_only(),
            "dataset": meta}


@app.get("/api/dataset")
def dataset_info():
    return dataset_meta()


@app.get("/api/fx")
def fx_rates():
    """演示折算汇率：外币交易按此折算人民币，界面展示与数据金额同源。"""
    with open(os.path.join(BASE_DIR, "data", "fx_rates.json"), encoding="utf-8") as f:
        return json.load(f)


@app.get("/api/cases")
def list_cases():
    return {"dataset": dataset_meta(), "cases": demo_list_cases()}


@app.get("/api/cases/{case_id}")
def get_case(case_id: str):
    case = demo_get_case(case_id)
    if not case:
        # 演示 JSON 里没有 → 再查已定性案例库（LIB- / DIS- 条目可查看详情）
        from infra.case_repo import get_library
        conn = db()
        try:
            case = get_library(conn, case_id)
        finally:
            conn.close()
    if not case:
        raise HTTPException(404, f"案例 {case_id} 不存在")
    return case


@app.post("/api/diagnose/{case_id}")
def diagnose(case_id: str):
    case = demo_get_case(case_id)
    if not case:
        raise HTTPException(404, f"案例 {case_id} 不存在")
    conn = db()
    try:
        # 1. 规则引擎
        rule_hits = run_engine(case["transactions"], case["customer_info"], conn)
        # 2. AI 诊断（Mock / Live 同签名：available(case_id) + diagnose(case_id, case, rule_hits)）
        provider = get_provider()
        if not (hasattr(provider, "available") and provider.available(case_id)):
            raise HTTPException(503, f"AI Provider 不可用（case={case_id}）")
        try:
            ai_result = provider.diagnose(case_id, case, rule_hits)
        except AiUnavailableError as e:
            # Live 上游故障（网络/超时/返回不合格）：明确报 502，不让异常裸抛成 500
            raise HTTPException(502, str(e))
        # 3. 三向分流 + 相似案例召回
        triage_result = triage(rule_hits, ai_result, case)
        similar_cases = similar_for_case(case, conn)
    finally:
        conn.close()
    return {
        "case_id": case_id, "title": case["title"],
        "rule_hits": rule_hits,
        "ai_diagnosis": ai_result,
        "triage": triage_result,
        "similar_cases": similar_cases,
        "trace_chain": case["trace_chain"],
        "expected_conclusion": case["expected_conclusion"],
    }


@app.get("/api/trace/{case_id}")
def trace(case_id: str):
    """溯源面板：案例 → 命中规则 → 法规条款（含原文） → 官方类型 → 处罚事由"""
    case = demo_get_case(case_id)
    if not case:
        raise HTTPException(404, f"案例 {case_id} 不存在")
    conn = db()
    chain = []
    for tc in case["trace_chain"]:
        rule_info = None
        if tc["rule_id"]:
            r = conn.execute(
                "SELECT name, legal_desc, official_type_no, official_type_name, crime_code, crime_name, penalty_ref FROM rules WHERE rule_id=?",
                (tc["rule_id"],)).fetchone()
            rule_info = dict(r) if r else None
        clauses = []
        for lc in tc.get("legal_clauses", []):
            # 该条已作为"官方类型识别点"单独成层（下方 type_identify_content），
            # 不再重复渲染一遍 1500 字原文
            if (tc.get("type_clause_no") and lc.get("reg_code") == "PBOC_TYPE_TABLE"
                    and lc.get("clause_no") == tc["type_clause_no"]):
                continue
            c = conn.execute(
                "SELECT c.id, c.clause_no, c.content, c.chapter, r.name AS reg_name FROM clauses c "
                "JOIN regulations r ON r.id=c.regulation_id WHERE r.reg_code=? AND c.clause_no=?",
                (lc["reg_code"], lc["clause_no"])).fetchone()
            if c:
                clauses.append({"clause_id": c["id"], "reg_code": lc["reg_code"],
                                "reg_name": c["reg_name"], "clause_no": c["clause_no"],
                                "chapter": c["chapter"], "content": c["content"],
                                "note": lc.get("note", "")})
        # 官方类型对应的识别点原文
        type_clause = None
        type_note = ""
        if tc.get("type_clause_no"):
            c = conn.execute(
                "SELECT c.content FROM clauses c JOIN regulations r ON r.id=c.regulation_id "
                "WHERE r.reg_code='PBOC_TYPE_TABLE' AND c.clause_no=?",
                (tc["type_clause_no"],)).fetchone()
            type_clause = c["content"] if c else None
            if type_clause is None:
                # 不静默跳过：显式告知该类型无原文收录
                type_note = (f"法规库未收录「{tc['type_clause_no']}」的识别点原文"
                             f"（演示库仅收录官方对照表 12 类：类型1-1 ~ 类型12）")
        else:
            type_note = "本案例未归属官方对照表类型（非交易型或未定型案例，依据见上方法规条款）"
        chain.append({**tc, "rule_info": rule_info, "clauses": clauses,
                      "type_identify_content": type_clause, "type_note": type_note})
    conn.close()
    return {"case_id": case_id, "title": case["title"],
            "expected_conclusion": case["expected_conclusion"], "chain": chain}


@app.get("/api/clauses/{clause_id}")
def get_clause(clause_id: int):
    conn = db()
    row = conn.execute(
        "SELECT c.*, r.name AS reg_name, r.doc_number FROM clauses c "
        "JOIN regulations r ON r.id=c.regulation_id WHERE c.id=?", (clause_id,)).fetchone()
    conn.close()
    if not row:
        raise HTTPException(404, "条款不存在")
    return dict(row)


@app.get("/api/rules")
def list_rules():
    conn = db()
    rows = conn.execute(
        "SELECT rule_id, name, category, official_type_no, official_type_name, penalty_ref, "
        "legal_desc, params FROM rules ORDER BY rule_id"
    ).fetchall()
    conn.close()
    # executable 以后端规则注册表为准，前端不再硬编码清单
    return {"rules": [dict(r, executable=(r["rule_id"] in RULE_FUNCS)) for r in rows]}


@app.get("/api/screening")
def screening(q: str = ""):
    """名单筛查：命中不走 AI，先限制后核验。实现见 services/screening.py。"""
    try:
        return screen(q)
    except ValueError as e:
        raise HTTPException(400, str(e))


@app.get("/api/ctr")
def ctr():
    """大额交易报告：客观阈值逐日累计，实现见 services/ctr.py。"""
    return build_ctr()


@app.get("/api/regulations")
def list_regulations():
    conn = db()
    rows = conn.execute("""
        SELECT r.reg_code, r.name, r.issuer, r.doc_number, r.effective_date, r.source,
               COUNT(c.id) AS clause_count
        FROM regulations r LEFT JOIN clauses c ON c.regulation_id=r.id
        GROUP BY r.id ORDER BY r.id
    """).fetchall()
    conn.close()
    return {"regulations": [dict(r) for r in rows]}


# 前端静态文件（单文件应用）
@app.get("/")
def index():
    return FileResponse(os.path.join(FRONTEND_DIR, "index.html"),
                        headers={"Cache-Control": "no-store, max-age=0"})


if __name__ == "__main__":
    import uvicorn
    # 默认仅本机访问；公开演示时设 QINGYUAN_HOST=0.0.0.0，并务必同时开启只读模式
    uvicorn.run(app, host=os.getenv("QINGYUAN_HOST", "127.0.0.1"), port=PORT)
