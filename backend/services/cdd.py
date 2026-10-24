"""客户尽职调查（CDD）服务：对公工商尽调 + 个人身份核验。

设计原则（与 AI Provider 一致）：
1. Provider 抽象：Mock 离线可用；真实数据源需显式配置，未配置时 available()=False，
   绝不静默发起网络请求，也绝不编造"已核查"的结论。
2. 结果里每一项都标注来源（mock / 外部数据源 / 人工核验），页面照原样展示。
3. 个人身份核验在真实机构里走两条路：
   - 人行"联网核查公民身份信息系统"：仅对银行业金融机构开放，由机构前置系统对接，不是公开 API；
   - 商用二要素/三要素核验（腾讯云、阿里云等）：按次计费，需实名与场景报备。
   本项目两者都未接入，页面会明确写"未接入，仅做格式与规则校验"。
"""
import hashlib
import os
import re
from datetime import date

# ===== 模拟企业工商库（合成数据，仅用于演示）=====
MOCK_ENTERPRISES = {
    "ZZ供应链有限公司": {
        "uscc": "91310104MA1FL2XK72",
        "legal_rep": "陈某某",
        "reg_capital": "500 万元人民币",
        "established": "2025-11-18",
        "status": "存续（在营）",
        "address": "上海市徐汇区某路 88 号 3 层（集群注册地址）",
        "industry": "批发和零售业 / 供应链管理",
        "scope": "供应链管理服务；日用百货、建材、五金交电销售；国内货物运输代理。",
        "shareholders": [{"name": "陈某某", "ratio": "100%", "type": "自然人"}],
        "risk_tags": ["成立不满 1 年", "集群注册地址", "无社保缴纳记录（模拟）", "一般纳税人资格未核实"],
        "conclusion": "高风险",
        "suggestion": "建议 EDD：核实实际经营场所、社保与工资发放、上下游合同与发票；开户/提额从严。",
    },
    "清源建材贸易有限公司": {
        "uscc": "91310115MA1H8YQ238",
        "legal_rep": "王某某",
        "reg_capital": "1000 万元人民币",
        "established": "2016-03-09",
        "status": "存续（在营）",
        "address": "上海市浦东新区某路 1000 号 A 座 12 层",
        "industry": "批发和零售业 / 建材批发",
        "scope": "建筑材料、装饰材料、金属材料销售；货物进出口。",
        "shareholders": [{"name": "王某某", "ratio": "70%", "type": "自然人"},
                         {"name": "上海某某投资合伙企业（有限合伙）", "ratio": "30%", "type": "机构"}],
        "risk_tags": ["经营满 10 年", "社保参保人数正常（模拟）", "无行政处罚记录（模拟）"],
        "conclusion": "低风险",
        "suggestion": "常规尽调即可；按年复核工商变更与受益所有人。",
    },
    "XX贸易有限公司": {
        "uscc": "91310112MA1GC0P453",
        "legal_rep": "李某某",
        "reg_capital": "100 万元人民币",
        "established": "2023-06-21",
        "status": "经营异常（通过登记的住所无法联系）",
        "address": "上海市闵行区某路 5 号 2 层（已列入异常）",
        "industry": "批发和零售业 / 贸易经纪与代理",
        "scope": "国内贸易代理；货物进出口；技术进出口。",
        "shareholders": [{"name": "李某某", "ratio": "100%", "type": "自然人"}],
        "risk_tags": ["经营异常名录", "注册地址无法联系", "成立 3 年内", "无对外投资信息"],
        "conclusion": "高风险",
        "suggestion": "不得新增业务关系；存量业务核实受益所有人，必要时提交可疑交易报告。",
    },
}

# 模拟"联网核查"结果库：仅演示，真实环境必须接人行系统或持牌核验服务
# （号码为按 GB 11643 校验位算法构造的合成号，不对应任何真实自然人）
MOCK_IDENTITY = {
    ("赵某", "999999199303125513"): {"match": True, "note": "姓名与证件号一致（模拟）"},
    ("张某", "999999198801017780"): {"match": True, "note": "姓名与证件号一致（模拟）"},
}

ID_WEIGHTS = (7, 9, 10, 5, 8, 4, 2, 1, 6, 3, 7, 9, 10, 5, 8, 4, 2)
ID_CHECK = "10X98765432"

# GB 32100-2015 统一社会信用代码：31 字符集（不含 I/O/S/V/Z）与 17 位权重
_USCC_CHARS = "0123456789ABCDEFGHJKLMNPQRTUWXY"
_USCC_WEIGHTS = (1, 3, 9, 27, 19, 26, 16, 17, 20, 29, 25, 13, 8, 24, 10, 30, 28)


class CddError(Exception):
    pass


def _strip_suffix(name: str) -> str:
    return re.sub(r"（(对公|个人|演示)）$", "", (name or "").strip())


def verify_id_checksum(id_no: str) -> bool:
    """GB 11643 身份证号校验位（真实算法，不是编的）。"""
    if not re.fullmatch(r"\d{17}[\dXx]", id_no or ""):
        return False
    total = sum(int(id_no[i]) * ID_WEIGHTS[i] for i in range(17))
    return ID_CHECK[total % 11] == id_no[17].upper()


def verify_uscc(uscc: str) -> bool:
    """GB 32100-2015 统一社会信用代码校验位（真实算法）。

    第 18 位 = 字符集[(31 - Σ(字符值×权重) mod 31) mod 31]，
    模拟企业的信用代码均按此算法构造，可现场验算。
    """
    u = (uscc or "").strip().upper()
    if len(u) != 18:
        return False
    try:
        total = sum(_USCC_CHARS.index(u[i]) * _USCC_WEIGHTS[i] for i in range(17))
    except ValueError:
        return False
    return _USCC_CHARS[(31 - total % 31) % 31] == u[17]


def _mask_id(id_no: str) -> str:
    return id_no[:4] + "*" * 10 + id_no[-4:] if len(id_no) >= 18 else "—"


class CddProvider:
    """Provider 基类：真实数据源继承它，未配置时 available() 返回 False。"""

    id = "base"
    name = "未命名数据源"
    kind = "enterprise"  # enterprise | individual

    def available(self) -> bool:
        return False

    def note(self) -> str:
        return ""

    def lookup_enterprise(self, name: str, uscc: str = "") -> dict:
        raise CddError(f"{self.name} 未接入")

    def verify_identity(self, name: str, id_no: str, id_expiry: str = "") -> dict:
        raise CddError(f"{self.name} 未接入")


class MockEnterpriseProvider(CddProvider):
    id = "mock-enterprise"
    name = "内置模拟工商库（3 家合成企业）"
    kind = "enterprise"

    def available(self) -> bool:
        return True

    def note(self) -> str:
        return "离线合成数据，不指向任何真实企业；接入企查查/天眼查后替换本 Provider"

    def lookup_enterprise(self, name: str, uscc: str = "") -> dict:
        key = _strip_suffix(name)
        uscc = (uscc or "").strip().upper()
        if not key and not uscc:
            raise CddError("企业名称不能为空")
        data = MOCK_ENTERPRISES.get(key)
        if not data and uscc:
            # 名称未命中时按统一社会信用代码反查
            data = next((d for d in MOCK_ENTERPRISES.values() if d.get("uscc") == uscc), None)
        if not data:
            query = key or uscc
            return {"found": False, "query": query, "provider": self.id,
                    "notice": "模拟库中无此企业；真实环境应由企查查/天眼查返回工商照面与风险信息",
                    "checks": [] if not uscc else [
                        {"item": "统一社会信用代码校验位（GB 32100）",
                         "result": "通过" if verify_uscc(uscc) else "不通过（号码可能录错）",
                         "ok": verify_uscc(uscc)}]}
        checks = [
            {"item": "工商登记状态", "result": data["status"],
             "ok": "存续" in data["status"]},
            {"item": "成立年限", "result": data["established"],
             "ok": _years_since(data["established"]) >= 1},
            {"item": "受益所有人", "result": "；".join(
                f"{s['name']} {s['ratio']}" for s in data["shareholders"]), "ok": True},
            {"item": "风险标签", "result": "、".join(data["risk_tags"]),
             "ok": not any(t in ("经营异常名录", "注册地址无法联系") for t in data["risk_tags"])},
        ]
        if uscc:
            ok_uscc = verify_uscc(uscc)
            checks.insert(0, {"item": "统一社会信用代码校验位（GB 32100）",
                              "result": "通过" if ok_uscc else "不通过（号码可能录错）",
                              "ok": ok_uscc})
            match = uscc == data["uscc"]
            checks.append({"item": "名称与信用代码一致性",
                           "result": "一致" if match else f"不一致（该名称对应 {data['uscc']}）",
                           "ok": match})
        return {"found": True, "query": key or data["uscc"], "provider": self.id,
                "source": "内置模拟工商库（合成数据）", **data,
                "checks": checks}


class QccEnterpriseProvider(CddProvider):
    """企查查开放平台接入位（需 QCC_API_KEY）。

    按企查查开放平台的计费方式（按次计费，基础工商约 1 元/次、综合风险接口最高约 6 元/次），
    这里只保留接入位与请求参数约定，不实现真实调用：没有 key 时 available()=False，
    页面会显示"未配置"，避免出现"看起来查了、其实是假的"。
    """

    id = "qcc"
    name = "企查查开放平台（需 API Key）"
    kind = "enterprise"

    def __init__(self):
        self.api_key = os.environ.get("QCC_API_KEY", "").strip()

    def available(self) -> bool:
        return bool(self.api_key)

    def note(self) -> str:
        return ("按次计费（基础工商约 1 元/次、综合风险约 6 元/次），需在开放平台申请 Key 并报备场景；"
                "接入后由本 Provider 替换内置模拟库")

    def lookup_enterprise(self, name: str, uscc: str = "") -> dict:
        raise CddError("企查查接口尚未实现：请在此处按官方文档实现签名与请求"
                       "（本项目只预留接入位，不做未经验证的调用）")


class MockIdentityProvider(CddProvider):
    id = "mock-identity"
    name = "内置模拟核验（格式校验 + 模拟联网核查）"
    kind = "individual"

    def available(self) -> bool:
        return True

    def note(self) -> str:
        return ("真实环境请接：①人行联网核查公民身份信息系统（仅银行业金融机构，走机构前置系统）；"
                "②持牌商用二/三要素核验（按次计费）。本演示只做格式与规则校验。")

    def verify_identity(self, name: str, id_no: str, id_expiry: str = "") -> dict:
        name = (name or "").strip()
        id_no = (id_no or "").strip().upper()
        if not name:
            raise CddError("姓名不能为空")
        if not re.fullmatch(r"\d{17}[\dX]", id_no):
            raise CddError("身份证号应为 18 位（末位可为 X）")
        checks = []
        ok_format = verify_id_checksum(id_no)
        checks.append({"item": "证件号校验位（GB 11643）",
                       "result": "通过" if ok_format else "不通过（号码可能录错）", "ok": ok_format})
        birth = f"{id_no[6:10]}-{id_no[10:12]}-{id_no[12:14]}"
        checks.append({"item": "出生日期", "result": birth, "ok": True})
        expired = False
        if id_expiry:
            try:
                y, m, d = [int(x) for x in id_expiry.replace("/", "-").split("-")]
                expired = date(y, m, d) < date.today()
                checks.append({"item": "证件有效期", "result": f"{id_expiry}（{'已过期' if expired else '有效'}）",
                               "ok": not expired})
            except (ValueError, TypeError):
                checks.append({"item": "证件有效期", "result": "格式应为 YYYY-MM-DD", "ok": False})
        hit = MOCK_IDENTITY.get((name, id_no))
        if hit:
            checks.append({"item": "联网核查（模拟）", "result": hit["note"], "ok": hit["match"]})
        else:
            checks.append({"item": "联网核查（模拟）", "result": "演示库无此组合，无法核实（真实环境应返回一致/不一致）",
                           "ok": False})
        ok = all(c["ok"] for c in checks)
        return {"found": True, "query": name, "provider": self.id,
                "source": "内置模拟核验（未接入人行联网核查）",
                "id_masked": _mask_id(id_no),
                "verified": ok,
                "conclusion": "核验通过" if ok else "需人工核实",
                "checks": checks,
                "notice": "演示环境不存储证件号，也不调用任何外部核验接口"}


def _years_since(iso: str) -> float:
    try:
        y, m, d = [int(x) for x in iso.split("-")]
        return (date.today() - date(y, m, d)).days / 365.25
    except (ValueError, AttributeError):
        return 0


ENTERPRISE_PROVIDERS = (MockEnterpriseProvider(), QccEnterpriseProvider())
IDENTITY_PROVIDERS = (MockIdentityProvider(),)


def enterprise_providers_info():
    return [{"id": p.id, "name": p.name, "available": p.available(), "note": p.note()}
            for p in ENTERPRISE_PROVIDERS]


def identity_providers_info():
    return [{"id": p.id, "name": p.name, "available": p.available(), "note": p.note()}
            for p in IDENTITY_PROVIDERS]


def lookup_enterprise(name: str, uscc: str = "", provider_id: str = "mock-enterprise") -> dict:
    for p in ENTERPRISE_PROVIDERS:
        if p.id == provider_id:
            if not p.available():
                raise CddError(f"{p.name} 未配置，无法查询")
            return p.lookup_enterprise(name, uscc)
    raise CddError(f"未知数据源：{provider_id}")


def verify_identity(name: str, id_no: str, id_expiry: str = "", provider_id: str = "mock-identity") -> dict:
    for p in IDENTITY_PROVIDERS:
        if p.id == provider_id:
            if not p.available():
                raise CddError(f"{p.name} 未配置，无法核验")
            return p.verify_identity(name, id_no, id_expiry)
    raise CddError(f"未知核验渠道：{provider_id}")
