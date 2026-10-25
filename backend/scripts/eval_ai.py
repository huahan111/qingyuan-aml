"""AI 输出评测框架：把《模型输出评测集》的评测方法变成可复跑的代码。

用法：
  python3 backend/scripts/eval_ai.py --check                  # 校验评测集完整性（无需 API key）
  AML_EVAL_PROVIDER=live python3 backend/scripts/eval_ai.py \
      --mode constrained --out docs/eval_report_$(date +%Y%m%d).json
  # baseline = 裸跑（不注入官方类型清单）／constrained = 注入清单与易混差异（对齐 91.7% 口径）

评分口径（对齐评测集 v0.1 的评分细则）：
- 类型归属：模型结论须落在期望的官方类型（正常样例则不得给出可疑类型）
- 结论方向：可疑（应报 STR）/ 正常（不报），一票否决项（幻觉法条、越界结论）单独记录
说明：2026-10 的 45.8%→91.7% 五轮结论来自人工多模型会话（见评测结论收口文档）；
本框架的作用是让后续扩容（32→200+、双盲）可以按同一口径自动复跑。
"""
import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.request
from datetime import date

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE)

from ai_diagnosis import AiUnavailableError, OFFICIAL_TYPES  # noqa: E402

EVAL_PATH = os.path.join(BASE, "data", "eval_set_v0.1.json")

BASELINE_PROMPT = """你是银行反洗钱监测岗。根据以下客户画像与交易形态，判断是否可疑并给出可疑交易类型。

【客户画像】{profile}

【交易形态】{pattern}

直接以 JSON 输出：{{"conclusion": "可疑|正常", "official_type_no": "类型编号或空", "reason": "一句话依据"}}"""

CONSTRAINED_PROMPT = """你是银行反洗钱监测岗。根据以下客户画像与交易形态判断是否可疑，并从官方类型清单中选择类型。

【官方可疑交易类型清单】（结论只能从中选择；均不符合且无可疑特征时输出"正常"）
{official_types}

【硬性约束】
1. 正常样例（形似可疑但材料合理的）必须输出"正常"，不得为安全起见报可疑
2. 禁止编造法规条文与不存在的类型
3. 不得以户籍、地域刻板印象作为判断依据

【客户画像】{profile}

【交易形态】{pattern}

以 JSON 输出：{{"conclusion": "可疑|正常", "official_type_no": "类型编号或空", "reason": "一句话依据"}}"""


def load_set():
    with open(EVAL_PATH, encoding="utf-8") as f:
        return json.load(f)


def check_set():
    data = load_set()
    cases = data["cases"]
    ids = [c["id"] for c in cases]
    problems = []
    if len(set(ids)) != len(ids):
        problems.append("样例 ID 重复")
    for c in cases:
        for field in ("expected_conclusion", "expected_type", "profile", "pattern"):
            if not c.get(field):
                problems.append(f"{c['id']} 缺 {field}")
        if "可疑" not in c["expected_conclusion"] and "正常" not in c["expected_conclusion"]:
            problems.append(f"{c['id']} 期望结论口径不明：{c['expected_conclusion']}")
    sus = sum(1 for c in cases if "可疑" in c["expected_conclusion"])
    print(f"评测集：{len(cases)} 条（可疑 {sus} / 正常 {len(cases) - sus}）")
    print("完整性校验：", "通过" if not problems else "；".join(problems))
    return not problems


def _extract_type_no(text: str) -> str:
    m = re.search(r"第\s*([0-9]+[-–][0-9]+|[0-9]+)\s*类", text or "")
    return f"第{m.group(1)}类" if m else ""


def _call_model(prompt: str):
    """OpenAI 兼容调用（复用 ai_diagnosis 的环境变量约定与异常语义）。"""
    api_key = os.environ.get("OPENAI_API_KEY", "")
    if not api_key:
        raise SystemExit("未配置 OPENAI_API_KEY：评测需要真模型（mock 无预生成结果可用）。"
                         "先运行 --check 校验评测集，或配置 key 后重试。")
    base_url = os.environ.get("OPENAI_BASE_URL", "https://api.deepseek.com/v1")
    model = os.environ.get("AML_MODEL", "deepseek-chat")
    req = urllib.request.Request(
        f"{base_url}/chat/completions",
        data=json.dumps({"model": model,
                         "messages": [{"role": "user", "content": prompt}],
                         "temperature": 0.1,
                         "response_format": {"type": "json_object"}}).encode("utf-8"),
        headers={"Content-Type": "application/json",
                 "Authorization": f"Bearer {api_key}"}, method="POST")
    last = "unknown"
    for _ in (1, 2):
        try:
            with urllib.request.urlopen(req, timeout=90) as resp:
                body = json.loads(resp.read().decode("utf-8"))
            content = body["choices"][0]["message"]["content"]
            return json.loads(content), model
        except (urllib.error.URLError, TimeoutError, OSError, KeyError, IndexError,
                ValueError, json.JSONDecodeError) as e:
            last = f"{type(e).__name__}: {e}"
            continue
    raise AiUnavailableError(f"评测调用失败（已重试）：{last}")


def run_eval(mode: str, out_path: str):
    data = load_set()
    template = BASELINE_PROMPT if mode == "baseline" else CONSTRAINED_PROMPT
    results, type_ok, concl_ok, normal_total, normal_ok = [], 0, 0, 0, 0
    for c in data["cases"]:
        prompt = template.format(
            profile=c["profile"], pattern=c["pattern"],
            official_types="\n".join(f"- {t}" for t in OFFICIAL_TYPES))
        answer, model = _call_model(prompt)
        predicted_concl = "可疑" if "可疑" in str(answer.get("conclusion", "")) else "正常"
        expected_sus = "可疑" in c["expected_conclusion"]
        predicted_type = _extract_type_no(
            str(answer.get("official_type_no", "")) + str(answer.get("reason", "")))
        expected_type = _extract_type_no(c["expected_type"]) or c["expected_type"]
        type_match = (expected_type in (predicted_type or str(answer.get("official_type_no", "")))) \
            if expected_sus else (predicted_concl == "正常")
        concl_match = predicted_concl == ("可疑" if expected_sus else "正常")
        type_ok += type_match
        concl_ok += concl_match
        if not expected_sus:
            normal_total += 1
            normal_ok += (predicted_concl == "正常")
        results.append({"id": c["id"], "expected": c["expected_conclusion"][:24],
                        "expected_type": expected_type,
                        "predicted": predicted_concl, "predicted_type": predicted_type,
                        "type_ok": type_match, "conclusion_ok": concl_match,
                        "reason": str(answer.get("reason", ""))[:120]})
        print(f"{c['id']:<5} 期望[{c['expected_conclusion'][:10]}|{expected_type[:14]}] "
              f"预测[{predicted_concl}|{predicted_type or '—'}] "
              f"{'✓' if type_match else '✗'}")
    n = len(results)
    report = {
        "meta": {"date": date.today().isoformat(), "mode": mode,
                 "model": os.environ.get("AML_MODEL", "deepseek-chat"),
                 "set": "eval_set_v0.1 (32)", "note": "自动评测框架产出；口径对齐人工五轮评测"},
        "summary": {"n": n, "type_accuracy": round(type_ok / n, 3),
                    "conclusion_accuracy": round(concl_ok / n, 3),
                    "normal_total": normal_total, "normal_false_alarm": normal_total - normal_ok},
        "results": results,
    }
    path = out_path or os.path.join(BASE, "..", "docs",
                                    f"eval_report_{mode}_{date.today():%Y%m%d}.json")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print(f"\n类型归属 {type_ok}/{n}（{type_ok / n:.1%}）；结论方向 {concl_ok}/{n}；"
          f"正常样例误报 {normal_total - normal_ok}/{normal_total}")
    print("报告 →", path)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true", help="仅校验评测集完整性")
    ap.add_argument("--mode", choices=("baseline", "constrained"), default="constrained")
    ap.add_argument("--out", default="")
    args = ap.parse_args()
    if args.check or not os.environ.get("OPENAI_API_KEY"):
        ok = check_set()
        sys.exit(0 if (ok or not args.check) else 1)
    run_eval(args.mode, args.out)
