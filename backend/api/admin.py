"""演示管理路由：重置运营数据。"""
from fastapi import APIRouter

from infra.db import get_db
from services import demo as svc

router = APIRouter(prefix="/api/admin", tags=["admin"])


@router.post("/reset-demo")
def reset_demo():
    conn = get_db()
    try:
        return svc.reset(conn)
    finally:
        conn.close()
