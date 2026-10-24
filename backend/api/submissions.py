"""上报台账 API 路由：只做参数、响应与异常映射。"""
import logging

from fastapi import APIRouter, Body, HTTPException

from infra import audit as audit_chain
from infra.db import get_db
from services import submissions as svc
from services.case_linkage import promote_submission

router = APIRouter(prefix="/api", tags=["submissions"])
log = logging.getLogger("qingyuan.submissions")


@router.post("/submissions")
def create_submission(payload: dict = Body(...)):
    conn = get_db()
    try:
        result = svc.create(conn, payload)
        # 审计链留痕：报送写入/更正报送（幂等重复提交不重复记链）
        if result.pop("created", False):
            action = "更正报送" if payload.get("supersedes_receipt") else "报送写入"
            audit_chain.record(
                conn, actor=payload.get("operator") or "未署名", action=action,
                object_type="submission", object_id=result["receipt_no"],
                detail={"report_no": payload.get("report_no", ""),
                        "case_id": payload.get("case_id", ""),
                        "version": payload.get("version", 1),
                        "status": payload.get("status", "已报送"),
                        "supersedes_receipt": payload.get("supersedes_receipt", "")})
        try:
            promote_submission(conn, result["id"])
        except Exception:
            log.exception("案例库反哺失败，不影响报送记录")
        return result
    except svc.SubmissionValidationError as e:
        raise HTTPException(422, str(e))
    except svc.SubmissionConflictError as e:
        raise HTTPException(409, str(e))
    finally:
        conn.close()


@router.get("/submissions")
def list_submissions():
    conn = get_db()
    try:
        return svc.list_all(conn)
    finally:
        conn.close()


@router.get("/submissions/{sid}")
def get_submission(sid: int):
    conn = get_db()
    try:
        return svc.get(conn, sid)
    except svc.SubmissionNotFoundError as e:
        raise HTTPException(404, str(e))
    finally:
        conn.close()
