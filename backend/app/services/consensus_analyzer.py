"""ConsensusAnalyzer — 共识/分歧实时提取引擎。

从 transcript 中分析各方观点，识别共识(ConsensusItem)与分歧(DivergenceItem)。
支持 LLM 驱动(full) 和 关键词匹配(fallback) 两种模式。
"""

import json
import uuid
from collections import Counter
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session


def _now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# ---------------------------------------------------------------------------
# 关键词 → 共识/分歧 信号 (fallback 模式)
# ---------------------------------------------------------------------------

CONSENSUS_SIGNALS = [
    "一致认为", "达成共识", "都认同", "同意", "我也认为",
    "我赞同", "我支持", "确实如此", "没有异议", "各方均认同",
    "我们有共识", "普遍认可", "共同看法",
]
DIVERGENCE_SIGNALS = [
    "我反对", "我不同意", "但问题是", "然而", "恰恰相反",
    "我持不同", "存在分歧", "这不是", "我质疑", "未必",
    "根本区别", "完全错误", "不赞同",
]


class ConsensusAnalyzer:
    """共识/分歧提取引擎。"""

    def __init__(self, llm_client: Any = None):
        self._llm = llm_client

    # -----------------------------------------------------------------------
    # Public API
    # -----------------------------------------------------------------------

    def analyze(self, db: Session, discussion_id: str) -> dict:
        """分析讨论的共识与分歧。

        Returns:
            {"consensus": [{"content": str, "guest_ids": [...]}],
             "divergences": [{"content": str, "parties": [...]}]}
        """
        entries = self._collect_entries(db, discussion_id)
        if len(entries) < 2:
            return {"consensus": [], "divergences": []}

        if self._llm:
            return self._llm_analyze(entries)
        return self._keyword_analyze(entries)

    def analyze_and_persist(self, db: Session, discussion_id: str) -> dict:
        """分析并持久化到数据库。"""
        result = self.analyze(db, discussion_id)

        # 清除旧活跃数据 → 写入新数据
        db.execute(
            text("UPDATE consensus_items SET is_active=0 WHERE discussion_id=:did"),
            {"did": discussion_id},
        )
        db.execute(
            text("UPDATE divergence_items SET is_active=0 WHERE discussion_id=:did"),
            {"did": discussion_id},
        )

        # 写入共识
        for c in result.get("consensus", []):
            cid = str(uuid.uuid4())
            now = _now()
            db.execute(
                text(
                    "INSERT INTO consensus_items "
                    "(id, discussion_id, content, agreed_guests, confidence, "
                    " first_identified_at, last_reinforced_at, is_active, "
                    " source_entries, created_at, updated_at) "
                    "VALUES (:id, :did, :content, :guests, :conf, "
                    " :first, :last, 1, :src, :now, :now)"
                ),
                {
                    "id": cid, "did": discussion_id, "content": c["content"],
                    "guests": json.dumps(c.get("guest_ids", [])),
                    "conf": c.get("confidence", 0.8),
                    "first": now, "last": now, "src": json.dumps(c.get("source_ids", [])),
                    "now": now,
                },
            )

        # 写入分歧
        for d in result.get("divergences", []):
            did_item = str(uuid.uuid4())
            now = _now()
            db.execute(
                text(
                    "INSERT INTO divergence_items "
                    "(id, discussion_id, content, parties, severity, "
                    " first_identified_at, last_updated_at, is_active, resolved, "
                    " source_entries, created_at, updated_at) "
                    "VALUES (:id, :did, :content, :parties, :sev, "
                    " :first, :last, 1, 0, :src, :now, :now)"
                ),
                {
                    "id": did_item, "did": discussion_id, "content": d["content"],
                    "parties": json.dumps(d.get("parties", [])),
                    "sev": d.get("severity", "moderate"),
                    "first": now, "last": now,
                    "src": json.dumps(d.get("source_ids", [])),
                    "now": now,
                },
            )

        db.commit()
        return result

    # -----------------------------------------------------------------------
    # Private: 数据采集
    # -----------------------------------------------------------------------

    def _collect_entries(self, db: Session, did: str) -> list[dict]:
        rows = db.execute(
            text(
                "SELECT te.id, te.guest_id, g.name as guest_name, "
                "te.content, te.sequence_number "
                "FROM transcript_entries te "
                "JOIN guests g ON te.guest_id = g.id "
                "WHERE te.discussion_id = :did "
                "ORDER BY te.sequence_number"
            ),
            {"did": did},
        ).fetchall()
        return [dict(r._mapping) for r in rows]

    # -----------------------------------------------------------------------
    # Fallback: 关键词匹配
    # -----------------------------------------------------------------------

    def _keyword_analyze(self, entries: list[dict]) -> dict:
        consensus, divergences = [], []
        # 简单规则: 检测一致/对立信号词
        agreeing = []
        opposing = []

        for e in entries:
            text = e.get("content", "")
            if any(sig in text for sig in CONSENSUS_SIGNALS):
                agreeing.append(e)
            if any(sig in text for sig in DIVERGENCE_SIGNALS):
                opposing.append(e)

        # 共识: 2+ 人表达一致信号
        if len(agreeing) >= 2:
            guest_ids = list({e["guest_id"] for e in agreeing})
            if len(guest_ids) >= 2:
                consensus.append({
                    "content": "各方在关键议题上表达了趋同立场",
                    "guest_ids": guest_ids,
                    "confidence": min(0.9, 0.5 + 0.1 * len(guest_ids)),
                    "source_ids": [e["id"] for e in agreeing[:3]],
                })

        # 分歧: 存在对立信号
        if len(opposing) >= 2:
            parties = []
            seen = set()
            for e in opposing:
                gid = e["guest_id"]
                if gid not in seen:
                    parties.append({
                        "stance": "持不同意见",
                        "guest_ids": [gid],
                    })
                    seen.add(gid)
            if len(parties) >= 2:
                divergences.append({
                    "content": "各方在实施路径上存在分歧",
                    "parties": parties,
                    "severity": "moderate" if len(parties) <= 2 else "sharp",
                    "source_ids": [e["id"] for e in opposing[:3]],
                })

        return {"consensus": consensus, "divergences": divergences}

    # -----------------------------------------------------------------------
    # LLM 模式 (Deepseek 驱动)
    # -----------------------------------------------------------------------

    def _llm_analyze(self, entries: list[dict]) -> dict:
        prompt = self._build_analysis_prompt(entries)
        try:
            response = self._llm.generate_sync(prompt)
            return self._parse_llm_response(response)
        except Exception:
            return self._keyword_analyze(entries)

    def _build_analysis_prompt(self, entries: list[dict]) -> str:
        lines = []
        for e in entries:
            lines.append(f"[{e['guest_name']}]: {e['content'][:200]}")
        transcript = "\n".join(lines)

        return f"""分析以下圆桌讨论记录，提取共识与分歧。

讨论记录:
{transcript}

请以 JSON 格式返回:
{{
  "consensus": [{{"content": "共识描述", "guest_ids": ["guest_id_1", "guest_id_2"]}}],
  "divergences": [{{"content": "分歧描述", "parties": [{{"stance": "立场", "guest_ids": ["..."]}}], "severity": "mild|moderate|sharp|fundamental"}}]
}}

如果无明显共识或分歧，返回空数组。
只返回 JSON，不要其他文字。"""

    def _parse_llm_response(self, raw: str) -> dict:
        text = raw.strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[1].rsplit("\n", 1)[0]
        data = json.loads(text)
        return {
            "consensus": data.get("consensus", []),
            "divergences": data.get("divergences", []),
        }
