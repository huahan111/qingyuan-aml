"""上报台账 API 路由：只做参数、响应与异常映射。"""
import logging

from fastapi import APIRouter, Body, HTTPException

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
