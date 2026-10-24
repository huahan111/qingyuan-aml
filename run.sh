#!/bin/bash
# 清源AML MVP 一键启动
cd "$(dirname "$0")"

# 加载 .env（如存在）
if [ -f .env ]; then
  set -a; source .env; set +a
fi

# 检查依赖
python3 -c "import fastapi, uvicorn" 2>/dev/null || {
  echo "安装依赖中…"; pip3 install -r requirements.txt || exit 1
}

# 数据库不存在则初始化（法规/规则进 SQLite，演示案例进独立 JSON）
if [ ! -f backend/data/qingyuan.db ]; then
  echo "初始化法规库/规则库 + 演示数据集…"
  python3 backend/scripts/init_db.py
  python3 backend/scripts/import_regulations_existing.py
  python3 backend/scripts/import_regulations_new.py
  python3 backend/scripts/import_regulations_extra.py
  python3 backend/scripts/build_rules.py
  python3 backend/scripts/build_cases.py
  python3 backend/scripts/build_mock_diagnosis.py
fi

echo ""
echo "清源AML MVP 启动中 → http://127.0.0.1:8000"
echo "AI 诊断源: ${AML_AI_PROVIDER:-mock}（live 模式请在 .env 配置 OPENAI_API_KEY）"
echo ""
cd backend && python3 main.py
