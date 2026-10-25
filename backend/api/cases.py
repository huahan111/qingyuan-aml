"""案例相关路由：相似案例召回、新交易接入、人工结论沉淀。"""
from fastapi import APIRouter, Body, Depends, HTTPException, Query, Request

from case_store import get_case
from infra import audit as audit_chain
from infra import auth
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
def intake(payload: dict = Body(...), user=Depends(auth.require_role("operator"))):
    conn = get_db()
    try:
        return screen_new_case(payload, conn)
    except IntakeValidationError as e:
        raise HTTPException(422, str(e))
    finally:
        conn.close()


@router.post("/case-library/disposition")
def disposition(payload: dict = Body(...), request: Request = None,
                user=Depends(auth.require_role("operator"))):
    case_id = payload.get("case_id")
    if not case_id:
        raise HTTPException(422, "缺少 case_id")
    case = get_case(case_id)
    if not case:
        raise HTTPException(404, f"案例 {case_id} 不存在")
    conn = get_db()
    try:
        result = record_disposition(
            conn, case, payload.get("conclusion", "放行"),
            payload.get("reason", ""), payload.get("operator", ""))
        audit_chain.record(
            conn, actor=auth.actor_label(request, payload.get("operator") or "未署名"),
            action="人工定性",
            object_type="library_case", object_id=result.get("library_case_id", case_id),
            detail={"case_id": case_id, "conclusion": payload.get("conclusion", ""),
                    "reason": (payload.get("reason") or "")[:200]})
        return result
    except ValueError as e:
        raise HTTPException(422, str(e))
    finally:
        conn.close()
