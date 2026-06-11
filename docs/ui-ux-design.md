# AI Panel Studio — UI/UX 设计文档

> **DDD 阶段交付物** | 设计隐喻：电视演播厅辩论节目

---

## 目录

1. [布局策略](#1-布局策略)
2. [信息可视化](#2-信息可视化)
3. [响应式适配](#3-响应式适配)
4. [组件拆解](#4-组件拆解)
5. [配色与氛围系统](#5-配色与氛围系统)
6. [动效系统](#6-动效系统)
7. [关键交互流程](#7-关键交互流程)
8. [设计决策总结](#8-设计决策总结)

---

## 1. 布局策略

### 1.1 核心设计隐喻

用户不是"参与讨论的人"，而是**"坐在观众席观看一场 AI 自动上演的辩论秀"**。
界面是"看台视角"——从正面观察舞台，所有嘉宾面朝观众。

参考：CNN《The Lead》多嘉宾连线 / 央视《对话》/ Bloomberg 多分析师连线

### 1.2 整体布局（桌面端 1440px+）

```
┌──────────────────────────────────────────────────────────────────────────┐
│  🏠 AI Panel Studio          "AI会取代人类工作吗"    ● Active  Round 8    │
│                                                              [结束讨论]  │
├──────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│   ┌──────────────────────────────────────────────────────────────────┐   │
│   │                       🎬 STUDIO STAGE                            │   │
│   │                                                                  │   │
│   │                    ┌──────────────────┐                          │   │
│   │                    │   🎤 张明远       │  ← HostCard              │   │
│   │                    │   主持人          │    居中、最大、金色边框   │   │
│   │                    │   资深科技记者     │    始终可见              │   │
│   │                    │   [idle] ●       │                          │   │
│   │                    └──────────────────┘                          │   │
│   │                                                                  │   │
│   │   ┌────────────┐     ┌────────────┐     ┌────────────┐          │   │
│   │   │ 💬 李思涵   │     │ 💬 王建国   │     │ 💬 陈雪梅   │          │   │
│   │   │ AI研究员    │     │ 劳动经济学家 │     │ 政策顾问    │          │   │
│   │   │ 乐观派      │     │ 谨慎派      │     │ 务实派      │          │   │
│   │   │ ┌──────────┐│     │ [idle] ●   │     │ [waiting]◐ │          │   │
│   │   │ │"正在组织  ││     │            │     │            │          │   │
│   │   │ │ 关于就业  ││     └────────────┘     └────────────┘          │   │
│   │   │ │ 市场的论点"││     ← ExpertCards: 较小、各自独特色彩边框       │   │
│   │   │ └──────────┘│                                               │   │
│   │   │ [thinking]◉ │                                               │   │
│   │   └────────────┘                                                │   │
│   │                                                                  │   │
│   └──────────────────────────────────────────────────────────────────┘   │
│                                                                          │
│   ┌────────────────────────────────┐  ┌──────────────────────────────┐   │
│   │     📝 LIVE TRANSCRIPT         │  │  📊 REAL-TIME ANALYSIS       │   │
│   │                                │  │                              │   │
│   │  🟡 张明远 | 主持人            │  │  ✅ 共识 (3)                 │   │
│   │  欢迎各位来到今天的圆桌讨论...   │  │  ┌────────────────────────┐  │   │
│   │                                │  │  │ AI监管需分级制度        │  │   │
│   │  🔵 李思涵 | AI研究员          │  │  │ 95% ▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓  │  │   │
│   │  回顾工业革命以来...            │  │  │ 李思涵 ✓ 王建国 ✓ 陈雪梅✓│  │   │
│   │                                │  │  └────────────────────────┘  │   │
│   │  🔴 王建国 | 劳动经济学家       │  │  ┌────────────────────────┐  │   │
│   │  我必须指出这个类比的缺陷...     │  │  │ 教育体系需改革          │  │   │
│   │                                │  │  │ 85% ▓▓▓▓▓▓▓▓▓▓▓▓▓     │  │   │
│   │  🔵 李思涵 | AI研究员  [流式]  │  │  └────────────────────────┘  │   │
│   │  我需要纠正一个认知偏差...█     │  │                              │   │
│   │                                │  │  ⚡ 分歧 (2)                 │   │
│   │  ▼ Auto-scrolling              │  │  ┌────────────────────────┐  │   │
│   │                                │  │  │ 技能断层危机??          │   │
│   │                                │  │  │ sharp ▓▓▓▓▓▓▓▓▓▓▓▓▓▓  │   │
│   │                                │  │  │ 乐观派 ←→ 谨慎派        │   │
│   │                                │  │  └────────────────────────┘  │   │
│   └────────────────────────────────┘  └──────────────────────────────┘   │
│                                                                          │
└──────────────────────────────────────────────────────────────────────────┘
```

**空间分配：**

| 区域 | 占比 | 说明 |
|---|---|---|
| Stage（舞台区） | 上部 35-40% | 用户视线焦点，主持人+嘉宾卡片 |
| Transcript（逐字稿） | 下部左 65-70% | 信息密度最高，独立滚动 |
| Analysis（分析面板） | 下部右 30-35% | 辅助决策，独立滚动 |

### 1.3 主持人 vs 嘉宾视觉区分

| 维度 | 主持人 (Host) | 专家 (Expert) |
|---|---|---|
| 位置 | 舞台中央顶部，略高于嘉宾 | 围绕主持人下方弧形排列 |
| 卡片大小 | 1.2x ~ 1.3x（约 200×260px） | 标准（约 160×200px） |
| 边框 | 金色渐变 (#E8A840 → #C89630)，3px | 各自立场色，2px |
| Avatar | 带🎤图标徽章 | 带立场标签 (正方/反方/中立) |
| 发言高亮 | 金色光晕 + scale(1.05) | 对应颜色光晕 + 边框加粗至 3px |
| 背景 | 深色磨砂玻璃 + 中心聚光灯效果 | 纯深色卡片 |

### 1.4 发言状态视觉反馈

| 状态 | 卡片表现 | 动效 |
|---|---|---|
| `idle` | 常态卡片，边框暗淡 | 无 |
| `thinking` | 底部浮现思考气泡（public_thought） | 边框脉冲 (pulse, 1.5s) + 💭 图标 |
| `speaking` | 放大 highlight，边框加粗+辉光 | 光晕呼吸 (glow-breathing, 3s) |
| `waiting` | 略微变暗，⏳ 冷却图标 | 淡出过渡 (300ms ease-out) |

**简化关键：** 同时只允许 1 人 `speaking`（状态机保证），前端只需 `speakingGuestId` 一个状态即可驱动全部高亮。

---

## 2. 信息可视化

### 2.1 共识卡片

```
┌──────────────────────────────────────┐
│ ✅ 共识                               │
│  AI监管需要分级制度                    │
│                                      │
│  李思涵 ●   王建国 ●   陈雪梅 ●       │  ← 头像+勾号
│  共识强度: 95%  ▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓  │  ← 极简条形
│  首次确认: 讨论第3轮  ·  最近强化: 2分钟前 │
└──────────────────────────────────────┘
```

- 绿色基调 (#50B86C)，强度越高填充越满
- 头像行用嘉宾颜色小圆点 + 勾号
- `is_active=false` 时 50% 透明度（共识被推翻的痕迹）

### 2.2 分歧卡片

```
┌──────────────────────────────────────┐
│ ⚡ 分歧 · sharp                       │
│  关于基本收入的实施路径存在分歧         │
│                                      │
│   支持UBI          反对UBI           │
│   沈一诺 ●         钱伟成 ●           │
│   ▓▓▓▓▓▓▓▓▓▓      ▓▓▓▓▓▓▓▓▓▓▓▓▓    │  ← 对比条形
│                                      │
│   中立/渐进                            │
│   郑佳慧 ●                           │
│   ▓▓▓▓▓▓                             │
└──────────────────────────────────────┘
```

- 暖色系梯度：mild=黄 → moderate=橙 → sharp=红 → fundamental=深红
- 分组对比条形，宽度 = 该方人数比例
- `resolved=true` 时显示 🏳️ + 绿色高亮

### 2.3 Transcript 逐字稿

- 每条消息左侧 4px 颜色条 = 嘉宾颜色（无需头像快速关联）
- 流式消息：闪烁光标 `█` + 浅色背景 + "正在发言..." 标签
- `quote_of` 引用：被引用消息以淡色背景闪现
- 消息附 entry_type 图标：🗣️ speech / ↩️ rebuttal / ➕ supplement / ❓ question
- 自动滚动：默认 ON，用户上滑暂停，右下角 "↓ 回到底部" 浮动按钮
- 轮次分隔线：`── 第 N 轮 ──`

---

## 3. 响应式适配

### 桌面端 (≥ 1280px)
- 完整三区布局（Stage + Transcript + Analysis）
- Analysis 始终可见

### 平板端 (768px ~ 1279px)
- Stage 区压缩，Analysis 变可折叠侧边栏（抽屉式）
- Tab 切换 Transcript / Analysis

### 手机端 (< 768px)

```
┌──────────────────────┐
│ 🏠 AI会取代人类工作吗  │  ← 顶部固定栏
│ ● Active · Round 8   │
├──────────────────────┤
│ ← 横向滑动嘉宾区 →    │  ← Stage (可滚卡片行)
│ [🎤张] [🔵李] [🔴王]  │
├──────────────────────┤
│ 📝 现场转录           │  ← Transcript (主区域)
│ 🔵 李思涵            │
│ 回顾工业革命以来...    │
│ 🔴 王建国            │
│ 我必须指出这个类比...  │
├──────────────────────┤
│ 📊 分析 (3共识/2分歧) ▲│  ← Bottom Sheet (可展开)
└──────────────────────┘
```

- Stage 区横向 Snap Scroll
- Transcript 全宽单列
- Analysis 底部折叠面板
- **每个区域独立滚动**

---

## 4. 组件拆解

### 4.1 组件树

```
App
├── AppHeader                    # 顶部导航栏
│   ├── Logo
│   └── GlobalControls           # 新建讨论 / 设置
│
├── DiscussionView               # 演播厅视图 (路由: /discussions/:id)
│   │
│   ├── DiscussionHeader         # 讨论信息栏
│   │   ├── TopicDisplay         # 话题 + 状态标签
│   │   ├── RoundIndicator       # 当前轮次 / 总轮次
│   │   └── ActionButtons        # [开始] [结束] [导出]
│   │
│   ├── StudioStage              # 🎬 演播厅舞台
│   │   ├── StageLighting        # 氛围背景（径向渐变、暗角）
│   │   ├── HostCard             # 主持人卡片（居中、特大、金色）
│   │   │   ├── GuestAvatar      # 头像 + 角色徽章
│   │   │   ├── StatusBadge      # 状态指示器
│   │   │   └── ThinkingBubble   # 公开思考气泡
│   │   └── GuestCard[]          # 专家卡片列表
│   │       ├── GuestAvatar
│   │       ├── StatusBadge
│   │       ├── ThinkingBubble
│   │       └── SpeechGlow       # 发言辉光效果
│   │
│   ├── LiveTranscript           # 📝 现场逐字稿
│   │   ├── TranscriptControls   # 自动滚动开关 / 过滤
│   │   ├── TranscriptEntry[]    # 单条发言
│   │   │   ├── GuestColorBar    # 左侧 4px 颜色条
│   │   │   ├── EntryHeader      # 姓名 + 职业 + 类型图标
│   │   │   ├── EntryContent     # Markdown 内容
│   │   │   ├── QuoteIndicator   # "引用 @某人"
│   │   │   └── StreamingCursor  # █ 光标
│   │   ├── RoundDivider         # "── 第 N 轮 ──"
│   │   └── ScrollToBottom       # "↓ 回到底部"
│   │
│   ├── AnalysisPanel            # 📊 实时分析
│   │   ├── PanelTabs            # [共识] [分歧]
│   │   ├── ConsensusList
│   │   │   └── ConsensusCard
│   │   │       ├── AgreementBar # 强度条
│   │   │       └── GuestRow     # 同意嘉宾头像行
│   │   └── DivergenceList
│   │       └── DivergenceCard
│   │           ├── SeverityBadge
│   │           └── PartyBar     # 各方对比条形
│   │
│   └── SummaryModal             # 总结弹窗
│       ├── SummaryContent       # Markdown 全文
│       ├── KeyFindings          # 关键发现
│       └── GuestContributions   # 嘉宾贡献度
│
├── DiscussionList               # 首页讨论列表 (路由: /)
│   ├── DiscussionCard[]
│   └── CreateDiscussionButton
│
└── SSEProvider                  # (非视觉) SSE 连接管理器
    └── useSSE()                 # Custom Hook / Composable
```

### 4.2 组件职责摘要

| 组件 | 职责 | 关键 Props |
|---|---|---|
| **StudioStage** | 舞台区容器，管理氛围背景 | `discussionId` |
| **HostCard** | 主持人专属卡片，金色辉光 | `guest, isSpeaking` |
| **GuestCard** | 专家卡片，立场色边框，状态动画 | `guest, isSpeaking` |
| **StatusBadge** | 四态指示灯 + 动效 | `status: GuestStatus` |
| **ThinkingBubble** | public_thought 摘要气泡 | `thought, confidence` |
| **LiveTranscript** | 消息列表容器，自动滚动+流式追加 | `discussionId, entries[]` |
| **TranscriptEntry** | 单条消息（颜色条+流式光标+引用） | `entry, isStreaming` |
| **ConsensusCard** | 共识卡片（头像行+强度条） | `consensus, guests[]` |
| **DivergenceCard** | 分歧卡片（对立条形+化解状态） | `divergence, guests[]` |
| **SSEProvider** | EventSource 封装，type→store 分发 | `discussionId` |

---

## 5. 配色与氛围系统

### 5.1 演播厅暗色主题

```css
--bg-primary:       #0a0a0f;    /* 极暗蓝黑 - 演播厅背景 */
--bg-secondary:     #141420;    /* 卡片底色 */
--bg-tertiary:      #1e1e30;    /* 悬浮态 */
--text-primary:     #e8e8ed;    /* 主文字 */
--text-secondary:   #9090a0;    /* 次要文字 */
--border-default:   #2a2a3a;    /* 默认边框 */
--gold:             #e8a840;    /* 主持人/强调 */
--stage-glow: radial-gradient(ellipse at 50% 30%, rgba(232,168,64,0.08) 0%, transparent 70%);
```

### 5.2 嘉宾颜色 Token

```
--color-host:       #e8a840    /* 金色 - 主持人固定 */
--color-expert-0:   #4a90d9    /* 蓝 */
--color-expert-1:   #d94a4a    /* 红 */
--color-expert-2:   #50b86c    /* 绿 */
--color-expert-3:   #7b61ff    /* 紫 */
--color-expert-4:   #ff8c42    /* 橙 */
--color-expert-5:   #20b2aa    /* 青 */
--color-expert-6:   #ff6b6b    /* 珊瑚 */
--color-expert-7:   #b8860b    /* 暗金 */
```

色相间隔 ≥ 60°，确保 8 人同台时视觉区分度足够。

---

## 6. 动效系统

| 动效 | 用途 | 实现 |
|---|---|---|
| `pulse-border` | thinking 状态 | `@keyframes pulse { 0%,100%{opacity:1} 50%{opacity:0.4} }` |
| `glow-breathing` | speaking 状态 | `box-shadow 0→12px→0` 循环 (3s) |
| `fade-in-up` | 新消息进入 | `translateY(10px)→0` + `opacity 0→1` (300ms) |
| `slide-in-right` | 共识/分歧更新 | 从右侧滑入 (200ms ease-out) |
| `shimmer` | 流式等待中 | 渐变左→右扫过 |
| `round-transition` | 轮次切换 | scale + fade 叠加文字 (1.5s) |

---

## 7. 关键交互流程

### 7.1 创建讨论 → 观看讨论

```
首页(讨论列表) → [新建讨论] → 填写话题/参数 → [生成嘉宾]
→ 展示阵容 → 确认/重新生成 → [开始讨论]
→ 演播厅视图 → SSE 连接 → 观看 → [结束讨论] → 查看总结
```

### 7.2 SSE 事件 → UI 更新

```
snapshot_update → GuestStore.updateSnapshot() → GuestCard 重渲染
transcript_delta → TranscriptStore.appendDelta() → 追加文字+闪烁光标
transcript_append → TranscriptStore.finalizeEntry() → 光标消失+自动滚动
consensus_update → AnalysisStore.replace() → ConsensusCard slide-in
divergence_update → AnalysisStore.replace() → DivergenceCard slide-in
discussion_status_change → DiscussionStore.setStatus() → 总结弹窗
```

---

## 8. 设计决策总结

| # | 决策 | 理由 |
|---|---|---|
| 1 | **电视演播厅隐喻** | 用户是观众，不是参与者——让用户"看戏" |
| 2 | **主持人居中放大** | 建立清晰视觉等级——主持人是讨论的锚点 |
| 3 | **同时只有 1 人 speaking** | 简化前端高亮逻辑 + 符合后端状态机 |
| 4 | **Transcript 左侧 4px 颜色条** | 无需头像快速关联，信息密度高 |
| 5 | **各区域独立滚动** | 舞台区始终可见，不被 Transcript 滚走 |
| 6 | **统一 SSE 事件通道** | 一个 EventSource + type 路由 → 多 store |
| 7 | **暗色主题默认** | 演播厅氛围 + 颜色标识在暗底更突出 |
| 8 | **CSR 优先** | MVP 不引入 SSR，原生 HTML/CSS/JS + 轻量状态管理 |
