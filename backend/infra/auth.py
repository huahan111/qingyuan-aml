"""演示级登录鉴权（可选模式，QINGYUAN_AUTH=1 启用）。

- 账号来自 data/users.json：三角色（经办/复核/审批），口令仅存 SHA-256 摘要；
- 会话：HMAC-SHA256 签名 Cookie（qy_session，HttpOnly + SameSite=Lax，8 小时有效）；
  密钥取 QINGYUAN_SESSION_SECRET，未配置则进程内随机（重启失效，演示可接受）；
- 启用后：/api/*（health/login 豁免）未登录 401；写接口按角色校验
  （报送/定性/回填/接入=经办，演示重置=审批）；审计链操作人由"未鉴权"变为登录实名；
- 边界：演示级实现（单 worker、签名 Cookie）；生产须接机构统一身份认证（4A/AD）。
"""
import hashlib
import hmac
import json
import os
import secrets
import time
from base64 import urlsafe_b64encode, urlsafe_b64decode
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException, Request

COOKIE_NAME = "qy_session"
SESSION_TTL = 8 * 3600
# 免登录路径：健康检查、登录、登出与会话查询（me 仅返回当前状态，无敏感数据）
EXEMPT_PREFIXES = ("/api/health", "/api/auth/login", "/api/auth/logout", "/api/auth/me")
_TRUE = {"1", "true", "yes", "on"}
_TZ = timezone(timedelta(hours=8))

_process_secret = secrets.token_hex(32)
_users_cache = None


def is_auth_enabled() -> bool:
    return os.getenv("QINGYUAN_AUTH", "0").strip().lower() in _TRUE


def _secret() -> str:
    return os.getenv("QINGYUAN_SESSION_SECRET", "") or _process_secret


def _load_users():
    global _users_cache
    if _users_cache is None:
        path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                            "..", "data", "users.json")
        with open(path, encoding="utf-8") as f:
            _users_cache = json.load(f).get("users", [])
    return _users_cache


def _public(user: dict) -> dict:
    return {k: user[k] for k in ("username", "name", "id", "post", "role", "role_name")}


def verify_credentials(username: str, password: str):
    """校验口令（恒定时间比较）。通过返回脱敏用户信息，否则 None。"""
    digest = hashlib.sha256((password or "").encode("utf-8")).hexdigest()
    for user in _load_users():
        if hmac.compare_digest(user["username"], username or ""):
            if hmac.compare_digest(user["password_sha256"], digest):
                return _public(user)
            return None
    return None


def issue_token(user: dict):
    """签发会话令牌：base64url(payload).hmac，返回 (token, 过期时间戳)。"""
    exp = int(time.time()) + SESSION_TTL
    payload = json.dumps({"u": user["username"], "r": user["role"],
                          "n": user["name"], "i": user["id"], "p": user["post"],
                          "rn": user["role_name"], "e": exp},
                         ensure_ascii=False, separators=(",", ":"))
    body = urlsafe_b64encode(payload.encode("utf-8")).decode("ascii")
    sig = hmac.new(_secret().encode(), body.encode(), hashlib.sha256).hexdigest()
    return f"{body}.{sig}", exp


def parse_token(token: str):
    """校验签名与有效期；通过返回用户信息 dict，否则 None。"""
    if not token or "." not in token:
        return None
    body, _, sig = token.rpartition(".")
    expect = hmac.new(_secret().encode(), body.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expect, sig or ""):
        return None
    try:
        payload = json.loads(urlsafe_b64decode(body.encode("ascii")).decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        return None
    if not isinstance(payload, dict) or payload.get("e", 0) < time.time():
        return None
    return {"username": payload["u"], "role": payload["r"], "name": payload["n"],
            "id": payload["i"], "post": payload["p"], "role_name": payload["rn"]}


def get_user(request: Request):
    """从 Cookie 解析当前登录用户；未登录/无效返回 None。"""
    return parse_token(request.cookies.get(COOKIE_NAME, ""))


def require_role(*roles):
    """写接口角色依赖：鉴权关闭时直通；开启后未登录 401、角色不符 403。"""
    role_names = {"operator": "经办", "reviewer": "复核", "approver": "审批"}

    def dependency(request: Request):
        if not is_auth_enabled():
            return None
        user = get_user(request)
        if not user:
            raise HTTPException(401, "未登录或会话已过期，请先登录")
        if roles and user["role"] not in roles:
            need = "、".join(role_names.get(r, r) for r in roles)
            raise HTTPException(403, f"该操作需要「{need}」角色，当前登录：{user['name']}（{user['role_name']}）")
        return user
    return dependency


def actor_label(request: Request, fallback: str = "演示用户（未鉴权）") -> str:
    """审计链操作人：登录态实名（姓名+工号），未鉴权时如实标注。"""
    user = get_user(request)
    return f"{user['name']}（{user['id']}）" if user else fallback


def session_header_exp(exp: int) -> str:
    return datetime.fromtimestamp(exp, _TZ).strftime("%Y-%m-%d %H:%M:%S")
