#!/bin/bash
# 清源AML MVP 一键启动
cd "$(dirname "$0")"

# 加载 .env（如存在）
if [ -f .env ]; then
  set -a; source .env; set +a
fi

# 本机演示默认：可写、仅监听 127.0.0.1。
# 注意：直接 `python3 backend/main.py`（容器/托管平台路径）默认只读 + 0.0.0.0（fail-closed），
# 平台只注入 PORT、无法自定义环境变量，靠代码默认值保证公开实例不可写。
export QINGYUAN_READ_ONLY="${QINGYUAN_READ_ONLY:-0}"
export QINGYUAN_HOST="${QINGYUAN_HOST:-127.0.0.1}"

# 检查依赖
python3 -c "import fastapi, uvicorn" 2>/dev/null || {
  echo "安装依赖中…"; pip3 install -r requirements.txt || exit 1
}

# Python >= 3.10（api 层使用 `dict | None` 语法，3.9 及以下启动即 SyntaxError）
if ! python3 -c 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)'; then
  echo "需要 Python 3.10 或更高版本，当前：$(python3 --version)"; exit 1
fi

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
