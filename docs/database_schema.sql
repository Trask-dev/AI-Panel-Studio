-- =============================================================================
-- AI Panel Studio — SQLite 数据库 Schema
-- =============================================================================
-- 版本: 1.0.0
-- 日期: 2026-06-11
-- 技术栈: Python FastAPI + SQLAlchemy + SQLite 3.38+
-- 编码: UTF-8
--
-- 设计原则:
--   1. UUID 主键统一使用 TEXT 存储（可读性 > 二进制性能）
--   2. 布尔值使用 INTEGER (0/1)，SQLite 原生无 BOOLEAN 类型
--   3. 时间统一使用 ISO8601 TEXT 格式 (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
--      - 理由: 人类可读、自然支持排序比较、易于导出/序列化、跨平台无歧义
--      - Unix 毫秒时间戳备选: 若需高精度时序，可新增 _ts_ms 列
--   4. JSON 字段使用 TEXT 存储，SQLite 3.38+ 原生支持 json_extract() / json_set()
--   5. 所有外键显式定义 ON DELETE 策略
--   6. 核心查询路径建立复合索引
--   7. 不设物理删除，使用 is_active / status 字段实现软删除
-- =============================================================================

-- -----------------------------------------------------------------------------
-- Pragma 设置（每个新连接必须执行）
-- -----------------------------------------------------------------------------
PRAGMA journal_mode       = WAL;       -- Write-Ahead Logging: 支持并发读写
PRAGMA foreign_keys       = ON;        -- 强制外键约束（SQLite 默认关闭！）
PRAGMA busy_timeout       = 5000;      -- 写锁等待 5 秒后超时
PRAGMA cache_size         = -64000;    -- 缓存 64MB（以 KB 为单位，负数=绝对值）
PRAGMA temp_store         = MEMORY;    -- 临时表存储在内存中
PRAGMA mmap_size          = 268435456; -- 内存映射 I/O 256MB
PRAGMA synchronous        = NORMAL;    -- WAL 模式下 NORMAL 即可保证安全


-- =============================================================================
-- 1. discussions — 讨论会话主表
-- =============================================================================
-- 生命周期: setup -> active -> summarizing -> finished
-- 每个讨论包含 1 个主持人 + 2~8 个专家嘉宾
-- =============================================================================
CREATE TABLE IF NOT EXISTS discussions (
    id                  TEXT NOT NULL PRIMARY KEY,          -- UUID v4 (Python: str(uuid.uuid4()))
    topic               TEXT NOT NULL,                      -- 讨论话题，1-200 字符
    topic_description   TEXT,                               -- 话题补充背景，供 LLM 构建上下文
    host_style          TEXT NOT NULL DEFAULT 'neutral'     -- 主持风格
                        CHECK(host_style IN ('neutral', 'provocative', 'socratic', 'humorous')),
    expert_count        INTEGER NOT NULL                    -- 专家人数（不含主持人）
                        CHECK(expert_count >= 2 AND expert_count <= 8),
    status              TEXT NOT NULL DEFAULT 'setup'       -- 当前状态
                        CHECK(status IN ('setup', 'active', 'summarizing', 'finished')),
    round_count         INTEGER NOT NULL DEFAULT 0,         -- 已完成轮次计数
    max_rounds          INTEGER,                            -- 轮次上限，NULL=无限制
    started_at          TEXT,                               -- 讨论开始时间 (ISO8601)
    finished_at         TEXT,                               -- 讨论结束时间 (ISO8601)
    llm_model           TEXT NOT NULL,                      -- LLM 模型标识 (如 claude-sonnet-4-20250514)
    llm_config          TEXT NOT NULL DEFAULT '{}',         -- LLM 调用参数 JSON {temperature, max_tokens, ...}
    interjection_mode   TEXT NOT NULL DEFAULT 'moderated'   -- 插话模式
                        CHECK(interjection_mode IN ('moderated', 'free', 'hybrid')),
    created_at          TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    updated_at          TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);

-- 索引：按状态筛选（首页列表只查 active/finished）
CREATE INDEX IF NOT EXISTS idx_discussions_status ON discussions(status);
-- 索引：按创建时间排序（首页列表按最新排列）
CREATE INDEX IF NOT EXISTS idx_discussions_created_at ON discussions(created_at DESC);


-- =============================================================================
-- 2. guests — 嘉宾/角色表
-- =============================================================================
-- 关联到 discussion，包含人设、职业、立场、颜色标识
-- role: host(主持人, 每讨论唯一) / expert(专家, 2~8 人)
-- status 状态机: idle -> thinking -> speaking -> waiting
-- =============================================================================
CREATE TABLE IF NOT EXISTS guests (
    id                  TEXT NOT NULL PRIMARY KEY,          -- UUID v4
    discussion_id       TEXT NOT NULL,                      -- FK -> discussions.id
    role                TEXT NOT NULL                       -- 角色类型
                        CHECK(role IN ('host', 'expert')),
    name                TEXT NOT NULL,                      -- 嘉宾姓名，1-50 字符
    title               TEXT,                               -- 职业/头衔，如"AI 伦理研究员"
    bio                 TEXT,                               -- 简短背景介绍 (1-3 句)
    stance              TEXT NOT NULL,                      -- 立场描述，如"强烈支持 AI 发展"
    stance_label        TEXT,                               -- 立场短标签: 正方 / 反方 / 中立观察者
    color               TEXT NOT NULL,                      -- 专属颜色 Hex #RRGGBB
    avatar_url          TEXT,                               -- 头像 URL（后期集成 DiceBear）
    status              TEXT NOT NULL DEFAULT 'idle'        -- 当前行为状态
                        CHECK(status IN ('idle', 'thinking', 'speaking', 'waiting')),
    speech_order        INTEGER NOT NULL,                   -- 阵容展示顺序 (主持人=0)
    persona_prompt      TEXT,                               -- LLM 人格提示词片段
    is_active           INTEGER NOT NULL DEFAULT 1          -- 软删除标记 0=禁用 1=启用
                        CHECK(is_active IN (0, 1)),
    created_at          TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    updated_at          TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),

    FOREIGN KEY (discussion_id) REFERENCES discussions(id) ON DELETE CASCADE
);

-- 索引：按讨论拉取嘉宾阵容（最高频查询）
CREATE INDEX IF NOT EXISTS idx_guests_discussion ON guests(discussion_id, speech_order);
-- 索引：按讨论+角色查主持人
CREATE INDEX IF NOT EXISTS idx_guests_discussion_role ON guests(discussion_id, role);
-- 索引：按讨论+状态（活跃嘉宾状态查询）
CREATE INDEX IF NOT EXISTS idx_guests_discussion_status ON guests(discussion_id, status);


-- =============================================================================
-- 3. transcript_entries — 发言/转录记录表（核心大表）
-- =============================================================================
-- 这是最高频写入和查询的表。
-- 存储所有公开可见的发言内容，不含"举手"等内部事件。
-- 通过 guest_id 关联 Guest 以区分主持人/专家。
-- 流式输出: LLM 先创建 is_final=0 的记录，逐 token 更新 content，结束后置 is_final=1。
-- =============================================================================
CREATE TABLE IF NOT EXISTS transcript_entries (
    id                  TEXT NOT NULL PRIMARY KEY,          -- UUID v4
    discussion_id       TEXT NOT NULL,                      -- FK -> discussions.id
    guest_id            TEXT NOT NULL,                      -- FK -> guests.id
    sequence_number     INTEGER NOT NULL,                   -- 全局递增序号（讨论内唯一）
    round_number        INTEGER NOT NULL,                   -- 所属轮次号
    entry_type          TEXT NOT NULL                       -- 发言类型
                        CHECK(entry_type IN (
                            'opening_statement',            -- 主持人开场白
                            'position_statement',           -- 专家立场陈述（第一轮）
                            'speech',                       -- 常规发言
                            'interjection',                 -- 插话/打断
                            'rebuttal',                     -- 反驳
                            'supplement',                   -- 补充观点
                            'question',                     -- 主持人提问
                            'answer',                       -- 专家回答
                            'closing_statement',            -- 总结陈述
                            'host_summary'                  -- 主持人总结
                        )),
    content             TEXT NOT NULL,                      -- 公开发言内容 (Markdown)
    quote_of            TEXT,                               -- 引用前序发言的 ID (FK -> transcript_entries.id, 自引用)
    is_final            INTEGER NOT NULL DEFAULT 0          -- 是否为本轮最终定稿 0=流式中 1=已完成
                        CHECK(is_final IN (0, 1)),
    spoken_at           TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    created_at          TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),

    FOREIGN KEY (discussion_id) REFERENCES discussions(id) ON DELETE CASCADE,
    FOREIGN KEY (guest_id)       REFERENCES guests(id)       ON DELETE CASCADE,
    FOREIGN KEY (quote_of)       REFERENCES transcript_entries(id) ON DELETE SET NULL
);

-- ★ 核心索引 1: 按讨论+序号拉取完整时间线（演播厅最核心查询）
CREATE INDEX IF NOT EXISTS idx_transcript_discussion_seq
    ON transcript_entries(discussion_id, sequence_number);

-- ★ 核心索引 2: 按讨论+时间拉取对话流（满足用户要求的 discussion_id + created_at 联合索引）
CREATE INDEX IF NOT EXISTS idx_transcript_discussion_created
    ON transcript_entries(discussion_id, created_at);

-- 索引：按讨论+轮次查询（轮次摘要）
CREATE INDEX IF NOT EXISTS idx_transcript_discussion_round
    ON transcript_entries(discussion_id, round_number);

-- 索引：按嘉宾查询所有发言
CREATE INDEX IF NOT EXISTS idx_transcript_guest ON transcript_entries(guest_id);

-- 索引：按讨论+类型筛选（如只看 host_summary）
CREATE INDEX IF NOT EXISTS idx_transcript_discussion_type
    ON transcript_entries(discussion_id, entry_type);

-- 唯一约束：同一讨论内 sequence_number 唯一（防止并发写入乱序）
CREATE UNIQUE INDEX IF NOT EXISTS uq_transcript_discussion_seq
    ON transcript_entries(discussion_id, sequence_number);


-- =============================================================================
-- 4. thinking_snapshots — 嘉宾思考状态快照（安全敏感表）
-- =============================================================================
-- ⚠️ 安全警告: hidden_cot 字段存储 LLM 完整推理链，绝对禁止发送到前端！
-- 前端仅接收 public_thought (公开思考摘要)。
-- 每次嘉宾状态变化创建一条新快照，is_latest 标记最新一条。
-- 后端 API 序列化时必须使用不包含 hidden_cot 的 Public Schema。
-- =============================================================================
CREATE TABLE IF NOT EXISTS thinking_snapshots (
    id                  TEXT NOT NULL PRIMARY KEY,          -- UUID v4
    discussion_id       TEXT NOT NULL,                      -- FK -> discussions.id
    guest_id            TEXT NOT NULL,                      -- FK -> guests.id
    status              TEXT NOT NULL CHECK(status IN ('idle', 'thinking', 'speaking', 'waiting')),  -- 快照时的嘉宾状态
    public_thought      TEXT,                               -- ✅ 公开思考摘要（发送前端）
    hidden_cot          TEXT,                               -- ❌ 隐藏推理链（绝不发送前端！仅调试用）
    confidence          REAL CHECK(confidence >= 0.0 AND confidence <= 1.0),  -- LLM 确信度 0.0~1.0
    intent              TEXT CHECK(intent IN ('raise_hand','rebut','supplement','answer','concede','stay_silent')),  -- 发言意图
    snapshot_at         TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    is_latest           INTEGER NOT NULL DEFAULT 1 CHECK(is_latest IN (0, 1)),  -- 是否最新快照 0=历史 1=当前
    created_at          TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),

    FOREIGN KEY (discussion_id) REFERENCES discussions(id) ON DELETE CASCADE,
    FOREIGN KEY (guest_id)       REFERENCES guests(id)       ON DELETE CASCADE
);

-- ★ 核心索引: 按讨论+嘉宾+最新标记查当前状态（状态小窗轮询最频繁的查询）
CREATE INDEX IF NOT EXISTS idx_thinking_latest
    ON thinking_snapshots(discussion_id, guest_id, is_latest)
    WHERE is_latest = 1;                                   -- 部分索引，大幅减少索引大小

-- 辅助索引: 按讨论查所有快照
CREATE INDEX IF NOT EXISTS idx_thinking_discussion
    ON thinking_snapshots(discussion_id, snapshot_at);


-- =============================================================================
-- 5. consensus_items — 共识项
-- =============================================================================
-- 讨论过程中 LLM 动态识别各方达成的共识。
-- agreed_guests 存 JSON 数组，source_entries 溯源到具体发言。
-- is_active 支持共识反转（后续讨论可能推翻之前的共识）。
-- =============================================================================
CREATE TABLE IF NOT EXISTS consensus_items (
    id                   TEXT NOT NULL PRIMARY KEY,         -- UUID v4
    discussion_id        TEXT NOT NULL,                     -- FK -> discussions.id
    content              TEXT NOT NULL,                     -- 共识内容描述
    agreed_guests        TEXT NOT NULL,                     -- JSON 数组: ["guest_uuid_1", "guest_uuid_2"]
    confidence           REAL NOT NULL DEFAULT 1.0          -- 共识强度 0.0~1.0 (全员=1.0)
                         CHECK(confidence >= 0.0 AND confidence <= 1.0),
    first_identified_at  TEXT NOT NULL,                     -- 首次识别时间 (ISO8601)
    last_reinforced_at   TEXT NOT NULL,                     -- 最近强化时间 (ISO8601)
    is_active            INTEGER NOT NULL DEFAULT 1         -- 当前仍为共识 0=已推翻 1=活跃
                         CHECK(is_active IN (0, 1)),
    source_entries       TEXT,                              -- JSON 数组: 支撑此共识的 transcript_entries ID
    created_at           TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    updated_at           TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),

    FOREIGN KEY (discussion_id) REFERENCES discussions(id) ON DELETE CASCADE
);

-- 索引：按讨论+活跃状态查当前共识面板
CREATE INDEX IF NOT EXISTS idx_consensus_discussion_active
    ON consensus_items(discussion_id, is_active);

-- 索引：按时间排序（共识涌现的时间线）
CREATE INDEX IF NOT EXISTS idx_consensus_discussion_time
    ON consensus_items(discussion_id, first_identified_at);


-- =============================================================================
-- 6. divergence_items — 分歧项
-- =============================================================================
-- 讨论过程中 LLM 动态识别各方存在的分歧。
-- parties 存 JSON 数组，每个元素包含 stance 和 guest_ids。
-- 支持分歧化解追踪 (resolved / resolved_at / resolution_note)。
-- =============================================================================
CREATE TABLE IF NOT EXISTS divergence_items (
    id                   TEXT NOT NULL PRIMARY KEY,         -- UUID v4
    discussion_id        TEXT NOT NULL,                     -- FK -> discussions.id
    content              TEXT NOT NULL,                     -- 分歧内容描述
    parties              TEXT NOT NULL,                     -- JSON: [{"stance":"...","guest_ids":["..."]}]
    severity             TEXT NOT NULL DEFAULT 'moderate'   -- 分歧程度
                         CHECK(severity IN ('mild', 'moderate', 'sharp', 'fundamental')),
    first_identified_at  TEXT NOT NULL,                     -- 首次识别时间 (ISO8601)
    last_updated_at      TEXT NOT NULL,                     -- 最近更新时间 (ISO8601)
    is_active            INTEGER NOT NULL DEFAULT 1         -- 当前仍为活跃分歧
                         CHECK(is_active IN (0, 1)),
    resolved             INTEGER NOT NULL DEFAULT 0         -- 是否已化解 0=未化解 1=已化解
                         CHECK(resolved IN (0, 1)),
    resolved_at          TEXT,                              -- 化解时间 (ISO8601)
    resolution_note      TEXT,                              -- 化解说明
    source_entries       TEXT,                              -- JSON 数组: 支撑此分歧的 transcript_entries ID
    created_at           TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    updated_at           TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),

    FOREIGN KEY (discussion_id) REFERENCES discussions(id) ON DELETE CASCADE
);

-- 索引：按讨论+活跃状态查当前分歧面板
CREATE INDEX IF NOT EXISTS idx_divergence_discussion_active
    ON divergence_items(discussion_id, is_active);

-- 索引：按讨论+化解状态（总结时查询已化解的分歧）
CREATE INDEX IF NOT EXISTS idx_divergence_discussion_resolved
    ON divergence_items(discussion_id, resolved);

-- 索引：按程度筛选
CREATE INDEX IF NOT EXISTS idx_divergence_discussion_severity
    ON divergence_items(discussion_id, severity);


-- =============================================================================
-- 7. discussion_summaries — 讨论总结
-- =============================================================================
-- 与 Discussion 一对一（UNIQUE 约束）。
-- 结构化的子字段支持前端可视化（词云、贡献度图表等），避免前端解析 content。
-- =============================================================================
CREATE TABLE IF NOT EXISTS discussion_summaries (
    id                   TEXT NOT NULL PRIMARY KEY,         -- UUID v4
    discussion_id        TEXT NOT NULL UNIQUE,              -- FK -> discussions.id (一对一)
    content              TEXT NOT NULL,                     -- 主持人自然语言总结全文 (Markdown)
    key_findings         TEXT,                              -- JSON 数组: ["发现1", "发现2", ...]
    consensus_summary    TEXT,                              -- JSON: 共识汇总 (聚合所有 ConsensusItem)
    divergence_summary   TEXT,                              -- JSON: 分歧汇总 (聚合所有 DivergenceItem)
    guest_contributions  TEXT,                              -- JSON: [{"guest_id":"...","keywords":[],"highlights":[]}]
    generation_model     TEXT NOT NULL,                     -- 生成总结的 LLM 模型
    generation_cost      TEXT,                              -- JSON: {tokens_in, tokens_out, latency_ms, ...}
    created_at           TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),

    FOREIGN KEY (discussion_id) REFERENCES discussions(id) ON DELETE CASCADE
);

-- 索引：按讨论查总结（虽然 UNIQUE 已建索引，显式声明便于阅读）
CREATE INDEX IF NOT EXISTS idx_summary_discussion ON discussion_summaries(discussion_id);


-- =============================================================================
-- 辅助视图（可选，用于调试和分析）
-- =============================================================================

-- 视图: 讨论概览（首页列表接口可直接查询此视图）
CREATE VIEW IF NOT EXISTS v_discussion_overview AS
SELECT
    d.id,
    d.topic,
    d.status,
    d.expert_count,
    d.round_count,
    d.max_rounds,
    d.host_style,
    d.interjection_mode,
    d.llm_model,
    d.started_at,
    d.finished_at,
    d.created_at,
    -- 统计发言总数
    (SELECT COUNT(*) FROM transcript_entries te WHERE te.discussion_id = d.id) AS total_entries,
    -- 统计共识数
    (SELECT COUNT(*) FROM consensus_items ci WHERE ci.discussion_id = d.id AND ci.is_active = 1) AS active_consensus_count,
    -- 统计活跃分歧数
    (SELECT COUNT(*) FROM divergence_items di WHERE di.discussion_id = d.id AND di.is_active = 1 AND di.resolved = 0) AS active_divergence_count,
    -- 主持人姓名
    (SELECT g.name FROM guests g WHERE g.discussion_id = d.id AND g.role = 'host') AS host_name
FROM discussions d;

-- 视图: 嘉宾发言统计（总结时分析各嘉宾贡献度）
CREATE VIEW IF NOT EXISTS v_guest_speech_stats AS
SELECT
    g.discussion_id,
    g.id AS guest_id,
    g.name,
    g.role,
    g.color,
    COUNT(te.id) AS speech_count,
    -- 各类发言次数
    SUM(CASE WHEN te.entry_type = 'rebuttal' THEN 1 ELSE 0 END) AS rebuttal_count,
    SUM(CASE WHEN te.entry_type = 'supplement' THEN 1 ELSE 0 END) AS supplement_count,
    SUM(CASE WHEN te.entry_type = 'interjection' THEN 1 ELSE 0 END) AS interjection_count,
    -- 平均发言长度
    ROUND(AVG(LENGTH(te.content)), 0) AS avg_content_length
FROM guests g
LEFT JOIN transcript_entries te ON te.guest_id = g.id
WHERE g.is_active = 1
GROUP BY g.discussion_id, g.id, g.name, g.role, g.color
ORDER BY g.discussion_id, g.speech_order;


-- =============================================================================
-- 设计决策说明 (Design Rationale)
-- =============================================================================

-- 1. 时间格式选择：ISO8601 TEXT vs Unix 时间戳
--    选择 ISO8601 TEXT:
--    - 人类可读，调试时直接看懂时间
--    - 字符串自然排序 = 时间排序 ('2026-06-11T10:30:00Z' > '2026-06-11T09:00:00Z')
--    - 易于序列化/导出（Markdown/PDF 报告不需要转换）
--    - SQLite 的 strftime() 函数原生支持 ISO8601 格式化
--    - 精度到秒，满足 MVP 需求。如需毫秒精度可改用 strftime('%Y-%m-%dT%H:%M:%fZ')

-- 2. UUID 存储格式
--    选择 TEXT:
--    - 可读性优先于存储效率（SQLite 无原生 UUID 类型）
--    - Python uuid.uuid4() 直接转 str 即可，无需转换
--    - 36 字符的 UUID 对 SQLite 的索引效率影响可忽略（通常缓存整个页）

-- 3. 外键级联策略
--    ON DELETE CASCADE:
--    - discussions 删除时自动清理所有子表数据
--    - 符合业务语义：讨论被删除，其嘉宾/发言/共识/分歧/总结全部失效
--    ON DELETE SET NULL:
--    - transcript_entries.quote_of: 被引用的发言被删除时，引用方不删除，只是断链

-- 4. 多讨论数据隔离
--    通过 discussion_id 实现逻辑隔离:
--    - 所有子表均以 discussion_id 为第一索引列
--    - 所有 API 查询强制带 discussion_id 条件
--    - SSE channel 按 discussion_id 独立建立 asyncio.Queue
--    - SQLite 单文件部署，所有讨论共库但逻辑完全隔离

-- 5. transcript_entries 索引策略
--    核心查询: "获取某讨论从第 N 条开始的后续发言"（演播厅增量拉取）
--    - idx_transcript_discussion_seq(discussion_id, sequence_number):
--      对此查询最优，覆盖索引直接按序扫描，无需回表排序
--    - idx_transcript_discussion_created(discussion_id, created_at):
--      用户要求的联合索引，按时间范围查询时高效
--    - uq_transcript_discussion_seq(discussion_id, sequence_number):
--      唯一约束防并发写入乱序，同时建立唯一索引加速等值查询

-- 6. 流式输出支持
--    transcript_entries.is_final 字段专为流式场景设计:
--    1. LLM 开始生成 -> INSERT is_final=0, content='开头...'
--    2. 每个 token -> UPDATE content = content || new_token （通过 SSE 推前端）
--    3. 生成完成 -> UPDATE is_final=1
--    前端渲染逻辑: is_final=0 时显示闪烁光标，is_final=1 时光标消失

-- 7. hidden_cot 安全性
--    thinking_snapshots.hidden_cot 是安全敏感字段:
--    - 存储层: 独立字段，注释明确标注 ❌
--    - Schema 层: ThinkingSnapshotPublic（排除 hidden_cot）vs ThinkingSnapshotInternal（含 hidden_cot）
--    - API 层: 所有公开端点强制使用 Public Schema
--    - SSE 层: 推送前显式过滤
--    - 导出层: 导出 Markdown/PDF 时排除此字段
--    详见 docs/domain-model.md §1.4

-- 8. JSON 字段设计
--    复杂结构使用 TEXT(J)SON，核心查询列独立:
--    - consensus_items.agreed_guests: JSON 数组 -> 列独立，可用 json_extract() 查询
--    - divergence_items.parties: JSON 对象数组 -> 列独立，可用 json_each() 展开
--    - discussions.llm_config: JSON 对象 -> 列独立，可用 json_extract() 取特定参数
--    原则: 如果需要 WHERE/JOIN 的字段，一定要独立成列。JSON 仅存辅助元数据。

-- 9. 索引部分索引 (Partial Index)
--    idx_thinking_latest 使用 WHERE is_latest = 1 条件:
--    - 只索引最新快照，索引大小 = 活跃嘉宾数 × 1 (vs 全表)
--    - 大幅减少索引写入开销（快照表写入频繁）
--    - 查询 "各嘉宾当前状态" 时直接命中此索引

-- 10. 视图用于分析
--     v_discussion_overview: 首页列表的聚合查询视图
--     v_guest_speech_stats: 总结时分析各嘉宾贡献度
--     视图不存储数据，仅简化应用层 SQL。若性能为瓶颈，可改为物化视图（触发器维护实体表）。

-- 11. 扩展性预留
--     - 多模态: 可在 transcript_entries 增加 media_type / media_url 列
--     - 多语言: discussions 增加 locale 列，guest 增加 language 列
--     - 用户系统: 增加 users 表，discussions 增加 created_by 外键
--     - 讨论模板: discussions 增加 template_id 外键，引用 discussion_templates 表
--     - 导出审计: 增加 export_logs 表记录每次导出操作
