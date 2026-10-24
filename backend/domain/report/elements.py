"""STR 要素定义加载层。

62 项要素定义存放在 backend/data/str_elements.json，新增/调整字段只改 JSON，
不改 build_report 主流程。加载时校验编号连续、四部分齐全，数据损坏立即失败。
"""
import json
import os

_DATA_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "data", "str_elements.json")


def load_definition(path=None):
    with open(path or _DATA_PATH, encoding="utf-8") as f:
        data = json.load(f)

    elements = data.get("elements") or []
    parts = {int(k): v for k, v in (data.get("parts") or {}).items()}

    expected = list(range(1, 63))
    actual = [e.get("no") for e in elements]
    if actual != expected:
        raise ValueError("str_elements.json 编号必须为 1–62 连续")
    for e in elements:
        if e.get("part") not in parts:
            raise ValueError(f"第 {e.get('no')} 项所属部分 {e.get('part')} 未定义")
        if not str(e.get("name", "")).strip():
            raise ValueError(f"第 {e.get('no')} 项缺少要素名称")
    if set(parts) != {1, 2, 3, 4}:
        raise ValueError("str_elements.json 必须定义四个部分")
    return elements, parts


ELEMENTS, PARTS = load_definition()
STR_ELEMS = [[e["no"], e["part"], e["name"]] for e in ELEMENTS]
STR_PART = PARTS
