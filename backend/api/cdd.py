"""CDD 尽职调查接口：对公工商尽调 / 个人身份核验。

只做查询，不落库、不存储证件号；未配置外部数据源时如实返回"未接入"，
不会用模拟结果冒充真实核查。查询行为写入审计链（证件号只记掩码）。
"""
from fastapi import APIRouter, HTTPException, Request

from infra import audit as audit_chain
from infra import auth
from infra.db import get_db
from services import cdd

router = APIRouter()


@router.get("/api/cdd/info")
def cdd_info():
    return {
        "enterprise_providers": cdd.enterprise_providers_info(),
        "identity_providers": cdd.identity_providers_info(),
        "paths": {
            "enterprise": "对公：工商照面 + 股东/受益所有人 + 风险标签（企查查/天眼查开放平台，按次计费）",
            "individual": "个人：人行联网核查公民身份信息系统（仅银行业金融机构，走机构前置系统）"
                          "或持牌商用二/三要素核验（按次计费）",
        },
    }


@router.post("/api/cdd/enterprise")
def cdd_enterprise(payload: dict, request: Request = None):
    name = str(payload.get("name") or "").strip()
    uscc = str(payload.get("uscc") or "").strip()
    provider = str(payload.get("provider") or "mock-enterprise")
    if not name and not uscc:
        raise HTTPException(422, "企业名称或统一社会信用代码至少填一项")
    try:
        result = cdd.lookup_enterprise(name, uscc, provider)
    except cdd.CddError as e:
        raise HTTPException(422, str(e))
    conn = get_db()
    try:
        audit_chain.record(
            conn, actor=auth.actor_label(request), action="CDD对公尽调",
            object_type="cdd_enterprise", object_id=(name or uscc)[:80],
            detail={"provider": provider, "found": result.get("found", False),
                    "uscc": uscc[:18]})
    finally:
        conn.close()
    return result


@router.post("/api/cdd/personal")
def cdd_personal(payload: dict, request: Request = None):
    name = str(payload.get("name") or "").strip()
    id_no = str(payload.get("id_no") or "").strip()
    id_expiry = str(payload.get("id_expiry") or "").strip()
    provider = str(payload.get("provider") or "mock-identity")
    try:
        result = cdd.verify_identity(name, id_no, id_expiry, provider)
    except cdd.CddError as e:
        raise HTTPException(422, str(e))
    conn = get_db()
    try:
        # 隐私红线：审计只记姓名与证件号掩码，绝不落完整证件号
        audit_chain.record(
            conn, actor=auth.actor_label(request), action="CDD身份核验",
            object_type="cdd_personal", object_id=name[:80],
            detail={"provider": provider,
                    "id_masked": result.get("id_masked", ""),
                    "verified": result.get("verified", False)})
    finally:
        conn.close()
    return result
