#!/bin/sh
# 容器入口：数据库不存在则初始化（与 run.sh 同序），随后启动服务
set -e
cd /app/backend

if [ ! -f data/qingyuan.db ]; then
  echo "初始化法规库/规则库 + 演示数据集…"
  python3 scripts/init_db.py
  python3 scripts/import_regulations_existing.py
  python3 scripts/import_regulations_new.py
  python3 scripts/import_regulations_extra.py
  python3 scripts/build_rules.py
  python3 scripts/build_cases.py
  python3 scripts/build_mock_diagnosis.py
fi

echo "清源AML MVP 启动（read_only=${QINGYUAN_READ_ONLY}, host=${QINGYUAN_HOST:-0.0.0.0}, port=${QINGYUAN_PORT:-8000}）"
exec python3 main.py
