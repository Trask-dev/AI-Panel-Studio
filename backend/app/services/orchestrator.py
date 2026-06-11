"""Orchestrator — 讨论流程编排引擎

核心职责:
  1. 管理 Discussion 状态机 (active → summarizing → finished)
  2. 管理 Guest 状态机 (idle ↔ thinking ↔ speaking ↔ waiting)
  3. 控制发言顺序与轮次推进
  4. 确保同一时刻仅 1 人 speaking (互斥锁)
  5. 支持多讨论并行隔离 (通过 discussion_id 分片)

依赖注入:
  - db: SQLAlchemy Session
  - speech_fn: (guest_name, entry_type) → content (可注入 Mock 或 LLM)
"""

from datetime import datetime, timezone
from typing import Callable

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.services.persona_generator import GuestGenerator


# =============================================================================
# GuestStateMachine — Guest 状态流转
# =============================================================================

class GuestStateMachine:
    """嘉宾状态机。

    合法转换:
      idle → thinking   (自发举手)
      idle → speaking   (被主持人点名)
      idle → idle       (保持聆听)
      thinking → speaking (主持人确认/抢到发言权)
      thinking → idle   (放弃发言/被抢先)
      speaking → waiting (发言结束)
      speaking → idle   (简短发言后直接归位)
      waiting → idle    (冷却完成)
      waiting → thinking (被反驳后再次举手)
      waiting → speaking (被主持人追问)
    """

    # 合法转换集合: (from, to)
    VALID_TRANSITIONS: set[tuple[str, str]] = {
        ("idle", "thinking"),
        ("idle", "speaking"),
        ("idle", "idle"),
        ("thinking", "speaking"),
        ("thinking", "idle"),
        ("speaking", "waiting"),
        ("speaking", "idle"),
        ("waiting", "idle"),
        ("waiting", "thinking"),
        ("waiting", "speaking"),
    }

    def can_transition(self, from_status: str, to_status: str) -> bool:
        """检查状态转换是否合法。"""
        return (from_status, to_status) in self.VALID_TRANSITIONS

    def transition(self, from_status: str, to_status: str) -> str:
        """执行状态转换。非法转换抛 ValueError。"""
        if not self.can_transition(from_status, to_status):
            raise ValueError(
                f"非法的 Guest 状态转换: {from_status} → {to_status}"
            )
        return to_status


# =============================================================================
# Orchestrator
# =============================================================================

def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class Orchestrator:
    """讨论流程编排器。

    Args:
        db: SQLAlchemy Session (每个 Discussion 独立调用, 但共享同一个 DB)。
        speech_fn: 发言内容生成函数 (guest_name, entry_type) → content。
                   测试中注入 mock_speech_generator，
                   生产环境注入 LLM 驱动的生成函数。
    """

    def __init__(
        self,
        db: Session,
        speech_fn: Callable[[str, str], str] | None = None,
    ):
        self.db = db
        self._speech = speech_fn or self._default_speech
        self._state_machine = GuestStateMachine()

    # -------------------------------------------------------------------------
    # Public API
    # -------------------------------------------------------------------------

    def start(self, discussion_id: str) -> None:
        """开始讨论: 校验状态 → 生成开场白 → 设为 active。"""
        status = self._get_discussion_status(discussion_id)
        if status != "setup":
            raise ValueError(f"讨论状态应为 setup, 当前: {status}")

        host = self._get_host(discussion_id)
        if host is None:
            raise ValueError("讨论缺少主持人，无法开始")

        # 写开场白
        opening = self._speech(host.name, "opening_statement")
        self._insert_entry(
            discussion_id, host.id, 1, 0, "opening_statement", opening
        )

        # 更新状态
        self._update_discussion(discussion_id, {
            "status": "active",
            "started_at": _now(),
        })

    def run_round(self, discussion_id: str) -> None:
        """运行一轮讨论: 主持人提问 → 各专家依次发言。"""
        status = self._get_discussion_status(discussion_id)
        if status != "active":
            raise ValueError(f"讨论状态应为 active, 当前: {status}")

        host = self._get_host(discussion_id)
        experts = self._get_experts(discussion_id)
        current_round = self._get_round_count(discussion_id)
        round_number = current_round + 1
        seq = self._next_sequence(discussion_id)

        # 1. 主持人提问 (非首轮)
        if round_number > 1:
            question = self._speech(host.name, "question")
            self._insert_entry(
                discussion_id, host.id, seq, round_number, "question", question
            )
            seq += 1

        # 2. 各专家发言
        for expert in experts:
            # thinking
            self.set_guest_status(discussion_id, expert.id, "thinking")
            # speaking
            self.set_guest_status(discussion_id, expert.id, "speaking")

            entry_type = "position_statement" if round_number == 1 else "speech"
            content = self._speech(expert.name, entry_type)
            self._insert_entry(
                discussion_id, expert.id, seq, round_number, entry_type, content
            )
            seq += 1

            # 发言结束 → waiting
            self.set_guest_status(discussion_id, expert.id, "waiting")

        # 3. 所有专家冷却结束 → idle
        for expert in experts:
            self.set_guest_status(discussion_id, expert.id, "idle")

        # 4. 轮次 +1
        self._update_discussion(discussion_id, {"round_count": round_number})

        # 5. 检查是否达到 max_rounds
        max_rounds = self._get_max_rounds(discussion_id)
        if max_rounds is not None and round_number >= max_rounds:
            self._update_discussion(discussion_id, {"status": "summarizing"})

    def finish(self, discussion_id: str) -> None:
        """正常结束讨论: 生成 Host 总结 → 设为 finished。"""
        status = self._get_discussion_status(discussion_id)
        if status not in ("active", "summarizing"):
            raise ValueError(f"讨论状态应为 active 或 summarizing, 当前: {status}")

        # 设为 summarizing 并生成总结
        self._update_discussion(discussion_id, {"status": "summarizing"})

        host = self._get_host(discussion_id)
        summary = self._speech(host.name, "host_summary")
        seq = self._next_sequence(discussion_id)
        self._insert_entry(
            discussion_id, host.id, seq, 0, "host_summary", summary
        )

        self._update_discussion(discussion_id, {
            "status": "finished",
            "finished_at": _now(),
        })

    def force_stop(self, discussion_id: str) -> None:
        """强制终止 (不生成总结)。"""
        self._update_discussion(discussion_id, {
            "status": "finished",
            "finished_at": _now(),
        })

    # -------------------------------------------------------------------------
    # 嘉宾状态管理
    # -------------------------------------------------------------------------

    def set_guest_status(
        self, discussion_id: str, guest_id: str, new_status: str
    ) -> None:
        """设置嘉宾状态，含转换校验 + 说话锁。"""
        current = self._get_guest_status(discussion_id, guest_id)

        # 状态机校验
        self._state_machine.transition(current, new_status)

        # 说话锁: 若目标是 speaking, 确保同讨论无其他人 speaking
        if new_status == "speaking":
            speaking_count = self.db.execute(
                text(
                    "SELECT COUNT(*) as c FROM guests "
                    "WHERE discussion_id = :did AND status = 'speaking'"
                    "  AND id != :gid"
                ),
                {"did": discussion_id, "gid": guest_id},
            ).fetchone().c
            if speaking_count > 0:
                raise ValueError("已有其他嘉宾在发言，无法同时 speaking")

        self.db.execute(
            text("UPDATE guests SET status = :st, updated_at = :now "
                 "WHERE id = :gid AND discussion_id = :did"),
            {
                "st": new_status, "gid": guest_id,
                "did": discussion_id, "now": _now(),
            },
        )
        self.db.commit()

    # -------------------------------------------------------------------------
    # Private: 数据库查询
    # -------------------------------------------------------------------------

    def _get_discussion_status(self, did: str) -> str:
        row = self.db.execute(
            text("SELECT status FROM discussions WHERE id = :did"), {"did": did}
        ).fetchone()
        if row is None:
            raise ValueError(f"讨论不存在: {did}")
        return row.status

    def _get_host(self, did: str):
        return self.db.execute(
            text("SELECT * FROM guests WHERE discussion_id = :did AND role = 'host'"),
            {"did": did},
        ).fetchone()

    def _get_experts(self, did: str):
        return self.db.execute(
            text(
                "SELECT * FROM guests "
                "WHERE discussion_id = :did AND role = 'expert' AND is_active = 1 "
                "ORDER BY speech_order"
            ),
            {"did": did},
        ).fetchall()

    def _get_round_count(self, did: str) -> int:
        return self.db.execute(
            text("SELECT round_count FROM discussions WHERE id = :did"),
            {"did": did},
        ).fetchone().round_count

    def _get_max_rounds(self, did: str) -> int | None:
        return self.db.execute(
            text("SELECT max_rounds FROM discussions WHERE id = :did"),
            {"did": did},
        ).fetchone().max_rounds

    def _get_guest_status(self, did: str, gid: str) -> str:
        return self.db.execute(
            text("SELECT status FROM guests WHERE id = :gid AND discussion_id = :did"),
            {"gid": gid, "did": did},
        ).fetchone().status

    def _next_sequence(self, did: str) -> int:
        row = self.db.execute(
            text(
                "SELECT COALESCE(MAX(sequence_number), 0) + 1 AS nxt "
                "FROM transcript_entries WHERE discussion_id = :did"
            ),
            {"did": did},
        ).fetchone()
        return row.nxt

    def _insert_entry(
        self, did: str, gid: str, seq: int, rnd: int,
        entry_type: str, content: str,
    ) -> None:
        import uuid
        now = _now()
        self.db.execute(
            text(
                "INSERT INTO transcript_entries "
                "(id, discussion_id, guest_id, sequence_number, round_number, "
                " entry_type, content, is_final, spoken_at, created_at) "
                "VALUES "
                "(:id, :did, :gid, :seq, :rnd, :typ, :cnt, 1, :now, :now)"
            ),
            {
                "id": str(uuid.uuid4()), "did": did, "gid": gid,
                "seq": seq, "rnd": rnd, "typ": entry_type, "cnt": content,
                "now": now,
            },
        )
        self.db.commit()

    def _update_discussion(self, did: str, fields: dict) -> None:
        sets = ", ".join(f"{k} = :{k}" for k in fields)
        params = {**fields, "did": did, "now": _now()}
        if "updated_at" not in fields:
            sets += ", updated_at = :now"
        self.db.execute(
            text(f"UPDATE discussions SET {sets} WHERE id = :did"), params
        )
        self.db.commit()

    # -------------------------------------------------------------------------
    # Private: 默认发言生成 (降级)
    # -------------------------------------------------------------------------

    @staticmethod
    def _default_speech(guest_name: str, entry_type: str) -> str:
        """LLM 未注入时的默认发言。"""
        return f"[{guest_name}] 的{entry_type}发言。"
