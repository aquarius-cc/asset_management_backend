# =============================================================================
# Dockerfile - 资产管理系统容器镜像 (多阶段构建)
# =============================================================================

# === Stage 1: 构建阶段 (含编译依赖) ===
FROM python:3.12.8-slim-bookworm AS builder

WORKDIR /app

# 安装编译依赖 (仅此阶段需要)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq-dev \
    build-essential \
    pkg-config \
    && rm -rf /var/lib/apt/lists/*

COPY requirements/base.txt /app/requirements/base.txt
RUN pip install --no-cache-dir --prefix=/install -r requirements/base.txt

# === Stage 2: 运行阶段 (仅运行时依赖) ===
FROM python:3.12.8-slim-bookworm

# 安装运行时依赖 (无需 build-essential)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    curl \
    && rm -rf /var/lib/apt/lists/*

# 从 builder 阶段复制已安装的 Python 包
COPY --from=builder /install /usr/local

# 【安全】创建非 root 用户
RUN groupadd -r appuser && useradd -r -g appuser -d /app -s /sbin/nologin appuser

WORKDIR /app

# 复制应用代码
COPY . /app/

# 静态文件和媒体目录 + 权限设置
RUN mkdir -p /app/staticfiles /app/media \
    && chown -R appuser:appuser /app

# 【安全】切换到非 root 用户
USER appuser

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health/')" || exit 1

ENTRYPOINT ["bash", "/app/docker-entrypoint.sh"]
CMD ["daphne", "-b", "0.0.0.0", "-p", "8000", "config.asgi:application"]
