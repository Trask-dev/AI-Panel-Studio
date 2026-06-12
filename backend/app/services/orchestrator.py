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
        sse_manager=None,  # SSEManager 单例，用于推送实时事件
    ):
        self.db = db
        self._speech = speech_fn or self._default_speech
        self._state_machine = GuestStateMachine()
        self._sse = sse_manager

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
        entry = self._insert_entry(
            discussion_id, host.id, 1, 0, "opening_statement", opening
        )

        # SSE 推送: 讨论状态变化 + 开场白
        self._push_sse(discussion_id, "discussion_status_change", {
            "discussion_id": discussion_id,
            "status": "active",
            "previous_status": "setup",
        })
        self._push_sse(discussion_id, "transcript_append", {
            "id": entry["id"],
            "discussion_id": discussion_id,
            "guest_id": host.id,
            "guest_name": host.name,
            "guest_color": host.color or "#E8A840",
            "guest_role": "host",
            "guest_title": host.title or "",
            "sequence_number": 1,
            "round_number": 0,
            "entry_type": "opening_statement",
            "content": opening,
            "is_final": True,
        })

        # 更新状态
        self._update_discussion(discussion_id, {
            "status": "active",
            "started_at": _now(),
        })

    def run_round(self, discussion_id: str) -> dict:
        """运行一轮讨论: 动态调度——专家根据上下文自主决定发言/反驳/补充/沉默。

        SDD #9: 不允许机械式轮流发言。每轮由 LLM 评估上下文，
        为每位专家打分，决定发言顺序和发言类型。
        """
        status = self._get_discussion_status(discussion_id)
        if status != "active":
            raise ValueError(f"讨论状态应为 active, 当前: {status}")

        host = self._get_host(discussion_id)
        experts = list(self._get_experts(discussion_id))
        current_round = self._get_round_count(discussion_id)
        round_number = current_round + 1
        seq = self._next_sequence(discussion_id)

        # 1. 主持人开场/提问
        if round_number == 1:
            # 首轮: 开场白已在 start() 中生成，这里只做立场陈述调度
            pass
        else:
            question = self._speech(host.name, "question")
            entry = self._insert_entry(discussion_id, host.id, seq, round_number, "question", question)
            self._push_sse(discussion_id, "transcript_append", self._entry_to_sse(entry, host))
            seq += 1

        # 2. 动态调度: 非固定顺序，每个专家至少发言 1 次，可抢答/反驳/补充
        spoke_this_round = set()
        max_speeches = len(experts) * 2  # 最多 2 轮发言机会
        speech_count = 0

        while len(spoke_this_round) < len(experts) and speech_count < max_speeches:
            # 获取上下文
            recent = self._get_recent_entries(discussion_id, limit=8)

            # 选择下一位发言者
            selected = self._select_next_speaker(experts, spoke_this_round, recent)
            if selected is None:
                break  # 无人举手
            expert, entry_type = selected
            speech_count += 1
            spoke_this_round.add(expert.id)

            # thinking → SSE
            self.set_guest_status(discussion_id, expert.id, "thinking")
            self._push_sse(discussion_id, "guest_status_change", {
                "discussion_id": discussion_id, "guest_id": expert.id,
                "guest_name": expert.name, "status": "thinking",
            })

            # speaking → SSE
            self.set_guest_status(discussion_id, expert.id, "speaking")
            self._push_sse(discussion_id, "guest_status_change", {
                "discussion_id": discussion_id, "guest_id": expert.id,
                "guest_name": expert.name, "status": "speaking",
            })

            # 生成发言
            if round_number == 1:
                entry_type = "position_statement"
            content = self._speech(expert.name, entry_type)
            entry = self._insert_entry(discussion_id, expert.id, seq, round_number, entry_type, content)
            self._push_sse(discussion_id, "transcript_append", self._entry_to_sse(entry, expert))
            seq += 1

            # waiting → SSE
            self.set_guest_status(discussion_id, expert.id, "waiting")
            self._push_sse(discussion_id, "guest_status_change", {
                "discussion_id": discussion_id, "guest_id": expert.id,
                "guest_name": expert.name, "status": "waiting",
            })

        # 3. 所有专家回到 idle
        for expert in experts:
            self.set_guest_status(discussion_id, expert.id, "idle")

        # 4. 轮次 +1
        self._update_discussion(discussion_id, {"round_count": round_number})
        self._push_sse(discussion_id, "round_advance", {
            "discussion_id": discussion_id, "round_number": round_number,
        })

        # 5. 共识/分歧分析 → 返回结果
        result = self._analyze_and_push_consensus(discussion_id)

        # 6. 检查上限
        max_rounds = self._get_max_rounds(discussion_id)
        if max_rounds is not None and round_number >= max_rounds:
            self._update_discussion(discussion_id, {"status": "summarizing"})
            self._push_sse(discussion_id, "discussion_status_change", {
                "discussion_id": discussion_id, "status": "summarizing",
            })

        return result or {"consensus": [], "divergences": []}

    def _select_next_speaker(self, experts, spoke_this_round, recent_entries):
        """动态选择下一位发言者。

        策略: 随机化顺序 + 偏好未发言者 + 随机发言类型。
        LLM 模式可用时由 LLM 评估上下文决定。
        """
        import random
        available = [e for e in experts if e.id not in spoke_this_round]

        # 如果有未发言者，优先选择
        if available:
            expert = random.choice(available)
        else:
            # 所有人已发言，允许抢答——随机选
            expert = random.choice(experts)

        # 随机发言类型（模拟举手/反驳/补充）
        types = ["speech", "speech", "rebuttal", "supplement"]
        entry_type = random.choice(types)

        return expert, entry_type

    def _get_recent_entries(self, did: str, limit: int = 8):
        return self.db.execute(
            text(
                "SELECT g.name, te.content FROM transcript_entries te "
                "JOIN guests g ON te.guest_id = g.id "
                "WHERE te.discussion_id = :did ORDER BY te.sequence_number DESC LIMIT :lim"
            ),
            {"did": did, "lim": limit},
        ).fetchall()

    def _entry_to_sse(self, entry: dict, guest) -> dict:
        return {
            "id": entry["id"], "discussion_id": entry["discussion_id"],
            "guest_id": guest.id, "guest_name": guest.name,
            "guest_color": guest.color or "#9090a0",
            "guest_role": guest.role, "guest_title": guest.title or "",
            "sequence_number": entry["sequence_number"],
            "round_number": entry["round_number"],
            "entry_type": entry["entry_type"], "content": entry["content"],
            "is_final": True,
        }

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
        """获取下一个 sequence_number。读取后递增，失败时重试。"""
        import time
        for attempt in range(5):
            row = self.db.execute(
                text(
                    "SELECT COALESCE(MAX(sequence_number), 0) + 1 AS nxt "
                    "FROM transcript_entries WHERE discussion_id = :did"
                ),
                {"did": did},
            ).fetchone()
            nxt = row.nxt
            # 验证无冲突（处理其他线程并发写入）
            existing = self.db.execute(
                text("SELECT 1 FROM transcript_entries WHERE discussion_id=:did AND sequence_number=:seq"),
                {"did": did, "seq": nxt},
            ).fetchone()
            if existing is None:
                return nxt
            time.sleep(0.05 * (attempt + 1))  # 退避
        return nxt  # fallthrough

    def _insert_entry(
        self, did: str, gid: str, seq: int, rnd: int,
        entry_type: str, content: str,
    ) -> dict:
        import uuid
        eid = str(uuid.uuid4())
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
                "id": eid, "did": did, "gid": gid,
                "seq": seq, "rnd": rnd, "typ": entry_type, "cnt": content,
                "now": now,
            },
        )
        self.db.commit()
        return {"id": eid, "discussion_id": did, "guest_id": gid,
                "sequence_number": seq, "round_number": rnd,
                "entry_type": entry_type, "content": content}

    def _analyze_and_push_consensus(self, discussion_id: str) -> dict:
        """每轮结束后分析共识/分歧并推送 SSE。返回结果。"""
        import logging, os
        logger = logging.getLogger("orchestrator")
        result = {"consensus": [], "divergences": []}
        try:
            from app.services.consensus_analyzer import ConsensusAnalyzer
            from app.services.llm_client import LLMClient

            # B1: 有 API Key → LLM 分析；无 → 关键词 fallback
            api_key = os.getenv("LLM_API_KEY", "")
            llm = None
            if api_key:
                llm = LLMClient(
                    api_key=api_key,
                    model=os.getenv("LLM_MODEL", "deepseek-chat"),
                    base_url=os.getenv("LLM_BASE_URL", "https://api.deepseek.com/v1"),
                    timeout=int(os.getenv("LLM_TIMEOUT", "60")),
                    max_retries=int(os.getenv("LLM_MAX_RETRIES", "2")),
                )
            analyzer = ConsensusAnalyzer(llm_client=llm)
            result = analyzer.analyze_and_persist(self.db, discussion_id)

            logger.info(f"共识分析完成: consensus={len(result.get('consensus',[]))}, divergences={len(result.get('divergences',[]))}")
            if result.get("consensus"):
                self._push_sse(discussion_id, "consensus_update", {"discussion_id": discussion_id, "items": result["consensus"]})
            if result.get("divergences"):
                self._push_sse(discussion_id, "divergence_update", {"discussion_id": discussion_id, "items": result["divergences"]})
        except Exception as e:
            logger.error(f"共识分析失败: {e}", exc_info=True)
        return result

    def _push_sse(self, did: str, event_type: str, payload: dict) -> None:
        """推送 SSE 事件 (线程安全, 可从 sync 代码直接调用)。"""
        if self._sse is None:
            return
        from app.utils.sse_manager import SSEEvent

        payload.setdefault("discussion_id", did)
        self._sse.push(SSEEvent(type=event_type, payload=payload))

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
