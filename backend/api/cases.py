"""案例相关路由：相似案例召回、新交易接入、人工结论沉淀。"""
from fastapi import APIRouter, Body, HTTPException, Query

from case_store import get_case
from infra.db import get_db
from services.case_linkage import record_disposition
from services.intake import IntakeValidationError, screen_new_case
from services.similar_cases import similar_for_case

router = APIRouter(prefix="/api", tags=["cases"])


@router.get("/similar-cases/{case_id}")
def similar_cases(case_id: str, top_k: int = Query(3, ge=1, le=10)):
    case = get_case(case_id)
    if not case:
        raise HTTPException(404, f"案例 {case_id} 不存在")
    conn = get_db()
    try:
        return similar_for_case(case, conn, top_k)
    finally:
        conn.close()


@router.post("/intake")
def intake(payload: dict = Body(...)):
    conn = get_db()
    try:
        return screen_new_case(payload, conn)
    except IntakeValidationError as e:
        raise HTTPException(422, str(e))
    finally:
        conn.close()


@router.post("/case-library/disposition")
def disposition(payload: dict = Body(...)):
    case_id = payload.get("case_id")
    if not case_id:
        raise HTTPException(422, "缺少 case_id")
    case = get_case(case_id)
    if not case:
        raise HTTPException(404, f"案例 {case_id} 不存在")
    conn = get_db()
    try:
        return record_disposition(
            conn, case, payload.get("conclusion", "放行"),
            payload.get("reason", ""), payload.get("operator", ""))
    except ValueError as e:
        raise HTTPException(422, str(e))
    finally:
        conn.close()
