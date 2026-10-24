"""清源MVP AI诊断层：Mock/Live 双 Provider。
- MockProvider：读取预生成并人工校验的诊断 JSON（内置案例，演示稳定，零 token）
- LiveProvider：OpenAI 兼容格式调真实大模型（自定义案例或插 key 后启用）
输出结构与差异表版 prompt 约定一致。

Provider 接口约定（两个 Provider 必须同签名，调用方不区分类型）：
- available(case_id=None) -> bool
- diagnose(case_id, case_data, rule_hits) -> dict
"""
import os
import json
import urllib.request

MOCK_DIR = os.path.join(os.path.dirname(__file__), "data", "mock_diagnosis")

# 官方可疑交易类型清单：与法规库 PBOC_TYPE_TABLE 收录的《可疑交易类型和识别点对照表
# （银行业参考版）》逐条对齐——该表共 12 类、13 个编号条目（类型1-1、1-2、2～12）。
# 注意：对照表原文没有"类型13/14"，早期演示数据里的"官方第13/14/15/16类"是行内归纳
# 维度，不是官方类型；Live prompt 已按官方 12 类 + "无法归类"出口组织。
OFFICIAL_TYPES = [
    "类型1-1 疑似非法汇兑型地下钱庄", "类型1-2 疑似非法结算型地下钱庄",
    "类型2 疑似腐败", "类型3 疑似毒品犯罪", "类型4 疑似走私",
    "类型5 疑似诈骗", "类型6 疑似集资", "类型7 疑似传销",
    "类型8 疑似套现", "类型9 疑似涉税犯罪", "类型10 疑似恐怖融资",
    "类型11 疑似赌博", "类型12 疑似虚假出资、抽逃出资",
]

PROMPT_TEMPLATE = """你是银行反洗钱监测岗的智能研判助手。请基于以下信息完成可疑交易研判。

【客户信息】
{customer}

【交易序列】
{transactions}

【规则引擎命中特征】
{rule_hits}

【官方可疑交易类型清单】（结论必须引用编号；均不符合时输出"无法归类"）
{official_types}

【硬性约束】
1. 输出结论三选一：放行 / 拦截（提交可疑交易报告）/ 人工复核
2. 疑似类型只能从上方官方清单选择，禁止自创类型
3. 引用法规仅限：《反洗钱法》(2025施行)、人民银行令〔2016〕第3号、〔2025〕第11号令、《可疑交易类型和识别点对照表》，禁止编造条文
4. 逐项列出可疑特征点，并说明每个特征对应的官方类型识别点
5. 如证据不足但存在疑点，输出"人工复核"并列明需补充核验的材料清单

【输出格式】（JSON）
{{
  "conclusion": "放行|拦截|人工复核",
  "official_type_no": "官方第X类 或 空",
  "official_type_name": "类型名称 或 空",
  "risk_level": "高|中|低",
  "analysis_points": ["可疑特征点1（对应识别点）", "..."],
  "elimination": "排除理由（放行时必填，否则为空字符串）",
  "materials_to_check": ["需补充核验材料（人工复核时必填）"],
  "suggestion": "处置建议（一句话）"
}}"""


class MockProvider:
    """预生成诊断：演示内置案例走这里，确定性输出、零 token"""
    name = "mock-prebuilt"

    def available(self, case_id=None):
        return os.path.exists(os.path.join(MOCK_DIR, f"{case_id}.json"))

    def diagnose(self, case_id, case_data, rule_hits):
        path = os.path.join(MOCK_DIR, f"{case_id}.json")
        if not os.path.exists(path):
            raise FileNotFoundError(f"案例 {case_id} 无预生成诊断")
        with open(path, encoding="utf-8") as f:
            return json.load(f)


class LiveProvider:
    """真实大模型调用：OpenAI 兼容格式（DeepSeek 等），环境变量配置"""
    name = "live"

    def __init__(self):
        self.api_key = os.environ.get("OPENAI_API_KEY", "")
        self.base_url = os.environ.get("OPENAI_BASE_URL", "https://api.deepseek.com/v1")
        self.model = os.environ.get("AML_MODEL", "deepseek-chat")

    def available(self, case_id=None):
        return bool(self.api_key)

    def build_prompt(self, case_data, rule_hits):
        cust = json.dumps(case_data["customer_info"], ensure_ascii=False, indent=2)
        txs = json.dumps(case_data["transactions"], ensure_ascii=False, indent=2)
        hits = "\n".join(
            f"- {h['rule_id']} {h['rule_name']}：{h['trigger_desc']}" for h in rule_hits
        ) or "（无规则命中）"
        return PROMPT_TEMPLATE.format(
            customer=cust, transactions=txs, rule_hits=hits,
            official_types="\n".join(f"- {t}" for t in OFFICIAL_TYPES))

    def diagnose(self, case_id, case_data, rule_hits):
        # 签名与 MockProvider 保持一致（case_id 仅作上下文，不参与请求体）
        if not self.available():
            raise RuntimeError("未配置 OPENAI_API_KEY，Live Provider 不可用")
        prompt = self.build_prompt(case_data, rule_hits)
        req = urllib.request.Request(
            f"{self.base_url}/chat/completions",
            data=json.dumps({
                "model": self.model,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.1,
                "response_format": {"type": "json_object"},
            }).encode("utf-8"),
            headers={"Content-Type": "application/json",
                     "Authorization": f"Bearer {self.api_key}"},
            method="POST")
        with urllib.request.urlopen(req, timeout=60) as resp:
            body = json.loads(resp.read().decode("utf-8"))
        content = body["choices"][0]["message"]["content"]
        result = json.loads(content)
        result["model"] = self.model
        result["provider"] = "live"
        return result


def get_provider():
    """按环境变量 AML_AI_PROVIDER 选择，默认 mock"""
    mode = os.environ.get("AML_AI_PROVIDER", "mock").lower()
    if mode == "live":
        return LiveProvider()
    return MockProvider()
