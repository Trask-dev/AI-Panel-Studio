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

def _query_guest_stances(db: Session, entries: list[dict]) -> dict:
    """从 guests 表查询立场标签。"""
    if not entries:
        return {}
    guest_ids = list({e["guest_id"] for e in entries})
    if not guest_ids:
        return {}
    # SQLite 不支持 IN 参数化列表，手工拼接占位符
    placeholders = ",".join(f":g{i}" for i in range(len(guest_ids)))
    params = {f"g{i}": gid for i, gid in enumerate(guest_ids)}
    rows = db.execute(
        text(f"SELECT id, stance_label FROM guests WHERE id IN ({placeholders})"),
        params,
    ).fetchall()
    return {r.id: (r.stance_label or "嘉宾") for r in rows}


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
            return self._llm_analyze(db, entries)
        return self._keyword_analyze(db, entries)

    def analyze_and_persist(self, db: Session, discussion_id: str) -> dict:
        """分析并持久化到数据库。仅当新产生数据时才替换旧的。"""
        result = self.analyze(db, discussion_id)
        consensus_items = result.get("consensus", [])
        divergences_items = result.get("divergences", [])

        # 有新的共识 → 替换旧的
        if consensus_items:
            db.execute(
                text("UPDATE consensus_items SET is_active=0 WHERE discussion_id=:did"),
                {"did": discussion_id},
            )
        for c in consensus_items:
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

        # 有新的分歧 → 替换旧的
        if divergences_items:
            db.execute(
                text("UPDATE divergence_items SET is_active=0 WHERE discussion_id=:did"),
                {"did": discussion_id},
            )
        for d in divergences_items:
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
    # Fallback: 立场分析 (关键词兜底 + stance_label 对比)
    # -----------------------------------------------------------------------

    def _keyword_analyze(self, db: Session, entries: list[dict]) -> dict:
        # 1. 从 DB 查询嘉宾立场标签
        guest_stances = _query_guest_stances(db, entries)

        # 2. 关键词检测
        consensus, divergences = [], []
        for e in entries:
            text = e.get("content", "")
            e["_has_consensus_signal"] = any(sig in text for sig in CONSENSUS_SIGNALS)
            e["_has_divergence_signal"] = any(sig in text for sig in DIVERGENCE_SIGNALS)

        # 3. 立场分组（共识和分歧共用）
        stance_groups = {}
        for e in entries:
            gid = e["guest_id"]
            label = guest_stances.get(gid, "未知")
            if label not in stance_groups:
                stance_groups[label] = []
            stance_groups[label].append(e)

        # B2: 共识 = 关键词信号 OR 同立场≥2人
        agreeing = [e for e in entries if e["_has_consensus_signal"]]
        if len({e["guest_id"] for e in agreeing}) >= 2:
            consensus.append({
                "id": str(uuid.uuid4()),
                "content": "各方在关键议题上达成共识",
                "guest_ids": list({e["guest_id"] for e in agreeing}),
                "confidence": 0.75,
                "source_ids": [e["id"] for e in agreeing[:3]],
            })
        # 立场共识: 同立场 ≥2 人 → 自动生成共识
        if not consensus:
            for label, group_entries in stance_groups.items():
                if len(group_entries) >= 2 and label != "主持人":
                    gids = list({e["guest_id"] for e in group_entries})
                    consensus.append({
                        "id": str(uuid.uuid4()),
                        "content": f"「{label}」阵营在核心议题上达成共识",
                        "guest_ids": gids,
                        "confidence": 0.7,
                        "source_ids": [e["id"] for e in group_entries[:2]],
                    })
                    break  # 只取一组

        # 4. 分歧: 立场标签对立 → 必然有分歧
        if len(stance_groups) >= 2:
            parties = []
            for label, group_entries in stance_groups.items():
                gids = list({e["guest_id"] for e in group_entries})
                parties.append({"stance": label, "guest_ids": gids})
            severity = "sharp" if len(stance_groups) >= 3 else "moderate"
            divergences.append({
                "id": str(uuid.uuid4()),
                "content": f"各方在核心议题上存在立场分歧（{', '.join(stance_groups.keys())}）",
                "parties": parties,
                "severity": severity,
                "source_ids": [e["id"] for e in entries[:3]],
            })

        # 5. 关键词分歧（强化）
        opposing = [e for e in entries if e["_has_divergence_signal"]]
        if len({e["guest_id"] for e in opposing}) >= 2 and not divergences:
            parties = []
            for gid in {e["guest_id"] for e in opposing}:
                parties.append({"stance": guest_stances.get(gid, "反对"), "guest_ids": [gid]})
            divergences.append({
                "id": str(uuid.uuid4()),
                "content": "各方存在明显分歧",
                "parties": parties,
                "severity": "sharp" if len(parties) >= 3 else "moderate",
                "source_ids": [e["id"] for e in opposing[:3]],
            })

        return {"consensus": consensus, "divergences": divergences}

    # -----------------------------------------------------------------------
    # LLM 模式 (Deepseek 驱动)
    # -----------------------------------------------------------------------

    def _llm_analyze(self, db: Session, entries: list[dict]) -> dict:
        prompt = self._build_analysis_prompt(entries)
        try:
            response = self._llm.generate_sync(prompt)
            return self._parse_llm_response(response)
        except Exception:
            return self._keyword_analyze(db, entries)

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
