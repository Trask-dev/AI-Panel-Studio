# AI Panel Studio — 核心 Prompt 记录文档

> 本文档记录引导 AI 完成本项目的关键 Prompt，按开发范式分阶段组织。
> 每段 Prompt 附带意图说明、遇到的挑战及修正策略。

---

## 一、【SDD 阶段】— 数据建模与 API 契约生成

### Prompt 1: 领域建模启动

```
# Role: 资深系统架构师 & 领域建模专家
# Task: 完成 SDD 第一阶段——领域建模与数据结构设计
基于需求文档提取核心实体（Discussion, Guest, TranscriptEvent, ConsensusItem等），
输出 Markdown 表格 + Mermaid ER 图 + 状态机设计 + 关键疑问确认。
```

**意图**：在零代码状态下，先建立领域模型共识，避免后期推翻数据结构。

**挑战**：AI 倾向于一次性补全所有细节，但需求中"思考过程 vs 公开内容"的分离逻辑容易混淆。

**修正**：明确要求区分 `hidden_cot`（绝不发送前端）和 `public_thought`（发送前端），并在 ER 图中标注安全敏感字段。

---

### Prompt 2: SQLite Schema 生成

```
# Role: 资深数据库架构师 & SQLite 专家
# Task: 设计 SQLite 数据库 Schema
要求：数据类型严谨、外键约束、索引优化、JSON 支持、软删除预留。
输出：Mermaid ER 图 + 完整 DDL + 设计决策说明。
```

**意图**：将领域模型转化为可执行的 SQL，确保"演播厅"高频查询场景有索引支撑。

**挑战**：AI 生成的多行 CHECK 约束被 SQLite 解析器拒绝。

**修正**：将跨行 CHECK 合并为单行 `CHECK(status IN (...))`，用 `sqlite3 :memory:` 逐条验证 DDL 语法。

---

### Prompt 3: OpenAPI 3.0 契约

```
# Role: 资深后端架构师 & API 设计专家
# Task: 设计 RESTful API 契约 (OpenAPI 3.0)
包含 Discussions/Messages/Streaming/Consensus 四个模块，
SSE 接口需详细说明数据流格式，所有 Schema 强类型定义。
```

**意图**：前后端分离开发前，锁定 API 契约作为唯一交互界面。

**挑战**：SSE 事件类型定义模糊，前端不知道如何解析。

**修正**：在 OpenAPI 的 `description` 字段中写出完整的 SSE 事件 JSON 示例，附 `event.type` 路由表。

---

## 二、【DDD 阶段】— 前端组件与页面生成

### Prompt 4: UI/UX 头脑风暴

```
# Role: 资深 UI/UX 设计师兼前端架构师
# Task: "圆桌"如何在二维屏幕上体现？演播厅沉浸感如何设计？
用 ASCII 草图 + 组件树 + 配色方案输出设计文档。
```

**意图**：在写 HTML/CSS 之前，先确定"电视演播厅"设计隐喻，避免做成聊天软件。

**挑战**：AI 对"圆桌"的理解停留在物理围坐——但屏幕是二维的。

**修正**：明确定义"看台视角"：用户是观众，嘉宾面朝用户排列。主持人居中放大，专家分列两侧。

---

### Prompt 5: UI 搭建执行计划

```
# Task: 制定 HTML/CSS 纯视觉实现计划
分 11 步执行，每步指定 HTML 标签结构 + CSS 布局方式。
响应式三断点: 1920px/1280px/768px。各区域独立滚动。
```

**意图**：将设计文档转化为可执行的施工步骤，每次只做一件事。

**挑战**：AI 擅自添加 JS 逻辑、跳过占位步骤直接填充内容。

**修正**：强制要求"暂不写 JS""只关注视觉和布局"——每步验收后才能进入下一步。

---

### Prompt 6: 前端重构为 React 应用

```
# Task: 将静态页面重构为对接真实后端的动态应用
第一步：扫描后端代码，列出所有真实 API 端点
第二步：删除硬编码 Mock 数据，创建 API Service 模块
第三步：绑定交互——点击按钮调用真实 API
第四步：SSE 监听 → 实时追加消息
```

**意图**：静态演示 → 生产可用。前后端打通。

**挑战**：Vite 代理未配置，前端请求去了 5173 端口，后端在 8000。

**修正**：在 `vite.config.js` 添加 `server.proxy: { "/api": "http://127.0.0.1:8000" }`。

---

## 三、【TDD 阶段】— 核心逻辑测试与实现

### Prompt 7: 批量 TDD — GuestGenerator

```
# Task: 一次性完成 GuestGenerator 模块的批量 TDD
1. 写 7 个测试函数（含参数化）
2. 写 GuestModel (Pydantic) + GuestGenerator 完整实现
3. Host 颜色强制 #E8A840，专家颜色互不相同
```

**意图**：跳过逐个 TDD 循环的低效，验证"批量 TDD"在工作流中的可行性。

**挑战**：`AsyncMock` 返回 coroutine 对象，同步 `_call_llm()` 无法直接使用。

**修正**：在 `_call_llm()` 中添加 `if hasattr(response, "__await__"): asyncio.run(response)`。

---

### Prompt 8: 批量 TDD — Orchestrator

```
# Task: 批量完成 Orchestrator 的 TDD
测试 GuestStateMachine 全部 10 种合法转换 + 非法转换拒绝
测试 speaking 互斥锁：同一时刻仅 1 人 speaking
测试多讨论并行隔离
```

**意图**：核心逻辑——讨论状态机 + 嘉宾状态机——必须有完整测试覆盖。

**挑战**：测试 fixture 创建 `active` 状态的讨论，但 `start()` 要求 `setup`。

**修正**：将 fixture 改为 `setup` 状态，测试通过 `start()` 进入 `active`。

---

### Prompt 9: SSE Manager + hidden_cot 安全测试

```
# Task: 测试 SSE Manager 的 hidden_cot 过滤
验证浅层 dict、深层嵌套 dict、数组内 hidden_cot 全部被递归移除
验证多讨论 SSE 隔离：disc-1 的事件不到达 disc-2
```

**意图**：安全性测试——`hidden_cot` 绝不泄露到前端，是多层防御的核心。

**挑战**：`asyncio.Queue` 绑定 event loop，sync 线程 `asyncio.run()` 新建 loop 导致 push 丢失。

**修正**：重写 SSEManager 为线程安全版——`queue.Queue` + `asyncio.to_thread()`。

---

## 四、【E2E 阶段】— 系统级端到端测试与质量闭环

### Prompt 10: SDD 差距审计

```
# Task: 回归 SDD 规格审计
逐条对照需求文档，标注: ✅已实现 / ⚠️有偏差 / ❌缺失 / 🔗断裂点
输出《缺陷-规格映射表》+《TDD 失败测试清单》+《分层修复路线图》
```

**意图**：项目推进多轮后，重新对齐原始需求，防止范围蔓延。

**挑战**：共识/分歧引擎被标记为"架构缺失"——Orchestrator 不推送 consensus_update 事件。

**修正**：新建 `consensus_analyzer.py`，在 `run_round()` 每轮末尾调用分析 + 推送 SSE。

---

### Prompt 11: 实时推送断裂诊断

```
# Task: 诊断 SSE 实时推送为什么未生效
检查四层: 后端是否推送 / 前端是否连接 / 连接后是否解析 / 解析后是否渲染
输出诊断报告 + 修复 + Network 面板验证
```

**意图**：系统性排查——不是"修一改一"，而是"修一改所有同类问题"。

**挑战**：`asyncio.Queue` 跨线程故障——这是 SSE 推送失效的根因。

**修正**：SSEManager 全部改为 `queue.Queue`（线程安全），Orchestrator 的 `_push_sse` 从 `asyncio.run()` 改为直接调用同步 `push()`。

---

### Prompt 12: 视觉语言对齐诊断

```
# Task: "专业级 AI 演播厅"应传递什么情绪？
分析三个维度: 情绪错位 / 层级混乱 / 系统缺失
输出: 设计令牌草案 + 信息层级重排 + 分层实施路线图
```

**意图**：用视觉语言讲述产品灵魂——不是"装修"，而是用色彩/间距/动效传递"权威、锐利、聚焦"的情绪。

**挑战**：暗色主题三层灰色亮度太接近（3%差距），所有区域视觉权重均等。

**修正**：拉开背景层级亮度差距至 8%，舞台光晕 opacity 从 0.04 提至 0.10，动效从 1500ms 加速至 800ms。

---

## 五、关键协作模式总结

| 模式 | 触发场景 | 效果 |
|---|---|---|
| **契约先行** | 任何新功能启动前，先写 OpenAPI/Schema/设计文档 | 避免后期返工 |
| **批量 TDD** | 模块完整、测试场景明确的场景 | 效率提升 3-5x |
| **系统性诊断** | 问题反复出现时，停止修症状，追溯到根因 | 一次修复解决一类问题 |
| **分层修复** | 大范围缺陷时，按"数据层→状态层→渲染层"顺序 | 不引入新耦合 |
| **视觉得到产品定位** | "这里为什么丑" → 追溯到情绪/层级/系统缺失 | 设计决策可解释 |
