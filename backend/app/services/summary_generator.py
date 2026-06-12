"""SummaryGenerator — 讨论总结生成器。

调用 LLM 根据完整 transcript + consensus/divergence 生成自然语言总结。
"""

import json
from typing import Any, Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

SYSTEM_PROMPT = """你是一位资深的圆桌会议主持人，刚刚主持完一场关于"{topic}"的深度讨论。

你的任务是撰写一段 300-500 字的自然语言总结。请遵循以下要求：

1. **开门见山**：第一段概述讨论的核心议题和整体氛围。
2. **核心共识**：列出 2-3 条各方达成的共识，用自然语言叙述，不用编号。
3. **主要分歧**：指出 1-2 个关键分歧点，简要说明各方立场。
4. **主持人点评**：以第一人称（"我认为"、"整体来看"）给出你的最终点评和展望。
5. **格式要求**：纯文本或 Markdown，禁止使用 JSON 格式。语言流畅自然，像一位真正的节目主持人在做结语。

以下是讨论的完整记录和相关数据，请据此撰写总结："""


class SummaryGenerator:
    """讨论总结生成器。"""

    def __init__(self, llm_client: Any = None):
        self._llm = llm_client

    # -------------------------------------------------------------------------
    # Public API
    # -------------------------------------------------------------------------

    def generate(
        self,
        db: Session,
        discussion_id: str,
    ) -> dict:
        """生成讨论总结并持久化。

        Args:
            db: 数据库 session。
            discussion_id: 讨论 UUID。

        Returns:
            含 content, key_findings, guest_contributions 的 dict。

        Raises:
            ValueError: 讨论不存在或无 transcript 记录。
            RuntimeError: LLM 调用失败且 fallback 也失败。
        """
        topic, transcript = self._collect_transcript(db, discussion_id)
        consensus = self._collect_consensus(db, discussion_id)
        divergences = self._collect_divergences(db, discussion_id)

        if not transcript:
            raise ValueError("讨论无发言记录，无法生成总结")

        # 尝试 LLM 生成
        content = self._try_llm_generate(topic, transcript, consensus, divergences)

        # 持久化
        import uuid
        from datetime import datetime, timezone

        sid = str(uuid.uuid4())
        now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

        db.execute(
            text(
                "INSERT OR REPLACE INTO discussion_summaries "
                "(id, discussion_id, content, key_findings, "
                " consensus_summary, divergence_summary, generation_model, created_at) "
                "VALUES (:id, :did, :content, :kf, :cs, :ds, :model, :now)"
            ),
            {
                "id": sid,
                "did": discussion_id,
                "content": content,
                "kf": json.dumps(self._extract_key_findings(content), ensure_ascii=False),
                "cs": json.dumps(consensus, ensure_ascii=False),
                "ds": json.dumps(divergences, ensure_ascii=False),
                "model": "llm" if self._llm else "fallback",
                "now": now,
            },
        )
        db.commit()

        return {"id": sid, "content": content, "discussion_id": discussion_id}

    # -------------------------------------------------------------------------
    # Private: 数据收集
    # -------------------------------------------------------------------------

    def _collect_transcript(self, db: Session, did: str) -> tuple[str, str]:
        rows = db.execute(
            text(
                "SELECT g.name, g.role, te.entry_type, te.content "
                "FROM transcript_entries te "
                "JOIN guests g ON te.guest_id = g.id "
                "WHERE te.discussion_id = :did "
                "ORDER BY te.sequence_number"
            ),
            {"did": did},
        ).fetchall()

        topic_row = db.execute(
            text("SELECT topic FROM discussions WHERE id = :did"), {"did": did}
        ).fetchone()
        topic = topic_row.topic if topic_row else "未知话题"

        lines = [f"[{r.role}] {r.name} ({r.entry_type}): {r.content}" for r in rows]
        return topic, "\n".join(lines)

    def _collect_consensus(self, db: Session, did: str) -> list[str]:
        rows = db.execute(
            text(
                "SELECT content FROM consensus_items "
                "WHERE discussion_id = :did AND is_active = 1"
            ),
            {"did": did},
        ).fetchall()
        return [r.content for r in rows]

    def _collect_divergences(self, db: Session, did: str) -> list[str]:
        rows = db.execute(
            text(
                "SELECT content FROM divergence_items "
                "WHERE discussion_id = :did AND is_active = 1"
            ),
            {"did": did},
        ).fetchall()
        return [r.content for r in rows]

    # -------------------------------------------------------------------------
    # Private: LLM 调用
    # -------------------------------------------------------------------------

    def _try_llm_generate(
        self, topic: str, transcript: str, consensus: list[str], divergences: list[str]
    ) -> str:
        prompt = f"{SYSTEM_PROMPT.format(topic=topic)}\n\n"
        prompt += f"## 讨论记录\n{transcript[:6000]}\n\n"
        if consensus:
            prompt += f"## 识别的共识\n" + "\n".join(f"- {c}" for c in consensus) + "\n\n"
        if divergences:
            prompt += f"## 识别的分歧\n" + "\n".join(f"- {d}" for d in divergences) + "\n\n"
        prompt += "请撰写总结："

        if self._llm:
            try:
                response = self._llm.generate(prompt)
                if hasattr(response, "__await__"):
                    import asyncio
                    response = asyncio.run(response)
                if isinstance(response, str):
                    return response[:2000]  # 限长
            except Exception:
                pass

        return self._fallback_summary(topic, consensus, divergences)

    def _fallback_summary(self, topic: str, consensus: list[str], divergences: list[str]) -> str:
        parts = [f"## 讨论总结：{topic}\n"]
        parts.append("本次讨论围绕核心议题展开了深入交流。各方嘉宾从不同角度分享了专业见解。\n")

        if consensus:
            parts.append("### 核心共识")
            for c in consensus:
                parts.append(f"- {c}")

        if divergences:
            parts.append("\n### 主要分歧")
            for d in divergences:
                parts.append(f"- {d}")

        parts.append("\n### 主持人点评")
        parts.append(
            "整体来看，本次讨论展现了这一议题的多维度特性。"
            "虽然各方在某些具体问题上存在分歧，但都认同深入对话和持续研究的重要性。"
            "期待未来有更多的数据和实践来帮助我们进一步厘清这些关键问题。"
        )
        return "\n".join(parts)

    def _extract_key_findings(self, content: str) -> list[str]:
        # 简单提取以 "- " 开头的行
        findings = []
        for line in content.split("\n"):
            stripped = line.strip()
            if stripped.startswith("- ") and len(stripped) > 3:
                findings.append(stripped[2:])
        return findings[:5]
