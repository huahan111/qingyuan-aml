"""可疑交易报告（STR）生成 API 路由。"""
from fastapi import APIRouter, Body, HTTPException

from ai_diagnosis import get_provider
from case_store import get_case
from infra.db import get_db
from domain.report.builder import build_report
from domain.rules import run_engine

router = APIRouter(prefix="/api", tags=["reports"])

# 客户端传入 diagnosis 时的结构白名单：结论走枚举、分析要点限量限长。
# 不接受"任意文本直出报告"——调用方可以带研判结论，但不能夹带未定义结构。
_CONCLUSIONS = ("放行", "拦截", "人工复核")
_RISK_LEVELS = ("高", "中", "低")
_MAX_POINTS, _MAX_LEN = 20, 500


def _validate_diagnosis(diagnosis):
    if not isinstance(diagnosis, dict):
        raise HTTPException(422, "diagnosis 必须是对象")
    if diagnosis.get("conclusion") not in _CONCLUSIONS:
        raise HTTPException(422, "diagnosis.conclusion 必须是 放行 / 拦截 / 人工复核")
    risk = diagnosis.get("risk_level", "中")
    if risk not in _RISK_LEVELS:
        raise HTTPException(422, "diagnosis.risk_level 必须是 高 / 中 / 低")
    points = diagnosis.get("analysis_points", [])
    if not isinstance(points, list) or len(points) > _MAX_POINTS:
        raise HTTPException(422, f"diagnosis.analysis_points 应为不超过 {_MAX_POINTS} 项的数组")
    if any(not isinstance(p, str) or len(p) > _MAX_LEN for p in points):
        raise HTTPException(422, f"diagnosis.analysis_points 每项应为不超过 {_MAX_LEN} 字的文本")
    materials = diagnosis.get("materials_to_check", [])
    if not isinstance(materials, list) or any(not isinstance(m, str) or len(m) > _MAX_LEN
                                              for m in materials):
        raise HTTPException(422, "diagnosis.materials_to_check 应为文本数组")
    for key in ("official_type_no", "official_type_name", "elimination", "suggestion"):
        if key in diagnosis and not isinstance(diagnosis[key], str):
            raise HTTPException(422, f"diagnosis.{key} 应为文本")
    return diagnosis


@router.post("/report/{case_id}")
def build_str(case_id: str, payload: dict | None = Body(default=None)):
    """生成 STR 初稿：62 项官方要素 + 中英双语正文。"""
    case = get_case(case_id)
    if not case:
        raise HTTPException(404, f"案例 {case_id} 不存在")
    conn = get_db()
    try:
        rule_hits = run_engine(case["transactions"], case["customer_info"], conn)
        diagnosis = (payload or {}).get("diagnosis")
        if diagnosis:
            diagnosis = _validate_diagnosis(diagnosis)
        else:
            provider = get_provider()
            if not (hasattr(provider, "available") and provider.available(case_id)):
                raise HTTPException(503, f"AI Provider 不可用（case={case_id}）")
            diagnosis = provider.diagnose(case_id, case, rule_hits)
        return build_report(case, diagnosis, rule_hits, conn)
    finally:
        conn.close()
