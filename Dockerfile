# 清源AML 演示MVP 容器镜像
# 默认安全配置：只读模式 + 0.0.0.0 监听（公开演示前提：可看不可写）
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    QINGYUAN_READ_ONLY=1 \
    QINGYUAN_HOST=0.0.0.0 \
    QINGYUAN_PORT=8000

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/ backend/
COPY frontend/ frontend/

# 数据目录（SQLite 库首次启动时由 entrypoint 初始化；named volume 首挂会自动带出镜像内演示 JSON）
RUN chmod +x backend/docker-entrypoint.sh
EXPOSE 8000

ENTRYPOINT ["backend/docker-entrypoint.sh"]
