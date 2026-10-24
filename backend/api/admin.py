"""演示管理路由：重置运营数据。"""
from fastapi import APIRouter

from infra import audit as audit_chain
from infra.db import get_db
from services import demo as svc

router = APIRouter(prefix="/api/admin", tags=["admin"])


@router.post("/reset-demo")
def reset_demo():
    conn = get_db()
    try:
        result = svc.reset(conn)
        # 重置动作本身留痕：审计链不随业务数据清空，事后可查"谁在何时重置过"
        audit_chain.record(
            conn, actor="演示操作员", action="演示重置",
            object_type="admin", object_id="reset-demo",
            detail={"cleared_submissions": result.get("submissions", 0),
                    "cleared_library_cases": result.get("library_cases", 0)})
        return result
    finally:
        conn.close()
