# AI Panel Studio — TDD 核心测试点清单

> **TDD 阶段交付物** | 分析范围：5 个核心业务模块 | 不包含代码，仅输出测试策略

---

## 1. 嘉宾生成 (Guest Generation)

### 1.1 正常路径：标准输入生成阵容

| 项目 | 内容 |
|---|---|
| **测试目的** | 验证 LLM 能根据话题和人数生成符合 Schema 的嘉宾阵容 |
| **输入数据** | `topic: "AI会取代人类工作吗"`, `expert_count: 3`, `language: "zh-CN"` |
| **预期输出** | 返回 4 个 Guest 对象（1 host + 3 expert） |
| **关键断言** | ① 每个 Guest 含 `name/title/stance/stance_label/color/bio/persona_prompt` 全部非空字段 ② `role` 字段恰好 1 个 `"host"` + N 个 `"expert"` ③ `color` 格式为合法 Hex `#RRGGBB` ④ Host 的 `color` 固定为 `#E8A840` ⑤ 所有 Expert 的 `color` 互不相同 ⑥ `speech_order` 从 0 开始连续递增 |

### 1.2 边界测试：极端人数

| 项目 | 内容 |
|---|---|
| **测试目的** | 验证边界值（2 人最少，8 人最多）不崩溃 |
| **输入** | `expert_count: 2` / `expert_count: 8` |
| **预期** | 分别返回 3 个 / 9 个 Guest；超出 8 时返回 422 错误 |
| **边界情况** | `expert_count: 0` → 400 错误 `"专家人数必须介于 2 和 8 之间"`; `expert_count: 99` → 422 校验失败 |

### 1.3 边界测试：空话题

| 项目 | 内容 |
|---|---|
| **测试目的** | 话题缺失时 API 应拒绝请求 |
| **输入** | `topic: ""` (空字符串) 或 `topic` 字段缺失 |
| **预期** | HTTP 400，error.code = `"VALIDATION_ERROR"`，message 包含 `"topic"` |
| **边界** | 超长话题 (>200 字符)：应截断或拒绝 |

### 1.4 异常测试：LLM 调用失败

| 项目 | 内容 |
|---|---|
| **测试目的** | LLM API 不可用时系统优雅降级 |
| **Mock** | `llm_client.generate()` 抛出 `TimeoutError` |
| **预期** | 返回 HTTP 502，error.code = `"LLM_ERROR"`；数据库不留孤儿 Guest 记录 |
| **边界** | LLM 返回格式错误（非 JSON 或缺少必填字段）：应触发 retry 后仍失败才返回 502 |

### 1.5 幂等性：重新生成

| 项目 | 内容 |
|---|---|
| **测试目的** | `regenerate: true` 时旧嘉宾被正确替换 |
| **输入** | 已有 4 个 Guest 的讨论，调用 `POST .../guests/generate { regenerate: true }` |
| **预期** | 旧 Guest 全部 `is_active = 0`（软删除），新 Guest 插入；Guest 总数 = 旧(4, inactive) + 新(4, active) = 8；但 API 仅返回 4 个 active |
| **边界** | 讨论不在 `setup` 状态时拒绝重新生成（409 Conflict） |

---

## 2. 对话流控制 (Dialogue Flow)

### 2.1 状态机：完整生命周期

| 项目 | 内容 |
|---|---|
| **测试目的** | Discussion 状态按 `setup → active → summarizing → finished` 顺序流转 |
| **前置** | Discussion 处于 `setup`，已生成 Guest |
| **步骤** | ① `POST /start` → status 变为 `active` ② 模拟 N 轮发言 ③ `POST /end` → status 变为 `summarizing` ④ 总结生成完成 → status 变 `finished` |
| **断言** | 每个状态转换成功；非法转换被拒绝（如 setup 直接跳 finished → 409） |
| **边界** | setup 跳 active 时若无 Guest 或无 Host → 400 错误 |

### 2.2 发言顺序：开场→发言→总结

| 项目 | 内容 |
|---|---|
| **测试目的** | 验证 Orchestrator 生成的 transcript 符合顺序约束 |
| **前置** | Discussion 处于 `active`，4 位 Guest |
| **预期顺序** | ① 第一条 entry_type = `opening_statement` (Host) ② 后续 N 条为 `position_statement` / `speech` / `rebuttal` / `supplement` 等 ③ 最后一条 entry_type = `host_summary` (Host) |
| **断言** | `transcript_entries[0].entry_type == "opening_statement"` 且 `guest.role == "host"`；`transcript_entries[-1].entry_type == "host_summary"` |
| **边界** | 讨论被强制终止 (`active → finished`) 时不生成 `host_summary` |

### 2.3 并发互斥：同时仅 1 人 Speaking

| 项目 | 内容 |
|---|---|
| **测试目的** | Guest 状态机保证同一讨论内最多 1 人 `speaking` |
| **前置** | Guest A 已处于 `speaking` |
| **操作** | 尝试将 Guest B 的 status 设为 `speaking` |
| **预期** | 后端拒绝（返回 409 或由 Orchestrator 排队）；数据库查询 `SELECT COUNT(*) FROM guests WHERE discussion_id=? AND status='speaking'` 始终 ≤ 1 |
| **边界** | Guest A speaking → 超时无响应 → Orchestrator 自动将其置为 `idle` → 释放锁 |

### 2.4 状态流转：Guest 四态

| 项目 | 内容 |
|---|---|
| **测试目的** | Guest 状态按 `idle → thinking → speaking → waiting → idle` 正确流转 |
| **测试场景** | ① idle → thinking（合法）② thinking → speaking（合法）③ speaking → idle（合法，直接跳过 waiting）④ waiting → speaking（合法，被主持人追问）⑤ idle → waiting（非法，应拒绝）⑥ thinking → thinking（合法，保持） |
| **断言** | 合法转换成功更新 DB；非法转换返回 409 |

### 2.5 多讨论并行隔离

| 项目 | 内容 |
|---|---|
| **测试目的** | 两个 active Discussion 的状态互不干扰 |
| **前置** | Discussion A (id=aaa) 和 Discussion B (id=bbb) 同时 active |
| **操作** | A 的 Guest 1 设为 speaking；查询 B 的 Guest 状态 |
| **预期** | B 的所有 Guest 状态不受影响；A 的 transcript 不包含 B 的 entry；B 的 SSE channel 不接收 A 的事件 |
| **断言** | 所有查询加 `discussion_id` 条件后隔离正确；跨讨论 orphan 检查为 0 |

---

## 3. 共识提取 (Consensus Extraction)

### 3.1 正常路径：从对话中提取共识

| 项目 | 内容 |
|---|---|
| **测试目的** | LLM 能从多轮发言中正确识别各方达成共识的观点 |
| **输入数据** | 3 位 Expert 的 6 条发言，其中 3 条明确认同 `"AI 监管需要分级制度"` |
| **预期输出** | 返回至少 1 个 ConsensusItem：`content` 描述该共识；`agreed_guests` 数组包含认同该观点的 guest_id；`confidence ≥ 0.75` |
| **断言** | `agreed_guests` 中的所有 ID 确实存在于该 Discussion；`confidence ∈ [0, 1]`；`source_entries` 引用的 transcript ID 有效 |

### 3.2 边界测试：无共识时

| 项目 | 内容 |
|---|---|
| **测试目的** | 各方分歧严重、无任何共识时，不强行生成虚假共识 |
| **输入** | 3 位 Expert 持完全相反立场，无观点重叠 |
| **预期** | 返回空列表 `items: []`，不返回 `null` 或 undefined |
| **边界** | `confidence` 低于阈值（如 < 0.5）的潜在共识不应入库 |

### 3.3 共识演化：新增与失效

| 项目 | 内容 |
|---|---|
| **测试目的** | 讨论推进过程中共识动态变化 |
| **前置** | 已有 ConsensusItem C1 (confidence 0.8, is_active=1) |
| **操作** | 新增一轮发言后 Guest 立场反转（原认同者现反对）→ 触发重新分析 |
| **预期** | C1 的 `is_active` 设为 0；可能生成新的 DivergenceItem；`consensus_update` SSE 事件推送更新后的列表 |
| **边界** | `is_active=false` 的共识在 API 的 `GET /consensus` 中默认不返回（`include_inactive=false`） |

### 3.4 数据完整性：共识关联验证

| 项目 | 内容 |
|---|---|
| **测试目的** | ConsensusItem 的外键和 JSON 字段引用完整性 |
| **断言** | ① `discussion_id` 指向存在的 Discussion ② `agreed_guests` JSON 数组中的每个 UUID 是有效的 Guest ③ `source_entries` JSON 数组中的每个 UUID 是有效的 TranscriptEntry ④ 孤儿检查 `agreed_guests` 中的 guest_id 在 guests 表中存在 |

---

## 4. 讨论生命周期 (Discussion Lifecycle)

### 4.1 状态机非法转换拦截

| 项目 | 内容 |
|---|---|
| **测试目的** | API 层拒绝所有非法状态转换 |
| **合法转换** | `setup → active`, `active → summarizing`, `summarizing → finished`, `active → finished` (强制终止), `summarizing → active` (总结失败回退) |
| **非法转换** | `setup → finished` (直接跳), `finished → active` (复活), `active → setup` (回退), `finished → summarizing` |
| **预期** | 非法转换返回 HTTP 409 + `error.code = "INVALID_STATE_TRANSITION"` |

### 4.2 讨论总结生成

| 项目 | 内容 |
|---|---|
| **测试目的** | DiscussionSummary 在讨论 `finished` 后正确生成 |
| **前置** | Discussion status=`summarizing`，已有 25 条 transcript，5 个 consensus，3 个 divergence |
| **操作** | Orchestrator 调用 LLM 生成总结 → 写入 `discussion_summaries` 表 |
| **断言** | `content` 非空；`key_findings` JSON 数组长度 ≥ 1；`guest_contributions` 包含每个 Guest 的贡献摘要；`generation_model` 非空 |
| **边界** | LLM 总结超时 → 自动重试 1 次 → 仍失败则标记 `generation_model = "fallback_template"` |

### 4.3 强制终止不生成总结

| 项目 | 内容 |
|---|---|
| **测试目的** | 用户点击"强制终止"后状态直接变 finished，不触发总结 |
| **前置** | Discussion 处于 `active` |
| **操作** | `POST /discussions/{id}/end { force: true }` (或专门端点) |
| **断言** | 状态 = `finished`；`discussion_summaries` 表中无对应记录；SSE 推送 `discussion_status_change` 事件 |

---

## 5. SSE 事件完整性 (Event Integrity)

### 5.1 事件类型覆盖率

| 项目 | 内容 |
|---|---|
| **测试目的** | 一次完整讨论流程中全部 9 种事件类型均有推送 |
| **预期事件序列** | ① `discussion_status_change` (setup→active) ② `guest_status_change` (host→speaking) ③ `transcript_delta` × N ④ `transcript_append` ⑤ `snapshot_update` ⑥ `round_advance` ⑦ `consensus_update` ⑧ `divergence_update` ⑨ `discussion_status_change` (→summarizing) ⑩ `discussion_status_change` (→finished) ⑪ `heartbeat`（每 15s） |
| **断言** | 验证事件类型集合包含以上全部；事件 `type` 字段符合 Schema 枚举值；每条事件含 `payload.discussion_id` |

### 5.2 hidden_cot 绝不泄露

| 项目 | 内容 |
|---|---|
| **测试目的** | 验证 `hidden_cot` 字段在任何 SSE 事件和 REST 响应中绝对不出现 |
| **检查点** | ① `GET /guests/{id}/snapshot` 响应体不含 `hidden_cot` ② SSE `snapshot_update` 事件 payload 不含 `hidden_cot` ③ `GET /discussions/{id}` 响应体中 Guest 相关字段不含 `hidden_cot` ④ 所有 OpenAPI Schema 的 `ThinkingSnapshotPublic` 定义不含 `hidden_cot` |
| **方法** | 对每个端点/事件序列化结果做 JSON path 遍历，搜索 `hidden_cot` key |

### 5.3 事件顺序一致性

| 项目 | 内容 |
|---|---|
| **测试目的** | 同一个 Discussion 内的事件按发生时间顺序推送 |
| **方法** | 监听 SSE channel，记录每条事件的接收时间戳；验证 `sequence_number` 严格递增 |
| **边界** | 断线重连后通过 `after_sequence` 参数恢复——验证不丢事件、不重复事件 |

### 5.4 多讨论 SSE 隔离

| 项目 | 内容 |
|---|---|
| **测试目的** | 监听 Discussion A 的 SSE channel 不接收 Discussion B 的事件 |
| **方法** | 同时连接 `/discussions/A/events` 和 `/discussions/B/events`；触发 A 的事件 |
| **断言** | Channel B 在 T+3s 内未收到任何事件（仅 heartbeat） |

---

## 测试优先级矩阵

| 优先级 | 模块 | 场景数 | 理由 |
|---|---|---|---|
| **P0** | 对话流控制 | 5 | 核心业务逻辑，错误直接影响用户体验 |
| **P0** | 嘉宾生成 | 5 | 用户入口，失败则整个流程无法启动 |
| **P1** | SSE 事件完整性 | 4 | 实时性核心，hidden_cot 安全关键 |
| **P1** | 讨论生命周期 | 3 | 状态机正确性是数据一致性的基础 |
| **P2** | 共识提取 | 4 | 增强功能，LLM 调用结果有不确定性 |

---

## 测试策略建议

1. **LLM 依赖隔离**：所有涉及 LLM 调用的测试使用 Mock，预定义输入→输出映射。真实 LLM 集成测试放在单独的 `integration/` 目录，不在 CI 中自动运行。
2. **数据库隔离**：每个测试用例使用独立的 SQLite `:memory:` 实例，通过 `docs/database_schema.sql` 初始化。
3. **SSE 测试**：使用 `httpx.AsyncClient` + `async for` 消费 SSE 流，设置 `timeout=5s` 防止挂起。
4. **状态机测试**：使用参数化测试覆盖全部合法/非法转换组合（Discussion 4种状态 × Guest 4种状态 = 独立用例）。
5. **快照测试**：对 OpenAPI Schema 和 JSON 响应体使用 snapshot testing，防止 `hidden_cot` 泄露和 Schema 回归。
