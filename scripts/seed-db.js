#!/usr/bin/env node

/**
 * AI Panel Studio — Mock 数据种子脚本
 * =============================================================================
 * 用途: 基于 docs/database_schema.sql 生成逼真的测试数据
 * 用法: npm run db:seed
 *
 * 数据关联性保证策略:
 *   1. 先生成 discussion → 再生成 guest（绑定 discussion_id）
 *   2. 再生成 transcript_entries（绑定 discussion_id + guest_id）
 *   3. consensus/divergence 的 agreed_guests/parties 使用已生成的 guest UUID
 *   4. source_entries 引用已生成的 transcript_entries UUID
 *
 * 时间连续性保证策略:
 *   - 每个讨论使用独立的 baseTime 起始点
 *   - 每条发言 spoken_at = baseTime + (sequence * randomInterval)
 *   - 时间间隔 30~120 秒，模拟流畅对话
 *   - transcript_entries 按 sequence_number 递增写入
 */

const Database = require("better-sqlite3");
const { faker } = require("@faker-js/faker");
const crypto = require("crypto");
const path = require("path");
const fs = require("fs");

// ---------------------------------------------------------------------------
// 配置
// ---------------------------------------------------------------------------
const DB_PATH = path.resolve(__dirname, "..", "data", "dev.db");
const SCHEMA_PATH = path.resolve(__dirname, "..", "docs", "database_schema.sql");

/** 生成指定范围内的随机整数 */
const randInt = (min, max) => Math.floor(Math.random() * (max - min + 1)) + min;

/** 生成指定范围内的随机浮点数 */
const randFloat = (min, max, decimals = 2) =>
  parseFloat((Math.random() * (max - min) + min).toFixed(decimals));

/** 在数组中随机选取一个元素 */
const pick = (arr) => arr[randInt(0, arr.length - 1)];

/** 生成 ISO8601 时间字符串，相对 base 偏移 seconds 秒 */
const timeAt = (base, seconds) => {
  const d = new Date(base.getTime() + seconds * 1000);
  return d.toISOString().replace(/\.\d{3}Z$/, "Z");
};

/** 当前时间（作为"最近创建"的讨论基准） */
const now = new Date();

// ---------------------------------------------------------------------------
// 讨论模板 — 3 个真实议题
// ---------------------------------------------------------------------------
const DISCUSSION_TEMPLATES = [
  {
    id: crypto.randomUUID(),
    topic: "AI会取代人类工作吗",
    topic_description:
      "探讨人工智能对未来10年就业市场的深远影响，聚焦白领工作自动化、新职业催生与技能重塑",
    host_style: "socratic",
    expert_count: 3,
    status: "active",
    round_count: 8,
    max_rounds: 10,
    started_at: null,
    finished_at: null,
    llm_model: "claude-sonnet-4-20250514",
    llm_config: JSON.stringify({ temperature: 0.7, max_tokens: 2048 }),
    interjection_mode: "moderated",
    baseTime: new Date(now.getTime() - 3600 * 1000), // 1 小时前开始
  },
  {
    id: crypto.randomUUID(),
    topic: "量子计算何时能商用化",
    topic_description:
      "讨论量子计算从实验室到产业化的关键瓶颈，以及未来5-10年的商业化路径",
    host_style: "provocative",
    expert_count: 4,
    status: "setup",
    round_count: 0,
    max_rounds: null,
    started_at: null,
    finished_at: null,
    llm_model: "claude-sonnet-4-20250514",
    llm_config: JSON.stringify({ temperature: 0.8, max_tokens: 2048 }),
    interjection_mode: "moderated",
    baseTime: new Date(now.getTime() - 600 * 1000), // 10 分钟前创建
  },
  {
    id: crypto.randomUUID(),
    topic: "是否应该实施全民基本收入",
    topic_description:
      "从经济可行性、社会公平、劳动力市场影响等角度，深入辩论全民基本收入(UBI)的利弊",
    host_style: "neutral",
    expert_count: 3,
    status: "finished",
    round_count: 12,
    max_rounds: 12,
    started_at: null, // 下面动态设置
    finished_at: null, // 下面动态设置
    llm_model: "claude-sonnet-4-20250514",
    llm_config: JSON.stringify({ temperature: 0.7, max_tokens: 2048 }),
    interjection_mode: "free",
    baseTime: new Date(now.getTime() - 86400 * 1000), // 1 天前开始
  },
];

// 为 finished 讨论设置 started_at / finished_at
DISCUSSION_TEMPLATES[2].started_at = timeAt(DISCUSSION_TEMPLATES[2].baseTime, 0);
DISCUSSION_TEMPLATES[2].finished_at = timeAt(
  DISCUSSION_TEMPLATES[2].baseTime,
  2400
);

// 为 active 讨论设置 started_at
DISCUSSION_TEMPLATES[0].started_at = timeAt(
  DISCUSSION_TEMPLATES[0].baseTime,
  0
);

// ---------------------------------------------------------------------------
// 嘉宾阵容模板 — 每个讨论 1 主持 + N 专家（预定义性格 + 立场 + 颜色）
// ---------------------------------------------------------------------------
const HOST_TEMPLATES = [
  {
    name: "张明远",
    title: "资深科技评论员",
    bio: "拥有15年科技媒体从业经验，曾主持多档知名科技访谈节目，以犀利的追问和深刻的洞察著称",
    stance: "中立客观，致力于发掘各方观点背后的逻辑",
    stance_label: "主持人",
    color: "#E8A840",
  },
  {
    name: "林婉清",
    title: "经济学人栏目主编",
    bio: "在政策分析和经济评论领域有丰富经验，擅长引导多维度的深度讨论",
    stance: "中立审慎，强调数据驱动与实证分析",
    stance_label: "主持人",
    color: "#E8A840",
  },
  {
    name: "陈道明",
    title: "凤凰卫视时事评论员",
    bio: "曾深度报道全球多个重大议题，主持风格沉稳大气，善于捕捉观点中的矛盾与张力",
    stance: "辩证中立，习惯从不同利益相关方视角审视问题",
    stance_label: "主持人",
    color: "#E8A840",
  },
];

const EXPERT_TEMPLATES = [
  // 讨论 1: AI 与工作
  [
    {
      name: "李思涵",
      title: "AI 研究员",
      bio: "在顶级AI实验室从事大模型研究8年，对AI技术边界有深刻理解",
      stance: "AI将大幅提升生产力并催生全新职业类别，历史证明每次技术革命最终创造的工作多于消灭的",
      stance_label: "乐观派",
      color: "#4A90D9",
    },
    {
      name: "王建国",
      title: "劳动经济学家",
      bio: "专注就业市场结构性变化研究，曾为多国政府提供劳动力转型政策咨询",
      stance: "本轮AI浪潮与以往技术革命不同——它威胁的是白领认知型工作而非体力劳动，转型阵痛将前所未有",
      stance_label: "谨慎派",
      color: "#D94A4A",
    },
    {
      name: "陈雪梅",
      title: "政策咨询顾问",
      bio: "在国际组织从事科技政策研究与倡导工作，聚焦AI治理与教育体系改革",
      stance: "关键在于政策准备——政府和企业需要提前布局技能重塑体系，不能等到失业潮来临再被动应对",
      stance_label: "务实派",
      color: "#50B86C",
    },
  ],
  // 讨论 2: 量子计算
  [
    {
      name: "周正宇",
      title: "量子物理学家",
      bio: "中科院量子信息重点实验室研究员，主导多个量子计算实验项目",
      stance: "量子纠错是最大瓶颈。乐观估计5年内实现逻辑量子比特，但通用量子计算机仍需10-15年",
      stance_label: "学界代表",
      color: "#7B61FF",
    },
    {
      name: "刘志强",
      title: "量子计算创业公司CTO",
      bio: "从学术圈跳到产业界，正在开发面向金融和制药行业的量子-经典混合计算平台",
      stance: "专用量子计算已在特定领域展现量子优势，3-5年内金融和制药行业将率先受益",
      stance_label: "产业推动者",
      color: "#FF6B6B",
    },
    {
      name: "赵明辉",
      title: "风险投资人",
      bio: "专注深科技领域投资，在过去3年投资了6家量子计算相关初创公司",
      stance: "市场过热需要降温。多数量子计算公司的估值与其技术成熟度严重脱节，泡沫正在形成",
      stance_label: "市场观察者",
      color: "#FFB347",
    },
    {
      name: "吴思远",
      title: "信息安全专家",
      bio: "在密码学和后量子密码领域拥有多项专利，为大型金融机构提供安全咨询",
      stance: "量子计算最先冲击的是网络安全——RSA加密可能在10年内被Shor算法攻破，现在就需要升级加密体系",
      stance_label: "安全倡导者",
      color: "#20B2AA",
    },
  ],
  // 讨论 3: UBI
  [
    {
      name: "沈一诺",
      title: "发展经济学家",
      bio: "在世界银行从事贫困与社会保障研究，对全球多个UBI试点项目有深入调研",
      stance: "UBI试点证据表明它能有效减少贫困和焦虑，但资金来源是核心挑战——需要累进税制和财富税配合",
      stance_label: "支持UBI",
      color: "#4CAF50",
    },
    {
      name: "钱伟成",
      title: "财政政策分析师",
      bio: "专注公共财政可持续性研究，曾参与多个国家社保体系改革的方案设计",
      stance: "以中国为例，14亿人口的UBI将耗费财政收入的2倍以上。我们需要的不是UBI，而是精准的社会安全网",
      stance_label: "反对UBI",
      color: "#F44336",
    },
    {
      name: "郑佳慧",
      title: "自动化与社会变革研究员",
      bio: "研究技术变革对劳动力市场的结构性影响，主张前瞻性社会政策以应对AI时代的就业危机",
      stance: "UBI不是灵丹妙药，但在AI大规模替代工作的时代，它是必要的安全网之一。我们应探索渐进式UBI方案",
      stance_label: "渐进改革派",
      color: "#2196F3",
    },
  ],
];

// ---------------------------------------------------------------------------
// 讨论 1 (AI & 工作) 的模拟对话流
// ---------------------------------------------------------------------------
const CONVERSATION_AI_JOBS = [
  // 第 0 轮: 开场 + 立场陈述
  {
    speaker: 0,
    type: "opening_statement",
    content:
      "欢迎各位来到今天的圆桌讨论。我们今天的主题是「AI会取代人类工作吗」。这是一个关乎每个人切身利益的话题——从工厂流水线到高级白领岗位，AI的能力边界正在以前所未有的速度扩展。让我们先听听各位专家的立场。李思涵老师，您是AI研究员，您怎么看？",
  },
  {
    speaker: 1,
    type: "position_statement",
    content:
      "谢谢主持人。我的立场是审慎乐观的。回顾工业革命以来的历史，每次重大技术变革都会带来短期就业冲击，但长期看创造的工作机会远超消灭的。蒸汽机淘汰了纺织工，但催生了铁路和机械制造行业。计算机淘汰了打字员，但创造了整个IT产业。我相信AI也将遵循这一规律——它会取代某些重复性认知工作，但更会催生AI训练师、提示工程师、AI伦理审计师等我们今天还无法命名的新职业。",
  },
  {
    speaker: 2,
    type: "position_statement",
    content:
      "我必须指出这个类比的缺陷。工业革命和计算机革命影响的主要是体力劳动和简单文书工作，而这一波生成式AI浪潮瞄准的恰恰是高技能白领工作——法律文书、编程、翻译、平面设计。这不是'旧工作消失、新工作出现'的简单循环，而是技能断层危机。一个45岁的会计师被AI取代后，不可能在几个月内转型为提示工程师。",
  },
  {
    speaker: 3,
    type: "position_statement",
    content:
      "两位的观点都有道理。我想补充一点：与其争论'会不会'，不如讨论'如何应对'。AI对就业的影响很大程度上取决于我们的制度选择。北欧国家的经验表明，有强大的再培训体系和社会保障作为缓冲，技术变革对就业的破坏性可以大幅降低。",
  },
  // 第 1 轮: 追问与辩论
  {
    speaker: 0,
    type: "question",
    content:
      "王建国老师提到技能断层危机，这是一个非常现实的问题。我想追问一下：您认为哪些行业会最先受到冲击？",
  },
  {
    speaker: 2,
    type: "answer",
    content:
      "最直接的是翻译和客服行业。去年某大型翻译公司的营收下降了40%，因为客户转向了AI翻译工具。其次是初级编程——GitHub Copilot已经能够完成约30%的编码任务。还有法律文书审核、初级财务分析、内容撰写等领域。我们需要认识到，这次不是渐进式的，而是爆发式的。",
  },
  {
    speaker: 1,
    type: "rebuttal",
    content:
      "我需要纠正一个认知偏差。AI翻译确实能完成大部分日常翻译任务，但高端法律翻译、文学翻译、同声传译的需求反而在增长——因为人们意识到了AI翻译的局限性，更愿意为人类专家付费。至于编程，Copilot是工具而不是替代者。它让程序员效率提升了，但软件的总需求也在增长——这就是Jevons悖论。",
  },
  {
    speaker: 3,
    type: "supplement",
    content:
      "我补充一个数据点：世界经济论坛的《2025年就业未来报告》预测，AI将在全球范围内取代约8500万个工作岗位，但将创造9700万个新岗位。净增长是存在的，但关键是这9700万个新岗位需要完全不同的技能组合——这才是我们需要认真对待的挑战。",
  },
  // 第 2 轮: 深入 AI 创造力边界
  {
    speaker: 0,
    type: "question",
    content:
      "说到创造力——AI最近在绘画、音乐、写作方面表现出惊人的能力。有人认为创意类工作者终于也会被替代。各位怎么看？",
  },
  {
    speaker: 1,
    type: "speech",
    content:
      "我承认AI在'有条件生成'方面很强——给定提示词，它能产出令人惊叹的图像和文本。但这是否算'创造力'？我认为真正的创造力需要意图(intention)和生命体验(lived experience)。AI可以模仿梵高的笔触，但它没有经历梵高所经历的痛苦和精神挣扎。它产出的东西在美学上可能是杰出的，但在人文深度上是有上限的。",
  },
  {
    speaker: 2,
    type: "rebuttal",
    content:
      "我不同意把'创造力的定义'当作挡箭牌。问题不在于AI有没有'真正的创造力'，而在于它产出的结果是否满足市场需求。大多数商业创意工作——广告文案、包装设计、背景音乐——客户需要的不是灵魂而是效果。对这部分从业者来说，AI已经是真实的威胁。",
  },
  {
    speaker: 3,
    type: "speech",
    content:
      "我想把讨论拉回到政策层面。即使我们承认AI有它的局限性，我们也需要一个'过渡期保障'的制度设计。我建议借鉴德国的'短时工作制'(Kurzarbeit)——当企业因AI转型而裁员时，政府补贴员工缩短工时进行再培训，而不是直接失业。这种方式已经证明比被动发放失业救济更有效。",
  },
  // 第 3 轮: 教育体系改革
  {
    speaker: 0,
    type: "question",
    content:
      "陈雪梅老师提到了再培训，这引出了教育的问题。我们现在的教育体系——从小学到大学——是否已经过时了？",
  },
  {
    speaker: 3,
    type: "answer",
    content:
      "不仅是过时，可能是致命的错配。我们的教育体系是为20世纪的工业社会设计的——标准化考试、固定的知识清单、假设学生在20岁前学会的东西可以用一辈子。但在AI时代，知识更新的半衰期正在急剧缩短。我们需要从'知识传授'转向'学习能力培养'——批判性思维、跨领域联想、情感智能，这些是AI在相当长时间内难以完全模拟的。",
  },
  {
    speaker: 1,
    type: "supplement",
    content:
      "我完全同意。另外我想补充，教育应该加强'人机协作'的能力培养。未来的工作不是'人类 vs AI'，而是'人类 + AI'。就像今天会用Excel是基本技能一样，未来会用AI工具高效完成任务将是基本素养。我们的学校应该从小学就开始教孩子如何与AI有效协作。",
  },
  {
    speaker: 2,
    type: "speech",
    content:
      "理想很美好，但现实是——我们的教育体系改革的速度远远慢于技术变革的速度。中国用了20年才完成新课标的全面推广。而GPT从3.5到4再到5只用了不到3年。这个速度差是我们真正的危机。我建议的措施更直接：大规模补贴在线职业教育平台，让已经在职场的人能够快速获得AI相关技能。",
  },
  // 第 4 轮: 社会保障体系
  {
    speaker: 0,
    type: "question",
    content:
      "顺着王老师的思路——如果大量中年白领确实无法快速转型，我们的社会保障体系能兜底吗？",
  },
  {
    speaker: 2,
    type: "speech",
    content:
      "坦率地说，不能。我们的社保体系是为低失业率、高就业稳定性的时代设计的。失业保险的覆盖范围、金额和期限都不足以应对AI可能带来的大规模结构性失业。我们需要一场严肃的社会契约重新谈判——政府、企业和劳动者之间需要达成新的共识。比如是否可以探讨'技术红利税'——对因AI而获得超额利润的企业征收特别税，用于设立再培训和转型基金。",
  },
  {
    speaker: 1,
    type: "rebuttal",
    content:
      "技术红利税的思路很有创意，但我担心它会抑制创新。如果企业因为使用AI要多交税，那反而会降低它们部署AI的动力——这可能把AI产业推向海外。我更倾向通过正常的公司税改革来扩大财政收入，然后定向增加教育和培训支出。",
  },
  {
    speaker: 3,
    type: "supplement",
    content:
      "两位的讨论引出另一个重要维度：我们需要提前行动而不是被动应对。我的建议是设立一个'AI转型预警机制'——政府定期评估各行业的AI替代风险指数，当某个行业的风险超过阈值时，自动触发相应的政策工具包：培训补贴、税收优惠、就业介绍服务等。这样比每遇到一次危机就临时拼凑方案要有效得多。",
  },
  // 第 5 轮: 全球化视角
  {
    speaker: 0,
    type: "question",
    content:
      "让我们把视野放到全球——AI对不同国家的影响是否不同？这对全球劳动力格局意味着什么？",
  },
  {
    speaker: 1,
    type: "speech",
    content:
      "非常好的问题。AI可能加剧全球不平等。发达国家因为有更强的AI研发能力和更好的数字基础设施，可能实现生产力跃升；而发展中国家依赖的低成本劳动力优势——这是它们融入全球价值链的主要筹码——可能被AI削弱。想象一下：当服装设计可以由AI在纽约完成并直接驱动自动化工厂生产时，孟加拉的服装工人将何去何从？",
  },
  {
    speaker: 2,
    type: "supplement",
    content:
      "确实如此。AI可能逆转全球化进程中的'劳动力套利'模式。过去30年，跨国公司把生产外包到劳动力成本低的国家；未来，如果AI+机器人比海外工人更便宜，制造业可能回流发达国家。这不是预测——我们已经看到一些鞋类和电子产品制造开始向自动化工厂转移。",
  },
  {
    speaker: 3,
    type: "speech",
    content:
      "这对于中国这样正在向高端制造转型的经济体来说，既是挑战也是机遇。挑战在于我们的劳动力密集型产业——比如电子产品组装——确实面临被AI+自动化替代的风险。但机遇在于，如果能抓住AI技术的研发和应用的制高点，中国可以加速向价值链上游攀升。关键是速度：我们必须在劳动力红利完全消失之前完成转型。",
  },
  // 第 6 轮: AI 治理与伦理
  {
    speaker: 0,
    type: "question",
    content:
      "这引出了一个更深层的问题：我们是否需要对AI的发展速度和部署节奏进行某种程度的管控？",
  },
  {
    speaker: 3,
    type: "speech",
    content:
      "是的，我认为这是必要的。但这不意味着'禁止AI'——那是因噎废食。我们需要的是'负责任的部署节奏'。比如，当AI即将大规模进入某个行业时，应该有一个'影响评估期'——评估对就业的冲击、制定再培训方案、建立社会安全网。这类似于大型基建项目的环评流程。",
  },
  {
    speaker: 1,
    type: "speech",
    content:
      "从技术从业者的角度，我对此有些矛盾。一方面我理解社会需要时间适应；另一方面技术的迭代速度是市场竞争的结果——如果Google放慢脚步，OpenAI不会等，Meta不会等。所以单一的国内管制可能无效，需要国际协调。这让我想到了核不扩散条约的模式——也许我们需要一个'AI发展国际公约'。",
  },
  {
    speaker: 2,
    type: "rebuttal",
    content:
      "国际公约的提议很好，但执行起来极其困难——核技术控制在少数国家手中，而AI是分布式的，任何有足够算力和数据的组织都能训练模型。我更务实的主张是：在每个公司层面建立AI伦理委员会，在部署可能造成大规模失业的AI系统前进行社会影响评估。",
  },
  {
    speaker: 0,
    type: "closing_statement",
    content:
      "我们今天讨论了很多层面——从技术能力到教育体系，从社会保障到全球治理。让我尝试总结一下几个核心共识：第一，AI确实会取代部分工作，但也会创造新机会，关键在于转型的速度和准备程度；第二，教育体系和社会安全网需要前瞻性改革；第三，AI的部署节奏需要某种形式的治理，但不能以牺牲创新为代价。感谢三位专家的精彩讨论。",
  },
  // 额外发言 — 超过50条
  {
    speaker: 0,
    type: "question",
    content:
      "我想追问一个更个人化的问题：如果让各位给自己的职业安全性打分，从1到10，你们会给自己打多少分？",
  },
  {
    speaker: 1,
    type: "answer",
    content:
      "我给自己的工作打8分。AI研究本身就是对抗AI替代的最好护城河——你需要人类来改进AI。但我不排除某些日常编码和文献综述任务被AI接手，这正好把时间留给更有创造性的研究。",
  },
  {
    speaker: 2,
    type: "answer",
    content:
      "我打5分。经济分析和政策研究需要综合判断力——整合多方数据、理解政治语境、感知历史趋势——这些是AI目前做不到的。但我做的大量统计分析工作确实可以被AI替代，这部分我可能需要重新定位自己的价值。",
  },
  {
    speaker: 3,
    type: "answer",
    content:
      "我给政策咨询工作打7分。政策制定本质上是利益协调和价值判断——这些是人类的专属领域。但背景调研和文案撰写部分可能需要拥抱AI工具。最后我想说，与其焦虑要不要被替代，不如主动学习AI工具——我已经在每天使用ChatGPT帮我处理初稿和文献摘要了。",
  },
  {
    speaker: 0,
    type: "speech",
    content:
      "这个问题的答案让我看到了一个乐观的信号——各位专家都在积极适应而不是消极抵抗。也许这就是我们面对AI时代应有的态度：不是问'我会不会被取代'，而是问'我如何与AI一起变得更强'。",
  },
];

// ---------------------------------------------------------------------------
// 讨论 3 (UBI) 的模拟对话流 (finished 状态，有完整总结)
// ---------------------------------------------------------------------------
const CONVERSATION_UBI = [
  {
    speaker: 0,
    type: "opening_statement",
    content:
      "欢迎来到今天的讨论。我们的主题是「是否应该实施全民基本收入」。UBI——无条件给予每个公民定期现金支付——这个概念近年来从边缘走向主流，支持者包括硅谷科技领袖和诺贝尔经济学奖得主，反对者也同样强大。让我们先听各位专家的核心立场。",
  },
  {
    speaker: 1,
    type: "position_statement",
    content:
      "谢谢。我是UBI的支持者，但不是无条件支持。全球各地的UBI试点——从肯尼亚到芬兰到美国的斯托克顿——都显示了类似的效果：UBI减少了贫困和焦虑，提升了心理健康，并没有导致大规模'躺平'。但资金是关键。我主张通过累进财富税和碳税来为渐进式UBI提供资金。",
  },
  {
    speaker: 2,
    type: "position_statement",
    content:
      "我必须唱反调。财政可行性是UBI的阿喀琉斯之踵。以中国为例，每人每月1000元的UBI——这是低保水平——每年就需要16.8万亿，超过中央和地方财政总收入的50%。这不是'调整税收结构'能解决的。我们需要的是精准的社会安全网，而不是向所有人无差别发钱。",
  },
  {
    speaker: 3,
    type: "position_statement",
    content:
      "两位的开场已经揭示了核心张力。我的立场是：UBI不是万能药，但它是AI时代不可或缺的政策工具之一。我不主张一步到位，而是探索'渐进式UBI'——先从特定人群（如失业转型期工作者、育儿家庭）开始试点，逐步扩大覆盖面和金额，在运行中不断优化。",
  },
  // 第 1 轮: 财务可行性辩论
  {
    speaker: 0,
    type: "question",
    content:
      "钱老师提出了一个尖锐的财务问题。沈老师，您如何回应16.8万亿这个数字？",
  },
  {
    speaker: 1,
    type: "answer",
    content:
      "这个数字的计算方式有误导性。首先，UBI不是凭空增加16.8万亿支出——它需要替代现有的低保、失业保险、各种补贴等碎片化的福利体系。其次，UBI可以通过累进税收回——高收入群体虽然也领UBI，但他们通过税收缴回去的更多。实际净成本远低于表面数字。IMF的研究显示，在一个合理的税收方案下，基础UBI的净成本约为GDP的3-4%。",
  },
  {
    speaker: 2,
    type: "rebuttal",
    content:
      "IMF的模型是基于发达国家的假设。中国的税收征管能力、收入申报的完整性、以及地下经济的规模都与OECD国家有巨大差异。而且'替代现有福利'在政治上是极其困难的——任何试图取消某项现有补贴的提议都会遭遇既得利益群体的强烈反对。UBI不是数学问题，是政治经济学问题。",
  },
  {
    speaker: 3,
    type: "supplement",
    content:
      "我建议把讨论聚焦在'试点'而非'全面推行'上。钱老师的担忧在全面推行情境下是成立的，但如果我们先从一个月入低于当地最低收入标准的50%的人群开始试点，支出规模是可控的。通过试点获得数据后，再评估是否需要扩大。这是实证政策制定，而不是意识形态之争。",
  },
  // 第 2 轮: 劳动力供给影响
  {
    speaker: 0,
    type: "question",
    content: "一个常见担忧是：如果人人都有基本收入，还会有人去工作吗？",
  },
  {
    speaker: 1,
    type: "speech",
    content:
      "这是UBI反对者最常提出的担忧，但证据并不支持。芬兰的UBI实验发现，接受UBI的群体的就业率与对照组没有显著差异。肯尼亚为期12年的UBI实验初步结果显示，UBI接受者更有可能创业。人的工作动机不纯粹是经济性的——社会认同、自我实现、对成就的追求同样重要。UBI只是移除了生存的恐惧，不是移除了工作的意愿。",
  },
  {
    speaker: 2,
    type: "speech",
    content:
      "芬兰实验的样本量只有2000人，且只覆盖了原有失业金领取者。从2000个失业者到14亿人的全面推广，这个外推在方法论上是极其脆弱的。另外，UBI实验通常只持续1-2年——参与者知道这笔钱是暂时的，他们当然不会放弃职业规划。但如果有人知道自己从出生到死亡每月都能领UBI，他们的行为可能完全不同。",
  },
  {
    speaker: 3,
    type: "speech",
    content:
      "两位的观点都有道理。这也是为什么我主张渐进式试点——不是一两年，而是至少十年的持续跟踪。加拿大安大略省原本计划了一个为期三年的UBI试点，遗憾的是被新政府提前取消了。我们需要更多长期数据才能对这个问题做出可靠判断。",
  },
  // 第 3 轮: AI 时代的紧迫性
  {
    speaker: 0,
    type: "question",
    content:
      "让我们回到今天的时代背景。如果AI确实会在未来10年大规模替代工作，这是否改变了UBI讨论的前提？",
  },
  {
    speaker: 3,
    type: "speech",
    content:
      "这正是我认为UBI讨论已经从'要不要'转向'何时做、怎么做'的原因。在AI可能大规模替代工作的世界里，UBI的逻辑基础发生了根本变化：它不再是'扶贫工具'，而是'社会契约的重新定义'。如果社会不再需要每个人全职工作来维持运转，那我们就需要一种新的分配机制来确保每个人都能共享技术红利。",
  },
  {
    speaker: 1,
    type: "supplement",
    content:
      "完全同意。这就是为什么硅谷的科技领袖——比如Sam Altman和Elon Musk——都公开支持UBI。他们不是出于慈善，而是看到了技术发展的方向。Altman甚至在做一个名为WorldCoin的全球UBI实验。当创造技术的人都在呼吁建立安全网时，我们应该认真对待。",
  },
  {
    speaker: 2,
    type: "speech",
    content:
      "硅谷领袖支持UBI可能有一个更功利的动机——他们希望用UBI来换取公众对AI发展的接受。这不一定是坏事，但我们需要警惕'技术公司买单换社会许可证'的模式。另外，AI大规模替代工作的时间线是高度不确定的——10年前我们还在说自动驾驶将在2020年普及。如果AI替代的速度比预期慢，我们是否有必要现在就启动一个万亿级的UBI计划？",
  },
  // 第 4 轮: 国际比较与中国特色
  {
    speaker: 0,
    type: "question",
    content:
      "让我们谈谈中国具体的情况。中国推行UBI有什么特殊的挑战和优势？",
  },
  {
    speaker: 2,
    type: "speech",
    content:
      "中国的特殊挑战包括：第一，人口规模使任何普惠性政策都极为昂贵；第二，城乡二元结构——同样的UBI金额在城市和农村的实际购买力差异巨大；第三，社保体系的碎片化——不同地区的社保标准差异巨大，UBI替代现有体系面临巨大的整合难度。",
  },
  {
    speaker: 1,
    type: "speech",
    content:
      "但中国也有独特优势。首先，强大的数字基础设施——支付宝和微信支付的覆盖率超过90%——使得UBI的发放成本极低。其次，中国有成功的'低保'和'新农合'等大型转移支付项目的实施经验。第三，土地公有制和国有企业红利可以作为UBI的资金来源之一——阿拉斯加永久基金就是一个模式。",
  },
  {
    speaker: 3,
    type: "supplement",
    content:
      "我想补充一个非常重要的制度优势：中国可以更快速、更大规模地进行政策实验。深圳或雄安可以在几个区试点不同金额和模式的UBI，收集1-2年数据后再决定是否推广。这种'政策沙盒'的能力是中国独特于许多西方国家的。",
  },
  // 第 5 轮: 总结与展望 (接近结尾)
  {
    speaker: 0,
    type: "question",
    content:
      "在接近我们讨论的尾声时，我想请每位专家用一句话总结您的核心观点。并从1到10给您对UBI可行性的判断打分。",
  },
  {
    speaker: 1,
    type: "closing_statement",
    content:
      "UBI是AI时代社会契约的必要更新。打分：可行性7分——财务和政治方面有巨大挑战，但方向是正确的，我们应该从今天开始试点。",
  },
  {
    speaker: 2,
    type: "closing_statement",
    content:
      "UBI的意图值得赞赏，但其财务不可持续性是一个无法回避的硬伤。打分：可行性3分——在当前的技术和财政条件下，全面UBI不是一个负责任的建议。我支持大规模的精准转移支付替代方案。",
  },
  {
    speaker: 3,
    type: "closing_statement",
    content:
      "不要被'全面UBI'的理想吓退，也不要对'精准扶助'的现状满足。我的愿景是：从今天起，用10年时间，从试点到推广，从低金额到适中金额，逐步建成一个适应AI时代的基础收入保障体系。打分：可行性6分——难但不放弃。",
  },
  {
    speaker: 0,
    type: "host_summary",
    content:
      "感谢三位专家的深入讨论。我们今天触及了UBI的财务可行性、对劳动力市场的影响、AI时代的紧迫性、以及中国情境下的特殊挑战与机遇。核心分歧在于：沈老师认为UBI是方向正确但需要渐进推进的政策创新；钱老师认为其财务不可持续性使得全面推行不具现实性；郑老师则呼吁用实证试点的思路来检验理论。我个人认为，今天的讨论并未'解决'UBI之争，但它展示了这个议题的丰富维度——如果我们不认真思考AI时代的分配问题，等到危机来临时再被动反应，代价会大得多。感谢各位。",
  },
];

// ---------------------------------------------------------------------------
// 共识 & 分歧数据
// ---------------------------------------------------------------------------
const CONSENSUS_AI_JOBS = [
  {
    id: crypto.randomUUID(),
    content: "各方均认同AI将在短期内对部分白领工作造成显著冲击，尤其是翻译、客服、初级编程等领域",
    agreed_guests: ["guest_1", "guest_2", "guest_3"],
    confidence: 0.95,
    source_entry_offset: [3, 5, 6],
  },
  {
    id: crypto.randomUUID(),
    content: "教育体系需要从'知识传授'转向'学习能力培养'，并加强人机协作技能的培训",
    agreed_guests: ["guest_1", "guest_2", "guest_3"],
    confidence: 0.85,
    source_entry_offset: [14, 15, 16],
  },
  {
    id: crypto.randomUUID(),
    content: "AI的部署节奏需要某种形式的治理机制，但不能以牺牲创新为代价",
    agreed_guests: ["guest_1", "guest_2", "guest_3"],
    confidence: 0.75,
    source_entry_offset: [27, 28, 29],
  },
];

const DIVERGENCE_AI_JOBS = [
  {
    id: crypto.randomUUID(),
    content: "关于AI对就业的最终净影响：乐观派认为将创造更多新职业，谨慎派认为技能断层危机将导致大量结构性失业",
    severity: "sharp",
    source_entry_offset: [2, 3],
  },
  {
    id: crypto.randomUUID(),
    content: "关于是否需要对AI企业征收'技术红利税'来为再培训提供资金",
    severity: "moderate",
    source_entry_offset: [20, 21],
  },
];

const CONSENSUS_UBI = [
  {
    id: crypto.randomUUID(),
    content: "各方同意UBI的财务可行性是最大挑战，资金来源需通过税收体系改革来解决",
    agreed_guests: ["guest_1", "guest_2", "guest_3"],
    confidence: 0.9,
    source_entry_offset: [5, 6, 7],
  },
  {
    id: crypto.randomUUID(),
    content: "试点优于一步到位的全面推行——各方同意应通过小规模、长期试点来收集数据",
    agreed_guests: ["guest_1", "guest_2", "guest_3"],
    confidence: 0.8,
    source_entry_offset: [8, 14, 16],
  },
];

const DIVERGENCE_UBI = [
  {
    id: crypto.randomUUID(),
    content: "关于全面UBI的财务可行性：支持方认为净成本可控（约GDP 3-4%），反对方认为在中国情境下不可行",
    severity: "fundamental",
    source_entry_offset: [5, 6],
  },
];

// =============================================================================
// 主流程
// =============================================================================
function main() {
  console.log("🧹 清理旧数据库...");
  if (fs.existsSync(DB_PATH)) {
    fs.unlinkSync(DB_PATH);
  }

  console.log("📂 初始化数据库 Schema...");
  const db = new Database(DB_PATH);
  db.pragma("journal_mode = WAL");
  db.pragma("foreign_keys = ON");

  const schemaSQL = fs.readFileSync(SCHEMA_PATH, "utf-8");
  db.exec(schemaSQL);

  console.log("🌱 开始生成 Mock 数据...\n");

  // ------------------------------------------------------------------
  // 处理每个讨论
  // ------------------------------------------------------------------
  for (const dt of DISCUSSION_TEMPLATES) {
    const dIdx = DISCUSSION_TEMPLATES.indexOf(dt);
    console.log(
      `📋 [${dt.status.toUpperCase()}] ${dt.topic} (${dt.expert_count + 1} 位嘉宾)`
    );

    // 1. 插入 discussion
    const discData = { ...dt };
    delete discData.baseTime;
    db.prepare(
      `INSERT INTO discussions (
        id, topic, topic_description, host_style, expert_count, status,
        round_count, max_rounds, started_at, finished_at,
        llm_model, llm_config, interjection_mode, created_at, updated_at
      ) VALUES (
        @id, @topic, @topic_description, @host_style, @expert_count, @status,
        @round_count, @max_rounds, @started_at, @finished_at,
        @llm_model, @llm_config, @interjection_mode,
        @created_at, @created_at
      )`
    ).run({
      ...discData,
      created_at: timeAt(dt.baseTime, 0),
      updated_at: timeAt(dt.baseTime, 0),
    });

    // 2. 插入 guests (1 主持 + N 专家)
    const guestIds = [];
    const hostTemplate = HOST_TEMPLATES[dIdx];
    const hostId = crypto.randomUUID();
    guestIds.push(hostId);

    // 主持人
    db.prepare(
      `INSERT INTO guests (
        id, discussion_id, role, name, title, bio,
        stance, stance_label, color, avatar_url,
        status, speech_order, persona_prompt, is_active, created_at, updated_at
      ) VALUES (
        @id, @discussion_id, 'host', @name, @title, @bio,
        @stance, @stance_label, @color, NULL,
        'idle', 0, @persona_prompt, 1, @created_at, @created_at
      )`
    ).run({
      id: hostId,
      discussion_id: dt.id,
      name: hostTemplate.name,
      title: hostTemplate.title,
      bio: hostTemplate.bio,
      stance: hostTemplate.stance,
      stance_label: hostTemplate.stance_label,
      color: hostTemplate.color,
      persona_prompt: `你是一位经验丰富的主持人，${hostTemplate.bio}。你的主持风格是${dt.host_style}。你需要保持中立，引导讨论深入，提出有洞察力的问题，并在必要时进行追问。`,
      created_at: timeAt(dt.baseTime, -60),
    });

    // 专家
    const expertTemplates = EXPERT_TEMPLATES[dIdx];
    let actualExpertCount = 0;
    for (const expert of expertTemplates) {
      if (actualExpertCount >= dt.expert_count) break;
      const expertId = crypto.randomUUID();
      guestIds.push(expertId);
      actualExpertCount++;

      db.prepare(
        `INSERT INTO guests (
          id, discussion_id, role, name, title, bio,
          stance, stance_label, color, avatar_url,
          status, speech_order, persona_prompt, is_active, created_at, updated_at
        ) VALUES (
          @id, @discussion_id, 'expert', @name, @title, @bio,
          @stance, @stance_label, @color, NULL,
          'idle', @speech_order, @persona_prompt, 1, @created_at, @created_at
        )`
      ).run({
        id: expertId,
        discussion_id: dt.id,
        name: expert.name,
        title: expert.title,
        bio: expert.bio,
        stance: expert.stance,
        stance_label: expert.stance_label,
        color: expert.color,
        speech_order: actualExpertCount,
        persona_prompt: `你是${expert.name}，${expert.title}。${expert.bio}。你的核心立场是：${expert.stance}。在讨论中保持自己的专业视角，主动发言、补充、反驳，但保持专业和礼貌。`,
        created_at: timeAt(dt.baseTime, -30),
      });
    }
    console.log(`   ├─ 嘉宾: ${guestIds.length} 位 (1 主持 + ${actualExpertCount} 专家)`);

    // 3. 插入 transcript entries
    const conversation =
      dIdx === 0
        ? CONVERSATION_AI_JOBS
        : dIdx === 2
          ? CONVERSATION_UBI
          : null;

    const entryIds = [];
    if (conversation) {
      const insertEntry = db.prepare(
        `INSERT INTO transcript_entries (
          id, discussion_id, guest_id, sequence_number, round_number,
          entry_type, content, quote_of, is_final, spoken_at, created_at
        ) VALUES (
          @id, @discussion_id, @guest_id, @sequence_number, @round_number,
          @entry_type, @content, @quote_of, 1, @spoken_at, @spoken_at
        )`
      );

      let seq = 0;
      let round = 0;

      for (let i = 0; i < conversation.length; i++) {
        const msg = conversation[i];

        // 根据类型推进轮次
        if (
          msg.type === "opening_statement" ||
          msg.type === "question"
        ) {
          round++;
        }

        const entryId = crypto.randomUUID();
        entryIds.push(entryId);
        seq++;

        // 时间递增 30-120 秒
        const timeOffset = (i === 0 ? 60 : (seq - 1) * randInt(30, 120)) + randInt(0, 30);

        insertEntry.run({
          id: entryId,
          discussion_id: dt.id,
          guest_id: guestIds[msg.speaker],
          sequence_number: seq,
          round_number: round,
          entry_type: msg.type,
          content: msg.content,
          quote_of: null,
          spoken_at: timeAt(dt.baseTime, timeOffset),
        });
      }
      console.log(`   ├─ 发言记录: ${entryIds.length} 条`);

      // 更新讨论的 round_count
      db.prepare("UPDATE discussions SET round_count = ? WHERE id = ?").run(
        round,
        dt.id
      );
    }

    // 4. 插入 thinking_snapshots (为专家生成 thinking 快照)
    let snapshotCount = 0;
    for (let g = 1; g < guestIds.length; g++) {
      // 每个专家 2-4 个历史快照（最后一条 is_latest=1）
      const snapCount = randInt(2, 4);
      for (let s = 0; s < snapCount; s++) {
        const isLatest = s === snapCount - 1 ? 1 : 0;
        const statuses = ["idle", "thinking", "speaking", "waiting"];
        const status = isLatest ? "idle" : pick(statuses);
        const intents = [
          "raise_hand",
          "rebut",
          "supplement",
          "stay_silent",
          "answer",
        ];

        db.prepare(
          `INSERT INTO thinking_snapshots (
            id, discussion_id, guest_id, status, public_thought,
            hidden_cot, confidence, intent, snapshot_at, is_latest, created_at
          ) VALUES (
            @id, @discussion_id, @guest_id, @status, @public_thought,
            @hidden_cot, @confidence, @intent, @snapshot_at, @is_latest, @snapshot_at
          )`
        ).run({
          id: crypto.randomUUID(),
          discussion_id: dt.id,
          guest_id: guestIds[g],
          status: status,
          public_thought: faker.lorem.sentence({ min: 5, max: 15 }),
          hidden_cot:
            "[隐藏推理链] " +
            faker.lorem.paragraph({ min: 2, max: 5 }),
          confidence: randFloat(0.5, 1.0),
          intent: pick(intents),
          snapshot_at: timeAt(dt.baseTime, randInt(60, 3000)),
          is_latest: isLatest,
        });
        snapshotCount++;
      }
    }
    console.log(`   ├─ 思考快照: ${snapshotCount} 条`);

    // 5. 插入 consensus items
    const consensusData =
      dIdx === 0
        ? CONSENSUS_AI_JOBS
        : dIdx === 2
          ? CONSENSUS_UBI
          : [];

    for (const ci of consensusData) {
      const agreedIds = ci.agreed_guests.map((label) => {
        const idx = parseInt(label.split("_")[1]);
        return guestIds[idx];
      });
      const sourceIds = ci.source_entry_offset
        .filter((off) => off - 1 < entryIds.length)
        .map((off) => entryIds[off - 1]);

      db.prepare(
        `INSERT INTO consensus_items (
          id, discussion_id, content, agreed_guests, confidence,
          first_identified_at, last_reinforced_at,
          is_active, source_entries, created_at, updated_at
        ) VALUES (
          @id, @discussion_id, @content, @agreed_guests, @confidence,
          @first_identified_at, @last_reinforced_at,
          1, @source_entries, @created_at, @created_at
        )`
      ).run({
        id: ci.id,
        discussion_id: dt.id,
        content: ci.content,
        agreed_guests: JSON.stringify(agreedIds),
        confidence: ci.confidence,
        first_identified_at: timeAt(dt.baseTime, randInt(200, 1800)),
        last_reinforced_at: timeAt(dt.baseTime, randInt(1800, 2400)),
        source_entries: JSON.stringify(sourceIds),
        created_at: timeAt(dt.baseTime, randInt(200, 1800)),
      });
    }
    console.log(`   ├─ 共识项: ${consensusData.length} 条`);

    // 6. 插入 divergence items
    const divergenceData =
      dIdx === 0
        ? DIVERGENCE_AI_JOBS
        : dIdx === 2
          ? DIVERGENCE_UBI
          : [];

    for (const di of divergenceData) {
      const sourceIds = di.source_entry_offset
        .filter((off) => off - 1 < entryIds.length)
        .map((off) => entryIds[off - 1]);

      // 构造 parties JSON
      const parties = [
        {
          stance: "支持方",
          guest_ids: [guestIds[1]], // 第一个专家
        },
        {
          stance: "反对方",
          guest_ids: [guestIds[2]], // 第二个专家
        },
      ];

      db.prepare(
        `INSERT INTO divergence_items (
          id, discussion_id, content, parties, severity,
          first_identified_at, last_updated_at,
          is_active, resolved, resolved_at, resolution_note,
          source_entries, created_at, updated_at
        ) VALUES (
          @id, @discussion_id, @content, @parties, @severity,
          @first_identified_at, @last_updated_at,
          1, 0, NULL, NULL,
          @source_entries, @created_at, @created_at
        )`
      ).run({
        id: di.id,
        discussion_id: dt.id,
        content: di.content,
        parties: JSON.stringify(parties),
        severity: di.severity,
        first_identified_at: timeAt(dt.baseTime, randInt(300, 1500)),
        last_updated_at: timeAt(dt.baseTime, randInt(1500, 2200)),
        source_entries: JSON.stringify(sourceIds),
        created_at: timeAt(dt.baseTime, randInt(300, 1500)),
      });
    }
    console.log(`   ├─ 分歧项: ${divergenceData.length} 条`);

    // 7. 为 finished 状态的讨论生成 summary
    if (dt.status === "finished") {
      db.prepare(
        `INSERT INTO discussion_summaries (
          id, discussion_id, content, key_findings,
          consensus_summary, divergence_summary,
          guest_contributions, generation_model, generation_cost, created_at
        ) VALUES (
          @id, @discussion_id, @content, @key_findings,
          @consensus_summary, @divergence_summary,
          @guest_contributions, @generation_model, @generation_cost, @created_at
        )`
      ).run({
        id: crypto.randomUUID(),
        discussion_id: dt.id,
        content:
          "本次讨论围绕全民基本收入(UBI)展开了多维度深入辩论。核心结论是：UBI是AI时代值得认真对待的政策工具，但其财务可行性和政治可接受性仍需通过长期试点来验证。讨论涵盖了资金来源、劳动力供给影响、AI时代的紧迫性、以及中国情境下的特殊挑战与制度优势。",
        key_findings: JSON.stringify([
          "UBI试点证据表明它能有效减少贫困和焦虑，不会导致大规模'躺平'",
          "财务可行性是UBI面临的最大挑战，净成本约为GDP的3-4%",
          "中国具有数字基础设施和'政策沙盒'的独特优势",
          "渐进式UBI方案获得了最大程度的共识",
        ]),
        consensus_summary: JSON.stringify(
          consensusData.map((c) => c.content)
        ),
        divergence_summary: JSON.stringify(
          divergenceData.map((d) => ({
            content: d.content,
            severity: d.severity,
          }))
        ),
        guest_contributions: JSON.stringify([
          {
            guest_name: HOST_TEMPLATES[2].name,
            role: "host",
            keywords: ["引导", "总结", "追问"],
            highlights: [
              "提出了AI时代UBI逻辑基础的根本变化",
            ],
          },
          {
            guest_name: EXPERT_TEMPLATES[2][0].name,
            role: "expert",
            keywords: ["UBI试点", "累进税制", "社会契约"],
            highlights: [
              "系统引用了全球UBI试点的实证证据",
              "提出了通过累进财富税和碳税为UBI提供资金",
            ],
          },
          {
            guest_name: EXPERT_TEMPLATES[2][1].name,
            role: "expert",
            keywords: ["财务可行性", "政治经济学", "精准安全网"],
            highlights: [
              "以16.8万亿数据论证全面UBI的财务不可持续性",
              "强调税收征管与地下经济的现实挑战",
            ],
          },
          {
            guest_name: EXPERT_TEMPLATES[2][2].name,
            role: "expert",
            keywords: ["渐进式UBI", "政策沙盒", "实证试点"],
            highlights: [
              "提出了'渐进式UBI'的中间路径",
              "强调中国'政策沙盒'的制度优势",
            ],
          },
        ]),
        generation_model: dt.llm_model,
        generation_cost: JSON.stringify({
          tokens_in: 12500,
          tokens_out: 2800,
          latency_ms: 4200,
        }),
        created_at: timeAt(dt.baseTime, 2500),
      });
      console.log("   └─ 总结: 1 份");
    } else {
      console.log("   └─ (跳过总结 — 讨论未结束)");
    }
    console.log("");
  }

  // ------------------------------------------------------------------
  // 验证
  // ------------------------------------------------------------------
  console.log("=".repeat(60));
  console.log("📊 数据统计:\n");

  const stats = db
    .prepare(
      `
    SELECT
      (SELECT COUNT(*) FROM discussions) AS discussions,
      (SELECT COUNT(*) FROM guests) AS guests,
      (SELECT COUNT(*) FROM transcript_entries) AS transcript_entries,
      (SELECT COUNT(*) FROM thinking_snapshots) AS thinking_snapshots,
      (SELECT COUNT(*) FROM consensus_items) AS consensus_items,
      (SELECT COUNT(*) FROM divergence_items) AS divergence_items,
      (SELECT COUNT(*) FROM discussion_summaries) AS discussion_summaries
    `
    )
    .get();

  for (const [key, val] of Object.entries(stats)) {
    console.log(`   ${key.padEnd(25)} ${val}`);
  }

  console.log("");
  console.log("🔍 数据完整性检查:");

  // 检查孤儿记录
  const orphanGuests = db
    .prepare(
      `SELECT COUNT(*) AS c FROM guests g
     LEFT JOIN discussions d ON g.discussion_id = d.id
     WHERE d.id IS NULL`
    )
    .get().c;
  console.log(`   孤儿 guests: ${orphanGuests} (应为 0)`);

  const orphanEntries = db
    .prepare(
      `SELECT COUNT(*) AS c FROM transcript_entries te
     LEFT JOIN guests g ON te.guest_id = g.id
     WHERE g.id IS NULL`
    )
    .get().c;
  console.log(`   孤儿 transcript_entries: ${orphanEntries} (应为 0)`);

  const orphanConsensus = db
    .prepare(
      `SELECT COUNT(*) AS c FROM consensus_items ci
     LEFT JOIN discussions d ON ci.discussion_id = d.id
     WHERE d.id IS NULL`
    )
    .get().c;
  console.log(`   孤儿 consensus_items: ${orphanConsensus} (应为 0)`);

  const orphanDivergence = db
    .prepare(
      `SELECT COUNT(*) AS c FROM divergence_items di
     LEFT JOIN discussions d ON di.discussion_id = d.id
     WHERE d.id IS NULL`
    )
    .get().c;
  console.log(`   孤儿 divergence_items: ${orphanDivergence} (应为 0)`);

  // 检查时间连续性: 每个讨论内 sequence_number 是否连续
  const seqGaps = db
    .prepare(
      `
    WITH seq_check AS (
      SELECT discussion_id, sequence_number,
             ROW_NUMBER() OVER (PARTITION BY discussion_id ORDER BY sequence_number) AS rn
      FROM transcript_entries
    )
    SELECT discussion_id FROM seq_check
    WHERE sequence_number != rn
    GROUP BY discussion_id
    `
    )
    .all();
  console.log(
    `   时间序列缺口: ${seqGaps.length} 个讨论 (应为 0)`
  );

  // 按讨论查看发言分布
  const distByDisc = db
    .prepare(
      `
    SELECT d.topic, d.status, COUNT(te.id) AS entries
    FROM discussions d
    LEFT JOIN transcript_entries te ON te.discussion_id = d.id
    GROUP BY d.id
    ORDER BY d.created_at
    `
    )
    .all();

  console.log("\n📋 讨论发言分布:");
  for (const row of distByDisc) {
    console.log(
      `   [${row.status.padEnd(10)}] ${row.topic.padEnd(20)} ${row.entries} 条`
    );
  }

  console.log("\n✅ 数据生成完毕！");
  console.log(`📁 数据库路径: ${DB_PATH}\n`);

  db.close();
}

main();
