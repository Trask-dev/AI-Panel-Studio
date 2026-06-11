# AI Panel Studio — UI 搭建执行计划

> **DDD 第二阶段** | 纯 HTML/CSS 视觉实现 | 暂不写 JS

---

## 目录

1. [文件结构](#文件结构)
2. [执行步骤 (11 Steps)](#执行步骤)
   - Step 1: CSS 设计 Token 体系
   - Step 2: 顶层页面骨架
   - Step 3: AppHeader
   - Step 4: StudioStage
   - Step 5: GuestCard 精细样式
   - Step 6: LiveTranscript
   - Step 7: AnalysisPanel
   - Step 8: 动效系统
   - Step 9: DiscussionSummary 弹窗
   - Step 10: DiscussionList 首页
   - Step 11: 响应式微调
3. [执行顺序依赖图](#执行顺序)
4. [响应式断点策略](#响应式断点)
5. [最终验证清单](#验证清单)

---

## 文件结构

```
frontend/
├── index.html                    # 主页面（演播厅视图 + 讨论列表）
├── css/
│   ├── reset.css                 # CSS Reset
│   ├── tokens.css                # 设计 Token（颜色、间距、字体、阴影）
│   ├── layout.css                # 顶层 Grid 布局
│   ├── components.css            # 所有组件样式
│   ├── animations.css            # 6 种关键帧动画
│   └── responsive.css            # 媒体查询
└── img/
```

---

## Step 1: CSS 设计 Token 体系

**产出**: `reset.css` + `tokens.css`

```css
:root {
  --bg-primary: #0a0a0f;
  --bg-secondary: #141420;
  --bg-tertiary: #1e1e30;
  --text-primary: #e8e8ed;
  --text-secondary: #9090a0;
  --border-default: #2a2a3a;
  --gold: #e8a840;
  --color-host: #e8a840;
  --color-expert-0 ~ 7: #4a90d9 / #d94a4a / #50b86c / #7b61ff / #ff8c42 / #20b2aa / #ff6b6b / #b8860b
  --space-xs~2xl: 4px~48px
  --radius-sm~full: 6px~9999px
  --content-max-width: 1920px
}
```

---

## Step 2: 顶层页面骨架

**产出**: `index.html` + `layout.css`

```
┌──────────────────────────────────────┐
│         .app (100vh, flex-col)       │
│  ┌────────────────────────────────┐  │
│  │   .app-header (56px fixed)     │  │
│  ├────────────────────────────────┤  │
│  │   .studio-view (flex: 1)       │  │
│  │  ┌──────────────────────────┐  │  │
│  │  │ .studio-stage (35%)      │  │  │
│  │  ├──────────────────────────┤  │  │
│  │  │ .studio-bottom (65%)     │  │  │
│  │  │ ┌──────────┬───────────┐ │  │  │
│  │  │ │Transcript│ Analysis  │ │  │  │
│  │  │ │  (1fr)   │ (360px)   │ │  │  │
│  │  │ └──────────┴───────────┘ │  │  │
│  │  └──────────────────────────┘  │  │
│  └────────────────────────────────┘  │
└──────────────────────────────────────┘
```

**CSS 关键**: `height: 100vh; overflow: hidden` 禁止整页滚动，子区域各自 `overflow-y: auto`

---

## Step 3: AppHeader

三栏 Flex 布局：左 Logo | 中标题+状态 | 右按钮

## Step 4: StudioStage

- 暗色背景 + 径向光晕 (`radial-gradient`)
- `stage-host-area`: 主持人居中
- `stage-experts-row`: Flex 行排列专家，`flex-wrap: wrap`

## Step 5: GuestCard

四种状态：
| 状态 | 样式 | 动效 |
|---|---|---|
| idle | 常态 | 无 |
| thinking | 底部思考气泡 | `pulse-border` (1.5s) |
| speaking | 辉光 + scale(1.05) | `glow-breathing` (3s) |
| waiting | opacity 0.7 | 过渡 (0.3s) |

HostCard: `min-width: 200px`, 金色渐变边框 3px
ExpertCard: `min-width: 160px`, 立场色边框 2px

Avatar: 纯 CSS 圆形 + `background: var(--guest-color)` + 文字首字母

## Step 6: LiveTranscript

- 独立滚动区域
- 每条消息: Flex 行，左侧 4px 颜色条
- 流式消息: 虚线边框 + 闪烁光标 `█`
- 轮次分隔线: `── 第 N 轮 ──`
- 浮动按钮: `↓ 回到底部`

## Step 7: AnalysisPanel

- Tab 切换 (纯 CSS 无 JS)
- 共识卡片: 头像行 + 强度条
- 分歧卡片: 对立条形 + 程度标签

## Step 8: 动效系统

| 动效 | 用途 |
|---|---|
| `pulse-border` | thinking |
| `glow-breathing` | speaking |
| `fade-in-up` | 新消息 |
| `slide-in-right` | 共识/分歧更新 |
| `blink` | 流式光标 |
| `round-transition` | 轮次切换 |

## Step 9: SummaryModal

Fixed overlay + blur backdrop + 居中弹窗 (max-width 640px)

## Step 10: DiscussionList

CSS Grid `auto-fill, minmax(320px, 1fr)` 自适应列数

## Step 11: 响应式

| 断点 | 策略 |
|---|---|
| ≥1920px | max-width 居中 |
| 1280~1919px | 完整布局 |
| 768~1279px | 单列 + Analysis 抽屉 |
| <768px | Stage 横向 Snap Scroll + Analysis Bottom Sheet |

---

## 执行顺序

```
Step 1  (tokens + reset)
  └→ Step 2  (骨架)
       ├→ Step 3  (Header)
       ├→ Step 4  (Stage) → Step 5 (GuestCard)
       ├→ Step 6  (Transcript)
       ├→ Step 7  (Analysis)
       ├→ Step 8  (动画，可并行)
       ├→ Step 9  (弹窗)
       └→ Step 10 (列表)
            └→ Step 11 (响应式)
```

---

## 验证清单

- [ ] 暗色主题生效，`:root` 变量齐全
- [ ] 三个区域可见，整页无外层滚动
- [ ] 舞台光晕 + 主持人金色居中 + 专家彩色边框
- [ ] GuestCard 四种状态静态样式正确
- [ ] Transcript 独立滚动 + 4px 颜色条 + 流式光标闪烁
- [ ] Analysis 独立滚动 + 强度条宽度正确
- [ ] Summary 弹窗居中模糊
- [ ] DiscussionList Grid 自适应
- [ ] 动效 @keyframes 定义齐全
- [ ] 1280px 以下单列 | 768px 以下横向Scroll
- [ ] 无 JavaScript 引用
