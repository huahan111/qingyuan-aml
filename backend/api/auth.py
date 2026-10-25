"""登录鉴权路由：登录 / 登出 / 当前会话。实现见 infra/auth.py。"""
from fastapi import APIRouter, Body, HTTPException, Request, Response

from infra import auth

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/login")
def login(payload: dict = Body(...), response: Response = None):
    username = str(payload.get("username") or "").strip()
    password = str(payload.get("password") or "")
    user = auth.verify_credentials(username, password)
    if not user:
        raise HTTPException(401, "用户名或口令错误")
    token, exp = auth.issue_token(user)
    response.set_cookie(auth.COOKIE_NAME, token, max_age=auth.SESSION_TTL,
                        httponly=True, samesite="lax")
    return {"user": user, "expires_at": auth.session_header_exp(exp),
            "auth_required": True}


@router.post("/logout")
def logout(request: Request, response: Response = None):
    if request.cookies.get(auth.COOKIE_NAME):
        response.delete_cookie(auth.COOKIE_NAME)
    return {"ok": True}


@router.get("/me")
def me(request: Request):
    user = auth.get_user(request)
    return {"auth_required": auth.is_auth_enabled(), "user": user,
            "demo_hint": auth.demo_hint() if auth.is_auth_enabled() and not user else ""}
