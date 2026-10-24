"""案例库与规则库联动路由：覆盖矩阵、规则有效性、案例库、反哺回填。"""
from fastapi import APIRouter

from infra import audit as audit_chain
from infra.db import get_db
from services import case_linkage as svc

router = APIRouter(prefix="/api", tags=["linkage"])


@router.get("/linkage/coverage")
def coverage():
    conn = get_db()
    try:
        return svc.coverage(conn)
    finally:
        conn.close()


@router.get("/linkage/effectiveness")
def effectiveness():
    conn = get_db()
    try:
        return svc.effectiveness(conn)
    finally:
        conn.close()


@router.get("/case-library")
def case_library():
    conn = get_db()
    try:
        return svc.library_summary(conn)
    finally:
        conn.close()


@router.post("/linkage/backfill")
def backfill():
    conn = get_db()
    try:
        result = svc.backfill(conn)
        audit_chain.record(
            conn, actor="演示操作员", action="历史报送回填",
            object_type="case_library", object_id="backfill",
            detail={"submissions": result.get("submissions", 0),
                    "promoted": result.get("promoted", 0)})
        return result
    finally:
        conn.close()
