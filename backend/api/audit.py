"""审计链路由：检索（GET /api/audit）与全链完整性校验（GET /api/audit/verify）。

只读演示模式下同样可用（GET 天然放行）——公开部署的访客可以自行校验审计链，
但无法追加或改动记录（只读模式下不记录新审计，触发器拒绝 UPDATE/DELETE）。
"""
from fastapi import APIRouter, HTTPException, Query

from infra import audit
from infra.db import get_db

router = APIRouter(prefix="/api/audit", tags=["audit"])


@router.get("")
def query_audit(
    actor: str = Query("", max_length=80),
    action: str = Query("", max_length=60),
    object_type: str = Query("", max_length=40),
    object_id: str = Query("", max_length=120),
    date_from: str | None = Query(None, pattern=r"^\d{4}-\d{2}-\d{2}$"),
    date_to: str | None = Query(None, pattern=r"^\d{4}-\d{2}-\d{2}$"),
    limit: int = Query(50, ge=1, le=audit.MAX_LIMIT),
    offset: int = Query(0, ge=0),
):
    conn = get_db()
    try:
        return audit.query(conn, actor=actor, action=action, object_type=object_type,
                           object_id=object_id, date_from=date_from or "",
                           date_to=date_to or "", limit=limit, offset=offset)
    except ValueError as e:
        raise HTTPException(422, str(e))
    finally:
        conn.close()


@router.get("/verify")
def verify_audit():
    conn = get_db()
    try:
        return audit.verify(conn)
    finally:
        conn.close()
