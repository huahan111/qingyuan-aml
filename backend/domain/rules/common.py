"""规则公共依赖：时间解析、交易类型枚举与参数加载。"""
import json
from datetime import datetime

# ===== 交易字段三分：类型 / 用途 / 附言 =====
# type    = 交易类型，只描述"钱怎么走"（转账/现金/跨境/结汇…），是银行流水的原始字段
# purpose = 交易摘要/用途（工资、货款、税费、学费…），银行摘要或客户申报用途
# summary = 交易附言，客户自己在转账时填写的备注（可以为空）
# 三者不得混用：系统判断（"贴线""分散""尾数.99"）属于结论，只能写在规则触发说明里。
IN_TYPES = ("转账收入", "现金存入", "跨境收入", "结汇收入")
OUT_TYPES = ("转账支出", "现金支取", "跨境支出", "购汇支出", "代发工资支出", "代扣代缴支出")
CASH_IN = ("现金存入",)
CASH_TYPES = ("现金存入", "现金支取")
TRANSFER_IN = ("转账收入",)
CROSS_TYPES = ("跨境收入", "跨境支出")


def tx_type(t):
    return t.get("type") or ""


def is_in(t):
    return tx_type(t) in IN_TYPES


def is_out(t):
    return tx_type(t) in OUT_TYPES


def amt(t):
    """折人民币金额：外币交易取 amount_cny，人民币交易取 amount。"""
    v = t.get("amount_cny")
    try:
        return float(v) if v not in (None, "") else float(t.get("amount") or 0)
    except (TypeError, ValueError):
        return 0.0


def purpose(t):
    return (t.get("purpose") or "").strip()


# 新交易接入允许的日期写法（归一化为 ISO）；规则内部一律按 ISO 处理
DATE_FORMATS = ("%Y-%m-%d", "%Y/%m/%d", "%Y.%m.%d")
MONTH_FORMATS = ("%Y-%m", "%Y/%m")


def parse_dt(t):
    return datetime.strptime(f"{t['date']} {t.get('time', '12:00')}", "%Y-%m-%d %H:%M")


def parse_date(value):
    """把多种日期写法归一化为 YYYY-MM-DD；无法解析返回 None。"""
    if not isinstance(value, str):
        return None
    v = value.strip()
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(v, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return None


def parse_month(value):
    """把月份写法归一化为 YYYY-MM；无法解析返回 None。"""
    if not isinstance(value, str):
        return None
    v = value.strip()
    for fmt in MONTH_FORMATS:
        try:
            return datetime.strptime(v, fmt).strftime("%Y-%m")
        except ValueError:
            continue
    # 完整日期按月份精度截断
    full = parse_date(v)
    return full[:7] if full else None


def parse_open_date(value):
    """开户日期：兼容 YYYY-MM / YYYY-MM-DD / 斜杠变体；无法解析返回 None。"""
    if not isinstance(value, str):
        return None
    v = value.strip()
    for fmt in ("%Y-%m", "%Y/%m", "%Y-%m-%d", "%Y/%m/%d"):
        try:
            return datetime.strptime(v, fmt)
        except ValueError:
            continue
    return None


def load_rules(conn):
    rows = conn.execute("SELECT rule_id, name, params FROM rules").fetchall()
    return {r[0]: {"name": r[1], "params": json.loads(r[2])} for r in rows}
