"""报告时限：发现日起 5 个工作日，跳过周末、法定节假日，计入调休上班日。

数据文件：backend/data/holidays.json（国办发明电〔2025〕7 号，2026 年全年）
格式：
{
  "version": "2026",
  "source": "国务院办公厅关于2026年部分节假日安排的通知（国办发明电〔2025〕7号）",
  "holidays": ["2026-01-01", ...],          # 放假调休日
  "extra_workdays": ["2026-01-04", ...]     # 调休补班的周六/周日（记为工作日）
}
兼容旧格式：纯日期数组视为 holidays。
"""
import json
import os
from datetime import date, timedelta

_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "data", "holidays.json")


def _load():
    """返回 (节假日集合, 调休上班日集合)。文件缺失或格式错误时返回空集合。"""
    try:
        with open(_PATH, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return set(), set()
    if isinstance(data, list):  # 兼容旧格式：纯日期数组
        return {str(d) for d in data}, set()
    if not isinstance(data, dict):
        return set(), set()
    holidays = {str(d) for d in data.get("holidays") or []}
    extra = {str(d) for d in data.get("extra_workdays") or []}
    return holidays, extra


HOLIDAYS, EXTRA_WORKDAYS = _load()


def holiday_count():
    """已配置的节假日数量（0 表示未配置，报告时限说明中会如实标注）。"""
    return len(HOLIDAYS)


def is_workday(d: date) -> bool:
    iso = d.isoformat()
    if iso in EXTRA_WORKDAYS:
        return True
    return d.weekday() < 5 and iso not in HOLIDAYS


def add_workdays(start: date, days: int) -> date:
    """按工作日顺延：跳过周末与法定节假日，计入调休上班日。

    未配置节假日时仅跳过周末——此时报告中的时限说明会显式提示未配置，
    不会假装"已按法定节假日计算"。
    """
    cur, left = start, days
    while left > 0:
        cur += timedelta(days=1)
        if is_workday(cur):
            left -= 1
    return cur
