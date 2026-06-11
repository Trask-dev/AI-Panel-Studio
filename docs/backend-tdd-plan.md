# AI Panel Studio — 后端 TDD 执行计划

> **TDD 阶段交付物** | 技术栈: Python + pytest + pytest-asyncio + SQLite `:memory:`

---

## 目录

1. [测试文件清单与领域映射](#1-测试文件清单)
2. [test_guest_generator.py](#2-test_guest_generatorpy)
3. [test_orchestrator.py](#3-test_orchestratorpy)
4. [test_consensus_extractor.py](#4-test_consensus_extractorpy)
5. [test_discussion_lifecycle.py](#5-test_discussion_lifecyclepy)
6. [test_sse_manager.py](#6-test_sse_managerpy)
7. [测试基础设施](#7-测试基础设施)
8. [CI 集成建议](#8-ci-集成建议)

---

## 1. 测试文件清单

| 文件 | 对应领域概念 | 对应服务模块 | 测试函数数 | 优先级 |
|---|---|---|---|---|
| `test_guest_generator.py` | Guest 聚合根创建 | `services/persona_generator.py` | 7 | P0 |
| `test_orchestrator.py` | Discussion 流程编排 + Guest 状态机 | `services/orchestrator.py` | 8 | P0 |
| `test_consensus_extractor.py` | ConsensusItem / DivergenceItem 值对象 | `services/consensus_analyzer.py` | 6 | P2 |
| `test_discussion_lifecycle.py` | Discussion 聚合根状态机 | `api/discussions.py` + `models/discussion.py` | 7 | P1 |
| `test_sse_manager.py` | SSE 事件通道 + hidden_cot 安全 | `utils/sse_manager.py` | 6 | P1 |

**总计: 34 个测试函数**

---

## 2. test_guest_generator.py

**领域概念**: Guest 聚合根的创建工厂。接收 `topic + expert_count`，调用 LLM 生成 1 Host + N Expert，返回经过校验的 Guest 列表。

### 2.1 `test_generate_returns_correct_guest_count`

| TDD 步骤 | 内容 |
|---|---|
| **Red** | 调用 `GuestGenerator.generate(topic, expert_count=3)` → 返回空列表 → 测试失败 |
| **Green** | 实现 Mock LLM 返回预设 JSON，解析为 Guest 对象列表，返回 `len == 4` |
| **Refactor** | 提取 `_parse_llm_response()` 方法，处理 JSON 解析异常 |
| **断言** | `len(result) == 4`；`result[0].role == "host"`；`result[1].role == "expert"` |

### 2.2 `test_generated_host_has_gold_border_color`

| TDD 步骤 | 内容 |
|---|---|
| **Red** | Host 的 color 字段为 `None` → 测试失败 |
| **Green** | 强制 `result[0].color = "#E8A840"` |
| **Refactor** | 在解析阶段对 role="host" 强制覆盖 color 为金色 |
| **断言** | Host 的 `color == "#E8A840"`；每个 Expert 的 `color ≠ "#E8A840"`；所有 color 互不相同 |

### 2.3 `test_generated_guests_have_all_required_fields`

| TDD 步骤 | 内容 |
|---|---|
| **Red** | LLM 返回不完整 JSON（缺 `stance` 字段）→ 解析失败 |
| **Green** | 实现字段校验：缺失必填字段时抛出 `ValidationError` |
| **Refactor** | 使用 Pydantic `GuestCreateSchema` 做输入校验，与 API Schema 复用 |
| **断言** | 每个 Guest 含 `name/title/bio/stance/stance_label/color/persona_prompt` 全部非空 |

### 2.4 `test_reject_empty_topic`

| TDD 步骤 | 内容 |
|---|---|
| **Red** | `topic=""` → 无校验，LLM 被调用（浪费 API 调用）→ 测试失败 |
| **Green** | `if not topic or not topic.strip(): raise ValueError` |
| **Refactor** | 移至 Pydantic schema `DiscussionCreateRequest` 的 `@validator` |
| **断言** | `ValueError` 被抛出；LLM mock 被调用 0 次 |

### 2.5 `test_reject_invalid_expert_count`

| TDD 步骤 | 内容 |
|---|---|
| **Red** | `expert_count=1` 和 `expert_count=9` → 无校验 |
| **Green** | `if not 2 <= expert_count <= 8: raise ValueError` |
| **Refactor** | Pydantic `Field(ge=2, le=8)` 约束 |
| **断言** | 两次调用均抛 `ValueError`；消息包含 "2" 和 "8" |

### 2.6 `test_llm_failure_returns_502_without_orphan_data`

| TDD 步骤 | 内容 |
|---|---|
| **Red** | Mock LLM `raise TimeoutError` → 未处理异常 → 500 |
| **Green** | `try/except` → 记录日志 → 返回 `LLMGenerationError` |
| **Refactor** | 提取 `LLMClient` 抽象基类，注入 `MockLLMClient` 用于测试 |
| **断言** | 异常被捕获；数据库中无孤儿 Guest 记录（`SELECT COUNT(*) == 0`） |

### 2.7 `test_regenerate_replaces_old_guests`

| TDD 步骤 | 内容 |
|---|---|
| **Red** | 调用 `regenerate=True` 后旧 Guest 仍存在 → 测试失败 |
| **Green** | 旧 Guest 的 `is_active` 设为 0；新 Guest 插入 |
| **Refactor** | 使用事务包裹：`BEGIN → UPDATE is_active=0 → INSERT → COMMIT` |
| **断言** | `COUNT(*) WHERE is_active=1 == 4`（新）；`COUNT(*) WHERE is_active=0 == 4`（旧） |

---

## 3. test_orchestrator.py

**领域概念**: Discussion 聚合根的核心行为——控制发言顺序、管理 Guest 状态机、推进轮次。

### 3.1 `test_discussion_starts_with_opening_statement`

| TDD 步骤 | 内容 |
|---|---|
| **Red** | `Orchestrator.start()` → 无 transcript 生成 → 测试失败 |
| **Green** | 主持人调用 LLM 生成开场白 → `TranscriptEntry(entry_type="opening_statement")` 写入 DB |
| **Refactor** | 提取 `_host_speak()` 方法，复用发言逻辑 |
| **断言** | `entries[0].entry_type == "opening_statement"` 且 `guest.role == "host"` |

### 3.2 `test_discussion_ends_with_host_summary`

| TDD 步骤 | 内容 |
|---|---|
| **Red** | Orchestrator 循环结束 → 无总结 → 测试失败 |
| **Green** | 最后一轮后调用 `_generate_summary()` → 生成 `host_summary` entry |
| **Refactor** | 区分 `finish()` (正常结束) 和 `force_stop()` (强制终止)，仅前者生成总结 |
| **断言** | `entries[-1].entry_type == "host_summary"` |

### 3.3 `test_only_one_guest_speaking_at_a_time`

| TDD 步骤 | 内容 |
|---|---|
| **Red** | 两个 Guest 同时 `status="speaking"` → 无校验 → 测试失败 |
| **Green** | `_acquire_speaking_lock(discussion_id)` → 获取失败时排队等待 |
| **Refactor** | 使用 `asyncio.Lock` / DB 行锁 `SELECT ... FOR UPDATE` |
| **断言** | `SELECT COUNT(*) WHERE discussion_id=? AND status='speaking'` 始终 ≤ 1 |

### 3.4 `test_guest_status_idle_to_thinking_to_speaking`

| TDD 步骤 | 内容 |
|---|---|
| **Red** | 直接设置 `status="speaking"` → 无前置状态检查 → 跳过 thinking |
| **Green** | 实现 `GuestStateMachine.transition(from, to)` 校验合法转换 |
| **Refactor** | 状态机独立为 `GuestStateMachine` 类，可单独测试 |
| **断言** | `idle→thinking` 成功；`idle→speaking` 也合法（主持人点名）；`idle→waiting` 非法 |

### 3.5 `test_guest_status_illegal_transition_rejected`

| TDD 步骤 | 内容 |
|---|---|
| **Red** | `idle → waiting` 无报错 → 测试失败 |
| **Green** | 非法转换抛出 `InvalidStateTransitionError`，HTTP 409 |
| **Refactor** | 所有转换路径定义在 `TRANSITION_MAP` 字典中，参数化测试 |
| **断言** | 非法转换抛异常；合法转换成功更新 DB |

### 3.6 `test_round_advances_after_all_experts_speak`

| TDD 步骤 | 内容 |
|---|---|
| **Red** | `round_count` 始终为 0 → 测试失败 |
| **Green** | 每个 Expert 发言后计数；全员发言完毕 → `round_count += 1` |
| **Refactor** | `RoundTracker` 类追踪本轮已发言专家集合 |
| **断言** | 3 位 Expert 发言完毕后 `round_count == 1`；再一轮后 `== 2` |

### 3.7 `test_max_rounds_triggers_summarizing`

| TDD 步骤 | 内容 |
|---|---|
| **Red** | `max_rounds=3` → 无限循环 → 测试失败 |
| **Green** | 每轮结束后 `if round_count >= max_rounds: break` → 状态切换 |
| **Refactor** | `_check_end_conditions()` 方法统一检查 (max_rounds / 用户手动 / LLM 自然结束信号) |
| **断言** | `round_count == 3` 时讨论状态变为 `summarizing` |

### 3.8 `test_parallel_discussions_independent`

| TDD 步骤 | 内容 |
|---|---|
| **Red** | A 的发言出现在 B 的 transcript 中 → 隔离失败 |
| **Green** | 所有 SQL 查询强制 `WHERE discussion_id = ?` |
| **Refactor** | `DiscussionContext` 封装 discussion_id，注入到所有 Repository 方法 |
| **断言** | `SELECT * FROM transcript_entries WHERE discussion_id='B' AND guest_id IN (SELECT id FROM guests WHERE discussion_id='A')` → 0 行 |

---

## 4. test_consensus_extractor.py

**领域概念**: ConsensusItem / DivergenceItem 值对象。从 TranscriptEntry 列表中分析并提取结构化共识与分歧。

### 4.1 `test_extract_consensus_from_agreeing_statements`

| TDD 步骤 | 内容 |
|---|---|
| **Red** | 输入 6 条发言（3 条明确认同同一观点）→ 返回空 |
| **Green** | Mock LLM 返回预设共识 JSON → 解析为 `ConsensusItem` |
| **Refactor** | 拆分 `_build_analysis_prompt()` + `_parse_consensus_response()` |
| **断言** | 返回 1 个 `ConsensusItem`；`agreed_guests` 长度 == 3；`confidence >= 0.75` |

### 4.2 `test_no_false_consensus_when_no_agreement`

| TDD 步骤 | 内容 |
|---|---|
| **Red** | 输入 3 条完全对立的发言 → 仍然返回共识项 → 测试失败 |
| **Green** | Mock LLM 返回空列表 → 确保不强行生成 |
| **Refactor** | 增加 `confidence` 阈值过滤（< 0.5 不入库） |
| **断言** | `result == []`（空列表，非 None） |

### 4.3 `test_extract_divergence_with_parties`

| TDD 步骤 | 内容 |
|---|---|
| **Red** | 输入对立发言 → 无分歧识别 |
| **Green** | Mock LLM 返回 parties 分组 JSON → 解析为 `DivergenceItem` |
| **Refactor** | 统一 `ConsensusExtractor` + `DivergenceExtractor` 共用 `TranscriptAnalyzer` 基类 |
| **断言** | `parties` 数组含 2 组；每组含 `stance` + `guest_ids`；`severity` 非空 |

### 4.4 `test_consensus_can_be_invalidated`

| TDD 步骤 | 内容 |
|---|---|
| **Red** | 更新 `is_active` 无效果 → 旧共识仍返回 |
| **Green** | `ConsensusItem.invalidate()` 设 `is_active=False`；API 查询默认过滤 |
| **Refactor** | 增加 `updated_at` 时间戳，前端可展示"共识已推翻" |
| **断言** | 调用 `invalidate()` 后 `GET /consensus` 不返回该项；`GET /consensus?include_inactive=true` 返回该项 |

### 4.5 `test_consensus_source_entries_valid`

| TDD 步骤 | 内容 |
|---|---|
| **Red** | `source_entries` 引用不存在的 transcript ID → 无校验 |
| **Green** | 插入前验证 `source_entries` JSON 数组中每个 UUID 在 `transcript_entries` 中存在 |
| **Refactor** | DB 层用触发器或应用层 `SELECT EXISTS` 批量校验 |
| **断言** | 无效 UUID 抛 `IntegrityError`；有效 UUID 插入成功 |

### 4.6 `test_divergence_severity_classification`

| TDD 步骤 | 内容 |
|---|---|
| **Red** | `severity` 字段无约束，可写任意值 |
| **Green** | `CHECK(severity IN ('mild','moderate','sharp','fundamental'))` 约束 |
| **Refactor** | Pydantic `Literal` 类型校验 + DB CHECK 双保险 |
| **断言** | `"critical"` 被拒绝；`"sharp"` 正常入库 |

---

## 5. test_discussion_lifecycle.py

**领域概念**: Discussion 聚合根状态机。管理 `setup → active → summarizing → finished` 完整生命周期。

### 5.1 `test_valid_transitions_accepted`

| TDD 步骤 | 内容 |
|---|---|
| **Red** | 无状态校验 → 任意转换 |
| **Green** | 实现 `DiscussionStateMachine`，合法转换通过 |
| **Refactor** | 参数化测试：`@pytest.mark.parametrize("from,to", [("setup","active"), ("active","summarizing"), ...])` |
| **断言** | 5 种合法转换（含 `active→finished` 强制终止 和 `summarizing→active` 失败回退）全部成功 |

### 5.2 `test_illegal_transitions_rejected`

| TDD 步骤 | 内容 |
|---|---|
| **Red** | `finished → active` 无报错 |
| **Green** | `TRANSITION_MAP` 之外的转换抛 `InvalidStateTransitionError` |
| **Refactor** | API 层 `try/except` → HTTP 409 + 结构化 error body |
| **断言** | `setup→finished`, `finished→active`, `active→setup`, `finished→summarizing` 全部 409 |

### 5.3 `test_start_requires_guests`

| TDD 步骤 | 内容 |
|---|---|
| **Red** | `POST /start` 无 Guest → 成功进入 active |
| **Green** | 检查 `SELECT COUNT(*) FROM guests WHERE discussion_id=? AND is_active=1` ≥ 3 |
| **Refactor** | `Discussion.can_start()` 方法封装前置条件检查 |
| **断言** | 无 Host → 400 `"主持人未生成"`；专家 < 2 → 400 `"专家人数不足"` |

### 5.4 `test_force_stop_skips_summary`

| TDD 步骤 | 内容 |
|---|---|
| **Red** | 强制终止后仍生成总结 |
| **Green** | `stop(force=True)` → 状态直接变 `finished`，不调用 LLM 总结 |
| **Refactor** | `stop()` 和 `stop_force()` 分两个端点或参数控制 |
| **断言** | `status == "finished"`；`discussion_summaries` 表无记录；LLM mock 调用次数 == 0 |

### 5.5 `test_summary_failure_retries_once`

| TDD 步骤 | 内容 |
|---|---|
| **Red** | LLM 总结超时 → 直接抛异常 |
| **Green** | 第 1 次失败 → 等待 2s → 重试 1 次；第 2 次仍失败 → fallback |
| **Refactor** | `SummaryGenerator` 独立类，封装重试 + fallback 逻辑 |
| **断言** | LLM mock 被调用 2 次；`generation_model == "fallback_template"` |

### 5.6 `test_summary_fallback_uses_transcript_data`

| TDD 步骤 | 内容 |
|---|---|
| **Red** | fallback 总结内容为空 |
| **Green** | 模板拼接：`ConsensusItem` 列表 + `DivergenceItem` 列表 + 最后 3 轮 transcript |
| **Refactor** | `FallbackSummaryBuilder` 类，可扩展模板 |
| **断言** | `summary.content` 包含共识项关键词；`key_findings` 非空数组 |

### 5.7 `test_discussion_soft_delete_cascades`

| TDD 步骤 | 内容 |
|---|---|
| **Red** | `DELETE /discussions/{id}` → 仅删 Discussion |
| **Green** | SQLite `ON DELETE CASCADE` → 关联 Guest/Transcript/Consensus/Divergence/Snapshot 全部删除 |
| **Refactor** | 应用层先设 `status='finished'` 再删，日志记录删除操作 |
| **断言** | 删除后各子表 `SELECT COUNT(*) WHERE discussion_id=?` 全部为 0 |

---

## 6. test_sse_manager.py

**领域概念**: SSE 事件通道基础设施。涉及 ThinkingSnapshot 的 `hidden_cot` 安全隔离。

### 6.1 `test_all_nine_event_types_delivered`

| TDD 步骤 | 内容 |
|---|---|
| **Red** | SSE channel 仅推送 2 种事件 |
| **Green** | Orchestrator 每个步骤调用 `SSEManager.push(event)`；覆盖全部 9 种事件类型 |
| **Refactor** | `EventFactory` 统一构造事件 payload，确保 Schema 一致 |
| **断言** | 完整讨论流程后收集到的事件类型集合包含全部 9 种 |

### 6.2 `test_hidden_cot_absent_from_all_events`

| TDD 步骤 | 内容 |
|---|---|
| **Red** | `snapshot_update` 事件含 `hidden_cot` 字段 |
| **Green** | `SSEManager.push()` 内部过滤：`event.payload.pop("hidden_cot", None)` |
| **Refactor** | `SSEEventSerializer` 使用 `ThinkingSnapshotPublic` Pydantic schema 序列化，编译时保证 |
| **断言** | 所有事件的 JSON 序列化结果中不出现 `"hidden_cot"` key；JSON path 全量搜索 |

### 6.3 `test_hidden_cot_absent_from_rest_api`

| TDD 步骤 | 内容 |
|---|---|
| **Red** | `GET /guests/{id}/snapshot` 返回含 `hidden_cot` |
| **Green** | Route handler 返回类型注解为 `ThinkingSnapshotPublic`（不含 cot） |
| **Refactor** | 添加集成测试遍历所有 GET 端点，断言响应体不含 `hidden_cot` |
| **断言** | 3 个端点验证：`GET /snapshot`、`GET /discussions/{id}`、`GET /discussions/{id}/guests/{id}/snapshot` |

### 6.4 `test_event_sequence_numbers_monotonic`

| TDD 步骤 | 内容 |
|---|---|
| **Red** | 事件乱序推送 |
| **Green** | 每个 `transcript_delta` / `transcript_append` 的 `sequence_number` 严格递增 |
| **Refactor** | 使用 `itertools.pairwise` 验证相邻事件 seq 差值为 1 |
| **断言** | 事件序列的 `sequence_number` 从 1 开始连续无缺口 |

### 6.5 `test_reconnect_with_after_sequence_resumes_correctly`

| TDD 步骤 | 内容 |
|---|---|
| **Red** | 断线重连后收到全部历史事件（重复） |
| **Green** | 连接参数 `?after_sequence=5` → 仅推送 `sequence_number > 5` 的事件 |
| **Refactor** | `SSEManager.subscribe(discussion_id, after_sequence)` 支持游标 |
| **断言** | 重连后第一条事件 `seq == 6`；总数 = 原总数 - 5；不丢不重 |

### 6.6 `test_cross_discussion_sse_isolation`

| TDD 步骤 | 内容 |
|---|---|
| **Red** | A 的 SSE 推送被 B 的消费者收到 |
| **Green** | `SSEManager` 内部 `channels: dict[discussion_id, set[Queue]]` |
| **Refactor** | 使用 `asyncio.Queue` 实现 pub/sub，广播只遍历对应 discussion_id 的 queue 集合 |
| **断言** | B 的消费者在 A 触发事件后 1s 内 timeout（未收到任何非 heartbeat 事件） |

---

## 7. 测试基础设施

### 7.1 目录结构

```
backend/
├── tests/
│   ├── conftest.py                    # 共享 fixtures (DB, client, mocks)
│   ├── factories.py                   # Test data factories (GuestFactory, DiscussionFactory, ...)
│   ├── test_guest_generator.py        # 7 tests
│   ├── test_orchestrator.py           # 8 tests
│   ├── test_consensus_extractor.py    # 6 tests
│   ├── test_discussion_lifecycle.py   # 7 tests
│   └── test_sse_manager.py           # 6 tests
├── app/
│   └── ... (源码)
└── requirements-dev.txt               # pytest, pytest-asyncio, httpx, pytest-cov
```

### 7.2 共享 Fixtures (`conftest.py`)

| Fixture | Scope | 说明 |
|---|---|---|
| `db_session` | function | SQLite `:memory:` 实例，每个测试独立 |
| `llm_mock` | function | `unittest.mock.AsyncMock`，预设 LLM 调用返回值 |
| `async_client` | function | `httpx.AsyncClient(app=fastapi_app)` |
| `discussion_factory` | session | 创建 Discussion + Guests 的辅助函数 |
| `transcript_factory` | session | 批量创建 TranscriptEntry 的辅助函数 |

### 7.3 Mock 策略

| 依赖 | Mock 方式 | 原因 |
|---|---|---|
| LLM API | `unittest.mock.AsyncMock` | 避免网络依赖 + API Key 泄露 + 测试速度 |
| 数据库 | SQLite `:memory:` | 真实 SQL 行为，零清理成本 |
| 时间 | `freezegun.freeze_time()` | 确定性时间戳断言 |
| UUID | `uuid.uuid4()` (真实) | UUID 格式校验无替代必要 |

### 7.4 运行命令

```bash
# 全量测试
pytest tests/ -v --cov=app --cov-report=term-missing

# 单模块
pytest tests/test_guest_generator.py -v

# 单测试函数 + TDD 模式（检测到失败后停止）
pytest tests/test_orchestrator.py::test_only_one_guest_speaking -x

# 按优先级
pytest tests/ -m "p0" -v   # P0 only
```

---

## 8. CI 集成建议

```yaml
# .github/workflows/test.yml (示意)
jobs:
  backend-tests:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - run: pip install -r requirements-dev.txt
      - run: pytest tests/ -v --cov=app --cov-report=xml --junitxml=report.xml
      - run: pytest tests/ -m "not slow" -v  # PR 检查跳过慢速集成测试

  hidden-cot-check:
    runs-on: ubuntu-latest
    steps:
      - run: |
          # 确保 OpenAPI schema 不含 hidden_cot
          grep -q "hidden_cot" docs/openapi.yaml && echo "FAIL: hidden_cot in OpenAPI" && exit 1 || echo "PASS"
```

---

## TDD 执行建议

1. **每个测试函数严格遵循 Red → Green → Refactor 三步**，提交信息按 `[TDD] test_xxx: Red` / `[TDD] test_xxx: Green` / `[TDD] test_xxx: Refactor` 格式。
2. **P0 模块最先执行**：`test_guest_generator.py` → `test_orchestrator.py`，因为它们定义了核心领域逻辑。
3. **每个 Green 步骤的代码量尽量小**——仅通过当前测试，不过度设计。
4. **Refactor 步骤关注消除重复**：提取公共 fixtures、factory 函数、状态机基类。
5. **LLM Mock 的预设返回值**统一放在 `tests/fixtures/llm_responses/` 目录（JSON 文件），便于审查和维护。
