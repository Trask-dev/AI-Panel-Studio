"""test_orchestrator.py — Orchestrator 核心单元测试

覆盖 8 个测试场景:
  1. test_discussion_starts_with_opening_statement   开场白
  2. test_discussion_ends_with_host_summary          总结
  3. test_only_one_guest_speaking_at_a_time          说话锁
  4. test_guest_status_idle_to_thinking_to_speaking  状态流转
  5. test_guest_status_illegal_transition_rejected   非法转换
  6. test_round_advances_after_all_experts_speak     轮次推进
  7. test_max_rounds_triggers_summarizing            轮次上限
  8. test_parallel_discussions_independent           多讨论隔离
"""

import pytest
from sqlalchemy import text

from app.services.orchestrator import Orchestrator, GuestStateMachine
from tests.factories import DiscussionFactory, TranscriptFactory


# =============================================================================
# Mock LLM — 模拟发言内容生成
# =============================================================================

def mock_speech_generator(guest_name: str, entry_type: str) -> str:
    """模拟 LLM 为嘉宾生成发言内容。"""
    templates = {
        "opening_statement": f"欢迎各位。我是{guest_name}，今天我们来探讨一个重要的话题。",
        "position_statement": f"作为{guest_name}，我的核心观点是这个问题需要从多维度分析。",
        "speech": f"我想补充一点——{guest_name}认为现有证据支持我的立场。",
        "question": f"{guest_name}向各位专家提问：你们如何看这个问题？",
        "host_summary": "感谢各位今天的精彩讨论。我们触及了多个核心议题，达成了若干共识。",
    }
    return templates.get(entry_type, f"[{guest_name}] 的{entry_type}发言。")


# =============================================================================
# Orchestrator Fixture
# =============================================================================

@pytest.fixture
def orchestrator(db_session, llm_mock):
    """创建 Orchestrator 实例，注入 mock 依赖。"""
    return Orchestrator(db=db_session, speech_fn=mock_speech_generator)


@pytest.fixture
def setup_discussion(db_session):
    """创建一场 setup 状态的完整讨论 (1 Host + 3 Expert)。"""
    return DiscussionFactory.create_full(
        db_session,
        topic="测试讨论",
        expert_count=3,
        status="setup",
        max_rounds=5,
    )


# =============================================================================
# 测试类
# =============================================================================

class TestOrchestratorBasic:
    """基础流程测试。"""

    def test_discussion_starts_with_opening_statement(
        self, db_session, orchestrator, setup_discussion
    ):
        """讨论开始 → 产生 Host 开场白。"""
        disc, guests = setup_discussion
        host = guests[0]

        orchestrator.start(disc["id"])

        entries = db_session.execute(
            text(
                "SELECT * FROM transcript_entries "
                "WHERE discussion_id = :did ORDER BY sequence_number"
            ),
            {"did": disc["id"]},
        ).fetchall()

        assert len(entries) == 1
        assert entries[0].entry_type == "opening_statement"
        assert entries[0].guest_id == host["id"]

    def test_discussion_ends_with_host_summary(
        self, db_session, orchestrator, setup_discussion
    ):
        """正常结束 → 产生 Host 总结。"""
        disc, guests = setup_discussion

        orchestrator.start(disc["id"])
        orchestrator.finish(disc["id"])

        entries = db_session.execute(
            text(
                "SELECT entry_type FROM transcript_entries "
                "WHERE discussion_id = :did ORDER BY sequence_number"
            ),
            {"did": disc["id"]},
        ).fetchall()

        assert entries[0].entry_type == "opening_statement"
        assert entries[-1].entry_type == "host_summary"


class TestGuestStateMachine:
    """Guest 状态机单元测试。"""

    @pytest.mark.parametrize("from_s, to_s, expected", [
        ("idle", "thinking", True),
        ("thinking", "speaking", True),
        ("speaking", "waiting", True),
        ("waiting", "idle", True),
        ("speaking", "idle", True),         # 简短发言后直接归位
        ("waiting", "speaking", True),       # 主持人追问
        ("waiting", "thinking", True),       # 被反驳后再次举手
        # 非法转换
        ("idle", "waiting", False),
        ("thinking", "idle", True),          # 放弃发言
        ("idle", "idle", True),              # 保持状态
    ])
    def test_guest_status_transition(self, from_s, to_s, expected):
        """合法转换返回 True，非法转换返回 False。"""
        sm = GuestStateMachine()
        assert sm.can_transition(from_s, to_s) is expected

    def test_guest_status_illegal_transition_rejected(
        self, db_session, orchestrator, setup_discussion
    ):
        """尝试直接 idle → waiting 应被拒绝。"""
        disc, guests = setup_discussion
        expert = guests[1]

        with pytest.raises(ValueError, match="非法.*状态转换"):
            orchestrator.set_guest_status(
                disc["id"], expert["id"], "waiting"
            )


class TestRoundManagement:
    """轮次管理测试。"""

    def test_round_advances_after_all_experts_speak(
        self, db_session, orchestrator, setup_discussion
    ):
        """所有专家发言完毕 → round_count 递增。"""
        disc, guests = setup_discussion

        orchestrator.start(disc["id"])
        orchestrator.run_round(disc["id"])

        # 验证 round_count 已增加
        after = db_session.execute(
            text("SELECT round_count FROM discussions WHERE id = :did"),
            {"did": disc["id"]},
        ).fetchone()
        assert after.round_count == 1

        # 验证本轮的发言数 = 1 host question + 3 expert speeches
        entries = db_session.execute(
            text(
                "SELECT COUNT(*) as c FROM transcript_entries "
                "WHERE discussion_id = :did AND round_number = 1"
            ),
            {"did": disc["id"]},
        ).fetchone()
        # Round 1: 3 专家立场陈述 (无主持人提问)
        assert entries.c == 3, f"Round 1 应有 3 条立场陈述, 实际 {entries.c}"

    def test_max_rounds_triggers_summarizing(
        self, db_session, orchestrator, setup_discussion
    ):
        """达到 max_rounds → 自动触发总结。"""
        disc, guests = setup_discussion

        # 将 max_rounds 改为 2
        db_session.execute(
            text("UPDATE discussions SET max_rounds = 2 WHERE id = :did"),
            {"did": disc["id"]},
        )
        db_session.commit()

        orchestrator.start(disc["id"])
        orchestrator.run_round(disc["id"])  # Round 1
        orchestrator.run_round(disc["id"])  # Round 2 → 达到上限

        status = db_session.execute(
            text("SELECT status FROM discussions WHERE id = :did"),
            {"did": disc["id"]},
        ).fetchone().status

        assert status == "summarizing"


class TestSpeakingLock:
    """发言互斥锁测试。"""

    def test_only_one_guest_speaking_at_a_time(
        self, db_session, orchestrator, setup_discussion
    ):
        """同一时刻只能有 1 人 speaking。"""
        disc, guests = setup_discussion
        expert_a = guests[1]
        expert_b = guests[2]

        # A 开始发言
        orchestrator.set_guest_status(disc["id"], expert_a["id"], "thinking")
        orchestrator.set_guest_status(disc["id"], expert_a["id"], "speaking")

        # B 尝试直接 speaking → 应被拒绝
        orchestrator.set_guest_status(disc["id"], expert_b["id"], "thinking")
        with pytest.raises(ValueError, match="已有.*在发言"):
            orchestrator.set_guest_status(disc["id"], expert_b["id"], "speaking")

        # 验证只有 A 在 speaking
        count = db_session.execute(
            text(
                "SELECT COUNT(*) as c FROM guests "
                "WHERE discussion_id = :did AND status = 'speaking'"
            ),
            {"did": disc["id"]},
        ).fetchone().c
        assert count == 1


class TestParallelIsolation:
    """多讨论并行隔离测试。"""

    def test_parallel_discussions_independent(
        self, db_session, orchestrator
    ):
        """A 的发言不出现在 B 中。"""
        # 创建两场独立讨论 (setup → start → active)
        disc_a, guests_a = DiscussionFactory.create_full(
            db_session, topic="讨论A", expert_count=2, status="setup"
        )
        disc_b, guests_b = DiscussionFactory.create_full(
            db_session, topic="讨论B", expert_count=2, status="setup"
        )

        # A 开始并运行一轮
        orchestrator.start(disc_a["id"])
        orchestrator.run_round(disc_a["id"])

        # 验证 B 中没有任何 A 的发言
        cross = db_session.execute(
            text(
                "SELECT COUNT(*) as c FROM transcript_entries te "
                "JOIN guests g ON te.guest_id = g.id "
                "WHERE te.discussion_id = :did_b "
                "AND g.discussion_id = :did_a"
            ),
            {"did_a": disc_a["id"], "did_b": disc_b["id"]},
        ).fetchone().c

        assert cross == 0, f"A 的发言泄露到 B: {cross} 条"

        # B 不受影响: 没有任何 transcript
        b_count = db_session.execute(
            text(
                "SELECT COUNT(*) as c FROM transcript_entries "
                "WHERE discussion_id = :did"
            ),
            {"did": disc_b["id"]},
        ).fetchone().c
        assert b_count == 0


class TestForceStop:
    """强制终止测试。"""

    def test_force_stop_skips_summary(
        self, db_session, orchestrator, setup_discussion
    ):
        """强制终止 → 不生成总结。"""
        disc, guests = setup_discussion

        orchestrator.start(disc["id"])
        orchestrator.force_stop(disc["id"])

        status = db_session.execute(
            text("SELECT status FROM discussions WHERE id = :did"),
            {"did": disc["id"]},
        ).fetchone().status

        assert status == "finished"

        # 无 host_summary
        summaries = db_session.execute(
            text(
                "SELECT COUNT(*) as c FROM transcript_entries "
                "WHERE discussion_id = :did AND entry_type = 'host_summary'"
            ),
            {"did": disc["id"]},
        ).fetchone().c
        assert summaries == 0
