# =============================================================================
# 后端 Dockerfile
# =============================================================================
# 基础镜像: 轻量 Python 3.12（slim）
# =============================================================================
FROM python:3.12-slim

# 设置容器内的工作目录
WORKDIR /app

# ---- 第 1 步: 安装依赖（利用 Docker 缓存：不改 requirements.txt 就不重装） ----
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -i https://pypi.tuna.tsinghua.edu.cn/simple --trusted-host pypi.tuna.tsinghua.edu.cn -r requirements.txt

# ---- 第 2 步: 复制代码 ----
COPY backend/app/ ./app/
COPY docs/database_schema.sql /docs/

# ---- 第 3 步: 创建 data 目录（SQLite 数据库文件存放处）----
RUN mkdir -p /app/data

# ---- 第 4 步: 暴露端口 ----
EXPOSE 8000

# ---- 第 5 步: 启动 ----
# --host 0.0.0.0 = 允许外部访问（不加就只能容器内部访问）
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
