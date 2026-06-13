# =============================================================================
# 前端 Dockerfile（多阶段构建）
# =============================================================================
# 第 1 阶段: 构建——用 Node.js 编译 React 代码
# =============================================================================
FROM node:20-alpine AS builder

WORKDIR /app
COPY frontend/package.json ./
RUN npm config set registry https://registry.npmmirror.com && npm install
COPY frontend/ ./
RUN npx vite build   # 产出在 frontend/dist/

# =============================================================================
# 第 2 阶段: 运行——用 nginx 托管编译好的静态文件
# =============================================================================
FROM nginx:alpine

# 把编译好的文件复制到 nginx 的默认网站目录
COPY --from=builder /app/dist /usr/share/nginx/html

# 把 API 请求代理到后端（/api → backend:8000）
RUN echo 'server { \
    listen 80; \
    location / { root /usr/share/nginx/html; try_files $uri /index.html; } \
    location /api/ { proxy_pass http://backend:8000; } \
    location /health { proxy_pass http://backend:8000; } \
}' > /etc/nginx/conf.d/default.conf

EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
