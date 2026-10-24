"""演示数据重置：清空上报台账与已定性案例库，保留法规、规则与演示 JSON。

用法：
  python3 backend/scripts/reset_demo.py          # 交互确认
  python3 backend/scripts/reset_demo.py --yes    # 跳过确认
"""
import argparse
import os
import sys

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE)

from infra.db import get_db  # noqa: E402
from services.demo import reset  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description="重置清源AML演示运营数据")
    parser.add_argument("--yes", action="store_true", help="跳过确认")
    args = parser.parse_args()
    if not args.yes:
        answer = input("将清空上报台账与已定性案例库，输入 YES 继续：").strip()
        if answer != "YES":
            print("已取消")
            return 1
    conn = get_db()
    try:
        result = reset(conn)
    finally:
        conn.close()
    print(f"已重置：清除 {result['submissions']} 条上报、{result['library_cases']} 条案例库")
    return 0


if __name__ == "__main__":
    sys.exit(main())
