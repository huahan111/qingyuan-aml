"""运营数据备份：把 SQLite 库按时间戳快照到 backend/data/backups/，保留最近 N 份。

用法：
  python3 backend/scripts/backup_db.py            # 备份并轮转（默认保留 10 份）
  python3 backend/scripts/backup_db.py --keep 20  # 自定义保留份数
备份内容含上报台账、已定性案例库与审计链（防篡改证据应随库一同归档）。
"""
import argparse
import shutil
import sqlite3
import os
import re
import sys
from datetime import datetime

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB = os.path.join(BASE, "data", "qingyuan.db")
BACKUP_DIR = os.path.join(BASE, "data", "backups")


def backup(keep: int = 10) -> str:
    if not os.path.exists(DB):
        print("未找到数据库，跳过备份：", DB)
        sys.exit(1)
    os.makedirs(BACKUP_DIR, exist_ok=True)
    # 用 SQLite 在线备份 API 保证一致性（比直接复制文件更稳，避免写到一半的页）
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    dest = os.path.join(BACKUP_DIR, f"qingyuan-{stamp}.db")
    src = sqlite3.connect(DB)
    dst = sqlite3.connect(dest)
    with dst:
        src.backup(dst)
    src.close()
    dst.close()
    print("已备份 →", dest)

    # 轮转：只保留最近 keep 份
    pattern = re.compile(r"^qingyuan-\d{8}-\d{6}\.db$")
    snaps = sorted(f for f in os.listdir(BACKUP_DIR) if pattern.match(f))
    for old in snaps[:-keep] if keep > 0 else []:
        os.remove(os.path.join(BACKUP_DIR, old))
        print("已轮转删除 →", old)
    return dest


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--keep", type=int, default=10, help="保留最近 N 份（0 = 不轮转）")
    backup(ap.parse_args().keep)
