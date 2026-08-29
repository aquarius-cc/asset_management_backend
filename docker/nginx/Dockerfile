# =============================================================================
# Nginx + 前端 多阶段构建
# =============================================================================
# Stage 1: 构建前端 (Vue 3 + Vite)
FROM node:20-alpine AS frontend-build
WORKDIR /app
COPY vue-assetmanagement/package*.json ./
RUN npm ci --prefer-offline
COPY vue-assetmanagement/ ./
# F-1 门禁(2026-08-26): 构建前强制校验环境变量完整性。
# 缺 VITE_TOKEN_CRYPTO_KEY 时直接失败, 防止产出首屏白屏的生产包。
# 密钥经文件通道注入(S2决策): CI 部署前将真实值写入 .env.production.local
# (已被 .gitignore 排除), 或由 CI job 改写 .env.production 后再触发本构建。
RUN node scripts/check-env.mjs \
    || (echo '❌ 环境变量校验失败: 请在构建上下文中提供 .env.production.local 或完整的 .env.production' && exit 1)
RUN npm run build

# Stage 2: Nginx 服务
FROM nginx:1.27-alpine

RUN apk add --no-cache curl gettext

# 删除默认配置
RUN rm -f /etc/nginx/conf.d/default.conf

# 复制配置模板和入口脚本
COPY docker/nginx/nginx.conf /etc/nginx/nginx.conf
COPY docker/nginx/conf.d/ /etc/nginx/conf.d/
COPY docker/nginx/entrypoint.sh /docker-entrypoint-custom.sh
RUN chmod +x /docker-entrypoint-custom.sh

# 复制前端构建产物
COPY --from=frontend-build /app/dist /app/dist

# 创建 ACME challenge 目录
RUN mkdir -p /var/www/certbot

EXPOSE 80 443

HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD curl -f http://localhost/health/ || exit 1

ENTRYPOINT ["/docker-entrypoint-custom.sh"]
