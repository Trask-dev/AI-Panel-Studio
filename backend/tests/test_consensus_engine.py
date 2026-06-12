"""test_consensus_engine.py — 共识/分歧分析引擎 TDD"""

import pytest
from sqlalchemy import text
from tests.factories import DiscussionFactory, TranscriptFactory


def _insert_speech(db, disc_id, guest, seq, rnd, etype, content):
    entry = TranscriptFactory.build_entry(disc_id, guest["id"], seq, rnd, etype, content)
    TranscriptFactory.insert_one(db, **entry)


class TestConsensusAnalyzer:
    """共识分析器。"""

    def test_extract_consensus_from_agreeing_speeches(self, db_session):
        from app.services.consensus_analyzer import ConsensusAnalyzer

        disc, guests = DiscussionFactory.create_full(
            db_session, topic="AI 监管", expert_count=3, status="active"
        )
        host, *experts = guests

        for i, e in enumerate(experts):
            _insert_speech(db_session, disc["id"], e, i + 1, 1,
                           "position_statement",
                           "我们都一致认为 AI 监管需要分级制度，这是各方共识。")

        analyzer = ConsensusAnalyzer()
        result = analyzer.analyze(db_session, disc["id"])

        assert result is not None
        assert len(result["consensus"]) >= 1, f"应有至少1条共识, 实际{result['consensus']}"

    def test_no_false_consensus_on_divergent_speeches(self, db_session):
        from app.services.consensus_analyzer import ConsensusAnalyzer

        disc, guests = DiscussionFactory.create_full(
            db_session, topic="UBI", expert_count=2, status="active"
        )
        host, e1, e2 = guests

        _insert_speech(db_session, disc["id"], e1, 1, 1, "position_statement",
                       "我坚决反对全民基本收入，这对财政是不可持续的。")
        _insert_speech(db_session, disc["id"], e2, 2, 1, "position_statement",
                       "我完全支持全民基本收入，这是社会进步的必然。")

        analyzer = ConsensusAnalyzer()
        result = analyzer.analyze(db_session, disc["id"])

        assert result is not None
        assert result.get("consensus", []) == []

    def test_extract_divergence_from_opposing_views(self, db_session):
        from app.services.consensus_analyzer import ConsensusAnalyzer

        disc, guests = DiscussionFactory.create_full(
            db_session, topic="技术路线", expert_count=2, status="active"
        )
        host, e1, e2 = guests

        _insert_speech(db_session, disc["id"], e1, 1, 1, "position_statement",
                       "我反对发展专用 AI 芯片，这根本不是一个好方向。")
        _insert_speech(db_session, disc["id"], e2, 2, 1, "position_statement",
                       "我也反对你的观点，完全错误，通用架构才是未来。")
        _insert_speech(db_session, disc["id"], e1, 3, 1, "speech",
                       "恰恰相反，专用芯片才是突破瓶颈的关键。")

        analyzer = ConsensusAnalyzer()
        result = analyzer.analyze(db_session, disc["id"])

        assert "divergences" in result
        assert len(result["divergences"]) >= 1

    def test_analyze_persists_to_db(self, db_session):
        from app.services.consensus_analyzer import ConsensusAnalyzer

        disc, guests = DiscussionFactory.create_full(
            db_session, topic="持久化测试", expert_count=2, status="active"
        )
        host, e1, e2 = guests

        _insert_speech(db_session, disc["id"], e1, 1, 1, "position_statement",
                       "我赞同统一 AI 安全标准，各方均认同这是必要的。")
        _insert_speech(db_session, disc["id"], e2, 2, 1, "position_statement",
                       "我也认为 AI 安全标准应该统一，确实如此，这是共识。")

        analyzer = ConsensusAnalyzer()
        analyzer.analyze_and_persist(db_session, disc["id"])
        db_session.commit()

        c_count = db_session.execute(
            text("SELECT COUNT(*) as c FROM consensus_items WHERE discussion_id = :did"),
            {"did": disc["id"]},
        ).fetchone().c
        d_count = db_session.execute(
            text("SELECT COUNT(*) as c FROM divergence_items WHERE discussion_id = :did"),
            {"did": disc["id"]},
        ).fetchone().c

        assert c_count + d_count >= 1, "共识或分歧至少有一项被写入数据库"
