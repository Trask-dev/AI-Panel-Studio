"""SpeechGenerator — LLM 驱动的发言生成器。

为每位嘉宾构建 System Prompt（含姓名、立场、性格）+
对话历史上下文，调用 Deepseek V4 生成符合人设的真实回复。
"""

import json
from typing import Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.services.llm_client import LLMClient


class SpeechGenerator:
    """LLM 发言生成器。"""

    def __init__(self, llm: LLMClient):
        self._llm = llm

    # -------------------------------------------------------------------------
    # Public API
    # -------------------------------------------------------------------------

    def generate_by_name(
        self, db: Session, guest_name: str, entry_type: str
    ) -> str:
        """便捷方法: 根据嘉宾姓名和发言类型生成发言。

        自动查找嘉宾信息、讨论上下文和当前轮次。
        签名适配 Orchestrator 的 speech_fn(guest_name, entry_type) → str。
        """
        # 1. 查嘉宾
        guest_row = db.execute(
            text(
                "SELECT g.*, d.topic, d.id as did, d.round_count "
                "FROM guests g "
                "JOIN discussions d ON g.discussion_id = d.id "
                "WHERE g.name = :name AND g.is_active = 1 "
                "ORDER BY g.created_at DESC LIMIT 1"
            ),
            {"name": guest_name},
        ).fetchone()

        if guest_row is None:
            return self._fallback({"name": guest_name}, entry_type)

        guest = dict(guest_row._mapping)
        did = guest["did"]
        round_num = guest.get("round_count", 0) + 1

        # 2. 生成发言
        return self.generate(db, did, guest, entry_type, round_num)

    # -------------------------------------------------------------------------
    # Public API (原始)
    # -------------------------------------------------------------------------

    def generate(
        self,
        db: Session,
        discussion_id: str,
        guest: dict,
        entry_type: str,
        round_number: int,
    ) -> str:
        """生成嘉宾发言内容。

        Args:
            db: 数据库 session。
            discussion_id: 讨论 UUID。
            guest: 嘉宾数据字典 (含 name, title, stance, persona_prompt)。
            entry_type: 发言类型 (opening_statement/position_statement/speech/rebuttal/...)。
            round_number: 当前轮次。

        Returns:
            LLM 生成的自然语言发言文本。
        """
        # 1. 构建 System Prompt
        system = self._build_system_prompt(db, discussion_id, guest, entry_type)

        # 2. 收集对话历史
        history = self._collect_history(db, discussion_id)

        # 3. 构建 User Prompt
        user = self._build_user_prompt(guest, entry_type, round_number, history)

        # 4. 调用 LLM
        prompt = f"{system}\n\n---\n\n{user}"
        try:
            response = self._llm.generate_sync(prompt)
            # 清理响应（去除可能的 JSON 包装）
            return self._clean_response(response)
        except Exception:
            return self._fallback(guest, entry_type)

    # -------------------------------------------------------------------------
    # Private: Prompt 构建
    # -------------------------------------------------------------------------

    def _build_system_prompt(
        self, db: Session, did: str, guest: dict, entry_type: str
    ) -> str:
        """构建 System Prompt。"""
        topic = self._get_topic(db, did)
        persona = guest.get("persona_prompt", "")
        stance = guest.get("stance", "")
        name = guest.get("name", "嘉宾")
        title = guest.get("title", "")

        type_hints = {
            "opening_statement": "你是主持人，现在请做一个开场白，介绍话题并欢迎嘉宾。2-3句话，热情专业。",
            "position_statement": f"请用2-3句话阐述你对'{topic}'的核心立场。态度鲜明，有理有据。",
            "speech": "请用2-3句话发表你的看法。可以引入数据、案例或个人经验。",
            "rebuttal": "请用2-3句话反驳对方的观点。保持专业，用逻辑和证据说话。",
            "supplement": "请用2-3句话补充新观点或数据。",
            "question": "作为主持人，请提一个尖锐但有深度的问题，推动讨论深入。1-2句话。",
            "host_summary": "作为主持人，请做一个总结发言。覆盖核心共识、主要分歧和你的点评。3-5句话。",
        }

        hint = type_hints.get(entry_type, "请发言。2-3句话。")

        return (
            f"你是{name}，{title}。\n\n"
            f"你的核心立场：{stance}\n\n"
            f"人格设定：{persona}\n\n"
            f"你现在正在参加一场关于「{topic}」的圆桌讨论。\n"
            f"规则：{hint}\n"
            f"要求：用中文发言，语气自然像真人对话，不要用JSON格式，直接输出发言内容。"
        )

    def _build_user_prompt(
        self,
        guest: dict,
        entry_type: str,
        round_number: int,
        history: str,
    ) -> str:
        """构建 User Prompt。"""
        name = guest.get("name", "嘉宾")

        parts = [f"当前轮次：第 {round_number} 轮"]

        if history:
            parts.append(f"\n最近的讨论记录：\n{history}")
        else:
            parts.append("\n讨论刚刚开始，这是你的第一次发言。")

        parts.append(f"\n现在请以{name}的身份发言：")

        return "\n".join(parts)

    # -------------------------------------------------------------------------
    # Private: 数据收集
    # -------------------------------------------------------------------------

    def _get_topic(self, db: Session, did: str) -> str:
        row = db.execute(
            text("SELECT topic FROM discussions WHERE id = :did"), {"did": did}
        ).fetchone()
        return row.topic if row else "未知话题"

    def _collect_history(self, db: Session, did: str) -> str:
        """收集最近 10 条发言作为上下文。"""
        rows = db.execute(
            text(
                "SELECT g.name, g.role, te.entry_type, te.content "
                "FROM transcript_entries te "
                "JOIN guests g ON te.guest_id = g.id "
                "WHERE te.discussion_id = :did "
                "ORDER BY te.sequence_number DESC "
                "LIMIT 10"
            ),
            {"did": did},
        ).fetchall()

        if not rows:
            return ""

        lines = []
        for r in reversed(rows):
            lines.append(f"[{r.role}] {r.name}: {r.content}")
        return "\n".join(lines)

    # -------------------------------------------------------------------------
    # Private: 响应清理
    # -------------------------------------------------------------------------

    def _clean_response(self, raw: str) -> str:
        """清理 LLM 响应：去除 JSON 包装、多余空白。"""
        text = raw.strip()

        # 尝试移除 JSON 包装
        if text.startswith("{") and text.endswith("}"):
            try:
                data = json.loads(text)
                if isinstance(data, dict):
                    text = data.get("content", data.get("speech", raw))
            except (json.JSONDecodeError, TypeError):
                pass

        # 移除可能的引号包裹
        if text.startswith('"') and text.endswith('"'):
            text = text[1:-1]

        return text.strip() or raw.strip()

    # -------------------------------------------------------------------------
    # Private: 降级
    # -------------------------------------------------------------------------

    def _fallback(self, guest: dict, entry_type: str) -> str:
        """LLM 不可用时的降级发言。"""
        name = guest.get("name", "嘉宾")
        stance = guest.get("stance", "")
        templates = {
            "opening_statement": f"欢迎各位来到今天的圆桌讨论。我是{name}，很高兴能与各位专家一起探讨这个重要的话题。让我们先听听各位的观点。",
            "position_statement": f"我认为这个问题需要从多维度审视。{stance[:50]}...这是我的核心立场。",
            "speech": f"我想补充一个重要的视角。从我的专业领域来看，这个问题比表面看起来更加复杂。",
            "rebuttal": "我尊重你的观点，但我必须指出其中的逻辑漏洞。",
            "question": "我想追问一个更深层的问题：我们是否忽略了某些关键因素？",
            "host_summary": "感谢各位的精彩讨论。今天，我们触及了多个核心议题，也发现了值得进一步探索的分歧点。期待下一次对话。",
        }
        return templates.get(entry_type, f"我是{name}，这是我的发言。")
