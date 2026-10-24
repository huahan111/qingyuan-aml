"""CDD 尽职调查接口：对公工商尽调 / 个人身份核验。

只做查询，不落库、不存储证件号；未配置外部数据源时如实返回"未接入"，
不会用模拟结果冒充真实核查。
"""
from fastapi import APIRouter, HTTPException

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
def cdd_enterprise(payload: dict):
    name = str(payload.get("name") or "").strip()
    uscc = str(payload.get("uscc") or "").strip()
    provider = str(payload.get("provider") or "mock-enterprise")
    if not name and not uscc:
        raise HTTPException(422, "企业名称或统一社会信用代码至少填一项")
    try:
        return cdd.lookup_enterprise(name, uscc, provider)
    except cdd.CddError as e:
        raise HTTPException(422, str(e))


@router.post("/api/cdd/personal")
def cdd_personal(payload: dict):
    name = str(payload.get("name") or "").strip()
    id_no = str(payload.get("id_no") or "").strip()
    id_expiry = str(payload.get("id_expiry") or "").strip()
    provider = str(payload.get("provider") or "mock-identity")
    try:
        return cdd.verify_identity(name, id_no, id_expiry, provider)
    except cdd.CddError as e:
        raise HTTPException(422, str(e))
