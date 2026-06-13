# AI Panel Studio — AI 圆桌讨论 Web App

> 让任何人都能瞬间召集一支"虚拟智库"，围绕任意议题展开深度碰撞。

## 快速开始（Docker）

> 无需安装 Python / Node.js / 任何依赖。只需 Docker。

```bash
# 1. 克隆项目
git clone <仓库地址>
cd AI圆桌讨论

# 2. 配置 API Key
cp .env.example .env
# 编辑 .env：LLM_API_KEY=sk-你的真实Key

# 3. 一键启动（首次约 5 分钟，以后 10 秒）
docker compose up -d

# 4. 打开浏览器
# http://localhost:5173
```

## 开发环境运行（不使用 Docker）

### 环境要求
- Python 3.11+ / Node.js 18+
- Deepseek API Key

### 后端

```bash
cd backend
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

### 前端

```bash
cd frontend
npm install
npx vite --port 5173
```

### 4. 初始化测试数据（可选）

```bash
cd ..
npm run db:seed   # 生成 3 个讨论 + 50+ 条模拟对话
```

## 技术选型

| 层 | 技术 | 理由 |
|---|---|---|
| 后端框架 | Python FastAPI | 异步支持、自动 OpenAPI 生成、Pydantic 校验 |
| 数据库 | SQLite (WAL 模式) | 零配置本地运行、单文件部署 |
| 前端框架 | React 18 + Vite | 组件化、HMR 热更新、生态丰富 |
| 状态管理 | Zustand | 极轻量 (<1KB)、无 boilerplate |
| 测试 | Pytest + Vitest | 统一 API、快、支持 async |
| 实时通信 | SSE (Server-Sent Events) | 单向推送、自动重连、浏览器原生支持 |
| LLM | Deepseek V4 Pro | OpenAI 兼容 API、性价比高 |

## 主要 API 列表

| 方法 | 端点 | 说明 |
|---|---|---|
| `POST` | `/api/v1/discussions` | 创建讨论 |
| `GET` | `/api/v1/discussions` | 讨论列表 |
| `GET` | `/api/v1/discussions/{id}` | 讨论详情 + 嘉宾 |
| `POST` | `/api/v1/discussions/{id}/guests/generate` | AI 生成嘉宾阵容 |
| `POST` | `/api/v1/discussions/{id}/start` | 开始讨论 |
| `POST` | `/api/v1/discussions/{id}/rounds/next` | 推进一轮（分布式 Agent 调度） |
| `POST` | `/api/v1/discussions/{id}/end` | 结束讨论 |
| `POST` | `/api/v1/discussions/{id}/summarize` | 生成总结 |
| `GET` | `/api/v1/discussions/{id}/messages` | 转录记录（游标分页） |
| `GET` | `/api/v1/discussions/{id}/events` | SSE 实时事件流 |
| `GET` | `/api/v1/discussions/{id}/consensus` | 共识列表 |
| `GET` | `/api/v1/discussions/{id}/divergences` | 分歧列表 |
| `GET` | `/health` | 健康检查 |

完整契约见 `docs/openapi.yaml`。

## 已完成能力

- [x] 首页讨论列表（创建/查看/状态标识）
- [x] AI 动态生成主持人与专家阵容（姓名/职业/立场/颜色）
- [x] 用户确认阵容 → 进入演播厅
- [x] 演播厅模式：主持人开场/追问/总结
- [x] 分布式 Agent 动态发言调度（并行评估 → urgency 排序 → 串行发言）
- [x] 专家状态小窗（idle/thinking/speaking/waiting + 思考气泡）
- [x] 实时共识与分歧（立场检测 + LLM 分析 + SSE 推送）
- [x] 现场 Transcript（色块区分、逐条 SSE 推送、自动滚动）
- [x] 主持人自然语言总结（非 JSON）
- [x] 多讨论并行隔离（discussion_id 全链路隔离）
- [x] 响应式布局（桌面/平板/手机三断点）
- [x] hidden_cot 安全过滤（多层防御，绝不泄露到前端）
