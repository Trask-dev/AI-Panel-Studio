"""测试数据工厂 (Test Data Factories)。

提供便捷的工厂函数，用于在测试中快速创建符合 Schema 的测试数据。
所有工厂接受 db_session 参数，在单个事务内完成插入。

使用示例:
    from tests.factories import DiscussionFactory, GuestFactory

    # 创建完整讨论 (含主持人 + 3 专家)
    disc, guests = DiscussionFactory.create_full(
        db_session,
        topic="AI 的未来",
        expert_count=3,
        status="active",
    )

    # 创建发言记录
    entries = TranscriptFactory.create_round(
        db_session,
        discussion_id=disc_id,
        guests=guests,
        round_number=1,
    )
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import text
from sqlalchemy.orm import Session


# =============================================================================
# 辅助函数
# =============================================================================

def _uid() -> str:
    """生成 UUID 字符串。"""
    return str(uuid.uuid4())


def _now() -> str:
    """返回当前 ISO8601 UTC 时间字符串。"""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _iso(dt: datetime | None = None, offset_seconds: int = 0) -> str:
    """格式化 ISO8601 时间，支持偏移。

    Args:
        dt: 基准时间，None 表示当前 UTC。
        offset_seconds: 相对基准的偏移秒数。
    """
    if dt is None:
        dt = datetime.now(timezone.utc)
    from datetime import timedelta
    adjusted = dt + timedelta(seconds=offset_seconds)
    return adjusted.strftime("%Y-%m-%dT%H:%M:%SZ")


# =============================================================================
# 预设常量
# =============================================================================

# 8 种专家颜色 (与 tokens.css 一致)
EXPERT_COLORS = [
    "#4a90d9",  # 蓝
    "#d94a4a",  # 红
    "#50b86c",  # 绿
    "#7b61ff",  # 紫
    "#ff8c42",  # 橙
    "#20b2aa",  # 青
    "#ff6b6b",  # 珊瑚
    "#b8860b",  # 暗金
]

# 预设立场模板 (用于快速生成测试数据)
STANCE_TEMPLATES = [
    {"label": "乐观派",    "stance": "对AI技术发展持积极态度，认为技术进步将创造更多机会"},
    {"label": "谨慎派",    "stance": "对AI的快速部署持审慎态度，强调风险管控"},
    {"label": "务实派",    "stance": "主张在技术创新与社会保障之间寻求平衡"},
    {"label": "反对派",    "stance": "对AI的大规模应用持否定立场，强调其破坏性影响"},
    {"label": "中立观察者", "stance": "保持中立立场，关注各方论据的合理性"},
    {"label": "技术专家",   "stance": "从技术可行性角度分析问题，注重数据与实证"},
    {"label": "人文学者",   "stance": "从人文关怀角度审视技术变革，关注社会公平"},
    {"label": "政策倡导者", "stance": "主张通过政策引导确保技术发展方向符合公共利益"},
]

# 预设立场语句模板 (按专家索引取模)
OPENING_LINES = [
    "我赞同这一观点，但需要补充几点关键数据...",
    "我必须在此提出不同看法——现有证据并不支持这一结论...",
    "从政策制定的角度来看，这个问题需要分阶段讨论...",
    "作为一个长期关注该领域的从业者，我认为核心矛盾在于...",
]


# =============================================================================
# GuestFactory — 嘉宾数据
# =============================================================================

class GuestFactory:
    """嘉宾数据工厂。

    生成单个 Guest 行的 INSERT 参数。
    """

    @staticmethod
    def build_host(
        discussion_id: str,
        name: str = "张明远",
        title: str = "资深科技评论员",
        **overrides,
    ) -> dict:
        """构建主持人数据。

        Args:
            discussion_id: 所属讨论 UUID。
            name: 主持人姓名。
            title: 职业/头衔。
            **overrides: 覆盖任意字段 (bio, stance, color, ...)。
        """
        defaults = {
            "id": _uid(),
            "discussion_id": discussion_id,
            "role": "host",
            "name": name,
            "title": title,
            "bio": f"{name}，{title}，拥有15年行业经验，主持过多场高水平讨论。",
            "stance": "保持中立客观，致力于发掘各方观点背后的逻辑与证据",
            "stance_label": "主持人",
            "color": "#E8A840",            # 金色 — Host 专属
            "avatar_url": None,
            "status": "idle",
            "speech_order": 0,
            "persona_prompt": f"你是{name}，{title}。你的主持风格是保持中立、善于追问...",
            "is_active": 1,
            "created_at": _now(),
            "updated_at": _now(),
        }
        defaults.update(overrides)
        return defaults

    @staticmethod
    def build_expert(
        discussion_id: str,
        index: int,
        name: str | None = None,
        stance_label: str | None = None,
        **overrides,
    ) -> dict:
        """构建专家数据。

        Args:
            discussion_id: 所属讨论 UUID。
            index: 专家序号 (0-based), 决定颜色和默认立场。
            name: 专家姓名 (None 则自动生成)。
            stance_label: 立场标签 (None 则根据 index 从模板选取)。
            **overrides: 覆盖任意字段。
        """
        template = STANCE_TEMPLATES[index % len(STANCE_TEMPLATES)]
        expert_names = ["李思涵", "王建国", "陈雪梅", "周正宇", "沈一诺", "钱伟成", "郑佳慧", "刘志强"]

        guest_name = name or expert_names[index % len(EXPERT_COLORS)]
        guest_title = f"{template['label']}代表"
        defaults = {
            "id": _uid(),
            "discussion_id": discussion_id,
            "role": "expert",
            "name": guest_name,
            "title": guest_title,
            "bio": f"在相关领域有深入研究，立场鲜明——{template['stance']}。",
            "stance": template["stance"],
            "stance_label": stance_label or template["label"],
            "color": EXPERT_COLORS[index % len(EXPERT_COLORS)],
            "avatar_url": None,
            "status": "idle",
            "speech_order": index + 1,
            "persona_prompt": (
                f"你是{guest_name}，{guest_title}。"
                f"你的核心立场是：{template['stance']}。"
                f"在讨论中保持自己的专业视角，主动发言、补充、反驳，但保持专业和礼貌。"
            ),
            "is_active": 1,
            "created_at": _now(),
            "updated_at": _now(),
        }
        defaults.update(overrides)
        return defaults

    @staticmethod
    def insert_one(db: Session, **kwargs) -> str:
        """插入单条 Guest 并返回其 id。"""
        data = kwargs
        db.execute(
            text("""
                INSERT INTO guests (
                    id, discussion_id, role, name, title, bio,
                    stance, stance_label, color, avatar_url,
                    status, speech_order, persona_prompt,
                    is_active, created_at, updated_at
                ) VALUES (
                    :id, :discussion_id, :role, :name, :title, :bio,
                    :stance, :stance_label, :color, :avatar_url,
                    :status, :speech_order, :persona_prompt,
                    :is_active, :created_at, :updated_at
                )
            """),
            data,
        )
        return data["id"]

    @staticmethod
    def create_lineup(
        db: Session,
        discussion_id: str,
        expert_count: int = 3,
        **overrides,
    ) -> list[dict]:
        """创建完整嘉宾阵容 (1 Host + N Expert)。

        Args:
            db: 数据库 session。
            discussion_id: 所属讨论 UUID。
            expert_count: 专家人数 (2-8)。
            **overrides: 传递给所有 Guest 的额外参数。

        Returns:
            list[dict]: 全部 Guest 数据字典列表 (顺序: Host → Expert 0 → Expert 1 → ...)。
        """
        guests = []

        # 主持人
        host = GuestFactory.build_host(discussion_id, **overrides)
        GuestFactory.insert_one(db, **host)
        guests.append(host)

        # 专家
        for i in range(expert_count):
            expert = GuestFactory.build_expert(discussion_id, index=i, **overrides)
            GuestFactory.insert_one(db, **expert)
            guests.append(expert)

        return guests


# =============================================================================
# DiscussionFactory — 讨论会话数据
# =============================================================================

class DiscussionFactory:
    """讨论会话数据工厂。

    支持创建 pure discussion 或包含完整 Guest 阵容的讨论。
    """

    DEFAULT_CONFIG = {
        "host_style": "socratic",
        "llm_model": "claude-sonnet-4-20250514",
        "llm_config": '{"temperature": 0.7, "max_tokens": 2048}',
        "interjection_mode": "moderated",
    }

    @staticmethod
    def build(
        topic: str = "AI会取代人类工作吗",
        topic_description: str | None = None,
        expert_count: int = 3,
        status: str = "setup",
        max_rounds: int | None = 10,
        **overrides,
    ) -> dict:
        """构建 Discussion 数据字典 (不插入 DB)。

        Args:
            topic: 讨论话题。
            topic_description: 话题补充背景。
            expert_count: 专家人数 (不含 Host)。
            status: 初始状态。
            max_rounds: 最大轮次。
            **overrides: 覆盖任意字段。
        """
        now = _now()
        defaults = {
            "id": _uid(),
            "topic": topic,
            "topic_description": topic_description,
            "host_style": DiscussionFactory.DEFAULT_CONFIG["host_style"],
            "expert_count": expert_count,
            "status": status,
            "round_count": 0,
            "max_rounds": max_rounds,
            "started_at": now if status != "setup" else None,
            "finished_at": None,
            "llm_model": DiscussionFactory.DEFAULT_CONFIG["llm_model"],
            "llm_config": DiscussionFactory.DEFAULT_CONFIG["llm_config"],
            "interjection_mode": DiscussionFactory.DEFAULT_CONFIG["interjection_mode"],
            "created_at": now,
            "updated_at": now,
        }
        defaults.update(overrides)
        return defaults

    @staticmethod
    def create(db: Session, **overrides) -> dict:
        """创建单条 Discussion 并返回数据字典。"""
        data = DiscussionFactory.build(**overrides)
        db.execute(
            text("""
                INSERT INTO discussions (
                    id, topic, topic_description, host_style, expert_count,
                    status, round_count, max_rounds,
                    started_at, finished_at,
                    llm_model, llm_config, interjection_mode,
                    created_at, updated_at
                ) VALUES (
                    :id, :topic, :topic_description, :host_style, :expert_count,
                    :status, :round_count, :max_rounds,
                    :started_at, :finished_at,
                    :llm_model, :llm_config, :interjection_mode,
                    :created_at, :updated_at
                )
            """),
            data,
        )
        return data

    @staticmethod
    def create_full(
        db: Session,
        topic: str = "AI会取代人类工作吗",
        expert_count: int = 3,
        status: str = "active",
        max_rounds: int | None = 10,
        **overrides,
    ) -> tuple[dict, list[dict]]:
        """创建完整讨论 + 嘉宾阵容。

        Returns:
            (discussion_dict, guest_dicts): 讨论数据 + 嘉宾列表 (Host 在前)。
        """
        discussion = DiscussionFactory.create(
            db,
            topic=topic,
            expert_count=expert_count,
            status=status,
            max_rounds=max_rounds,
            started_at=_now() if status != "setup" else None,
            **overrides,
        )
        guests = GuestFactory.create_lineup(
            db,
            discussion_id=discussion["id"],
            expert_count=expert_count,
        )
        return discussion, guests


# =============================================================================
# TranscriptFactory — 发言记录数据
# =============================================================================

class TranscriptFactory:
    """发言记录数据工厂。

    生成模拟的对话流，支持按轮次批量创建。
    """

    @staticmethod
    def build_entry(
        discussion_id: str,
        guest_id: str,
        sequence_number: int,
        round_number: int,
        entry_type: str = "speech",
        content: str = "这是一条测试发言内容。",
        **overrides,
    ) -> dict:
        """构建单条 TranscriptEntry 数据。

        Args:
            discussion_id: 所属讨论。
            guest_id: 发言嘉宾。
            sequence_number: 全局序号。
            round_number: 轮次号。
            entry_type: 发言类型。
            content: 发言内容。
        """
        defaults = {
            "id": _uid(),
            "discussion_id": discussion_id,
            "guest_id": guest_id,
            "sequence_number": sequence_number,
            "round_number": round_number,
            "entry_type": entry_type,
            "content": content,
            "quote_of": None,
            "is_final": 1,
            "spoken_at": _now(),
            "created_at": _now(),
        }
        defaults.update(overrides)
        return defaults

    @staticmethod
    def insert_one(db: Session, **kwargs) -> str:
        """插入单条发言并返回 id。"""
        data = kwargs
        db.execute(
            text("""
                INSERT INTO transcript_entries (
                    id, discussion_id, guest_id,
                    sequence_number, round_number,
                    entry_type, content, quote_of, is_final,
                    spoken_at, created_at
                ) VALUES (
                    :id, :discussion_id, :guest_id,
                    :sequence_number, :round_number,
                    :entry_type, :content, :quote_of, :is_final,
                    :spoken_at, :created_at
                )
            """),
            data,
        )
        return data["id"]

    @staticmethod
    def create_opening(
        db: Session,
        discussion_id: str,
        host_id: str,
        content: str | None = None,
    ) -> dict:
        """创建主持人开场白 (Round 0)。"""
        entry = TranscriptFactory.build_entry(
            discussion_id=discussion_id,
            guest_id=host_id,
            sequence_number=1,
            round_number=0,
            entry_type="opening_statement",
            content=content or (
                "欢迎各位来到今天的圆桌讨论。"
                "我们今天的主题非常值得深入探讨。"
                "让我们先听听各位专家的初步看法。"
            ),
        )
        TranscriptFactory.insert_one(db, **entry)
        return entry

    @staticmethod
    def create_position_statements(
        db: Session,
        discussion_id: str,
        experts: list[dict],
        start_seq: int = 2,
    ) -> list[dict]:
        """创建所有专家的立场陈述 (Round 1)。

        Args:
            db: 数据库 session。
            discussion_id: 讨论 UUID。
            experts: 专家数据列表 (不含 Host)。
            start_seq: 起始 sequence_number。

        Returns:
            创建的 entry 列表。
        """
        entries = []
        for i, expert in enumerate(experts):
            seq = start_seq + i
            entry = TranscriptFactory.build_entry(
                discussion_id=discussion_id,
                guest_id=expert["id"],
                sequence_number=seq,
                round_number=1,
                entry_type="position_statement",
                content=(
                    f"作为{expert.get('stance_label', '嘉宾')}，"
                    f"我认为这个问题需要从多个角度来审视。"
                    f"{OPENING_LINES[i % len(OPENING_LINES)]}"
                ),
            )
            TranscriptFactory.insert_one(db, **entry)
            entries.append(entry)
        return entries

    @staticmethod
    def create_round(
        db: Session,
        discussion_id: str,
        guests: list[dict],
        round_number: int,
        start_seq: int,
        entry_types: list[str] | None = None,
    ) -> list[dict]:
        """创建完整的一轮发言。

        Args:
            db: 数据库 session。
            discussion_id: 讨论 UUID。
            guests: 所有嘉宾列表 (Host at [0])。
            round_number: 轮次号。
            start_seq: 起始 sequence_number。
            entry_types: 每人的发言类型 (长度应与 guests 一致)。
                         默认: Host 提问, Experts 常规发言。

        Returns:
            创建的 entry 列表。
        """
        if entry_types is None:
            entry_types = ["question"] + ["speech"] * (len(guests) - 1)

        entries = []
        for i, guest in enumerate(guests):
            seq = start_seq + i
            entry_type = entry_types[i] if i < len(entry_types) else "speech"
            entry = TranscriptFactory.build_entry(
                discussion_id=discussion_id,
                guest_id=guest["id"],
                sequence_number=seq,
                round_number=round_number,
                entry_type=entry_type,
                content=f"[Round {round_number}] {guest['name']} 的{entry_type}发言 —— 测试数据",
            )
            TranscriptFactory.insert_one(db, **entry)
            entries.append(entry)
        return entries

    @staticmethod
    def create_full_flow(
        db: Session,
        discussion_id: str,
        guests: list[dict],
        num_rounds: int = 3,
    ) -> list[dict]:
        """创建完整讨论流: 开场 → N 轮 → 总结。

        Args:
            db: 数据库 session。
            discussion_id: 讨论 UUID。
            guests: 所有嘉宾 (Host at [0])。
            num_rounds: 辩论轮数。

        Returns:
            全部 entry 列表。
        """
        all_entries = []
        seq = 1

        # 开场
        host = guests[0]
        opening = TranscriptFactory.create_opening(
            db, discussion_id, host["id"],
        )
        all_entries.append(opening)
        seq += 1

        # 立场陈述 (Round 1)
        experts = [g for g in guests if g["role"] == "expert"]
        positions = TranscriptFactory.create_position_statements(
            db, discussion_id, experts, start_seq=seq,
        )
        all_entries.extend(positions)
        seq += len(positions)

        # 辩论轮次 (Round 2 ~ N)
        for r in range(2, num_rounds + 1):
            _round = TranscriptFactory.create_round(
                db, discussion_id, guests, round_number=r, start_seq=seq,
            )
            all_entries.extend(_round)
            seq += len(_round)

        # 总结
        summary = TranscriptFactory.build_entry(
            discussion_id=discussion_id,
            guest_id=host["id"],
            sequence_number=seq,
            round_number=num_rounds + 1,
            entry_type="host_summary",
            content="感谢各位嘉宾的精彩讨论。今天我们触及了多个核心议题...",
        )
        TranscriptFactory.insert_one(db, **summary)
        all_entries.append(summary)

        return all_entries


# =============================================================================
# ConsensusFactory — 共识/分歧数据 (预留)
# =============================================================================

class ConsensusFactory:
    """共识与分歧数据工厂 (Green Phase 使用)。"""

    @staticmethod
    def create_consensus(
        db: Session,
        discussion_id: str,
        content: str,
        agreed_guest_ids: list[str],
        confidence: float = 0.85,
        source_entry_ids: list[str] | None = None,
    ) -> str:
        """创建单条共识项，返回 id。"""
        import json
        cid = _uid()
        now = _now()
        db.execute(
            text("""
                INSERT INTO consensus_items (
                    id, discussion_id, content, agreed_guests, confidence,
                    first_identified_at, last_reinforced_at,
                    is_active, source_entries, created_at, updated_at
                ) VALUES (
                    :id, :discussion_id, :content, :agreed_guests, :confidence,
                    :first_identified_at, :last_reinforced_at,
                    1, :source_entries, :created_at, :updated_at
                )
            """),
            {
                "id": cid,
                "discussion_id": discussion_id,
                "content": content,
                "agreed_guests": json.dumps(agreed_guest_ids),
                "confidence": confidence,
                "first_identified_at": now,
                "last_reinforced_at": now,
                "source_entries": json.dumps(source_entry_ids or []),
                "created_at": now,
                "updated_at": now,
            },
        )
        return cid

    @staticmethod
    def create_divergence(
        db: Session,
        discussion_id: str,
        content: str,
        parties: list[dict],
        severity: str = "moderate",
        source_entry_ids: list[str] | None = None,
    ) -> str:
        """创建单条分歧项，返回 id。"""
        import json
        did = _uid()
        now = _now()
        db.execute(
            text("""
                INSERT INTO divergence_items (
                    id, discussion_id, content, parties, severity,
                    first_identified_at, last_updated_at,
                    is_active, resolved, resolved_at, resolution_note,
                    source_entries, created_at, updated_at
                ) VALUES (
                    :id, :discussion_id, :content, :parties, :severity,
                    :first_identified_at, :last_updated_at,
                    1, 0, NULL, NULL,
                    :source_entries, :created_at, :updated_at
                )
            """),
            {
                "id": did,
                "discussion_id": discussion_id,
                "content": content,
                "parties": json.dumps(parties),
                "severity": severity,
                "first_identified_at": now,
                "last_updated_at": now,
                "source_entries": json.dumps(source_entry_ids or []),
                "created_at": now,
                "updated_at": now,
            },
        )
        return did
