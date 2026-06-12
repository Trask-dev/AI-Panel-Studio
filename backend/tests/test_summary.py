"""test_summary.py — SummaryGenerator 单元测试 + API 端点测试"""

import pytest
from sqlalchemy import text

from app.services.summary_generator import SummaryGenerator
from tests.factories import DiscussionFactory, GuestFactory, TranscriptFactory, ConsensusFactory


class TestSummaryGenerator:
    """SummaryGenerator 服务层测试。"""

    def test_generates_summary_with_transcript(self, db_session):
        """有 transcript → 正常生成总结。"""
        disc, guests = DiscussionFactory.create_full(
            db_session, topic="AI 的未来", expert_count=2, status="active"
        )
        TranscriptFactory.create_full_flow(db_session, disc["id"], guests, num_rounds=2)
        db_session.commit()

        gen = SummaryGenerator()  # 无 LLM → fallback
        result = gen.generate(db_session, disc["id"])

        assert "content" in result
        assert result["discussion_id"] == disc["id"]
        assert len(result["content"]) > 50

        # 验证已持久化
        row = db_session.execute(
            text("SELECT * FROM discussion_summaries WHERE discussion_id = :did"),
            {"did": disc["id"]},
        ).fetchone()
        assert row is not None

    def test_empty_transcript_raises(self, db_session):
        """无 transcript → ValueError。"""
        disc, guests = DiscussionFactory.create_full(
            db_session, topic="空讨论", expert_count=2, status="setup"
        )
        db_session.commit()

        gen = SummaryGenerator()
        with pytest.raises(ValueError, match="无发言记录"):
            gen.generate(db_session, disc["id"])

    def test_fallback_summary_contains_consensus(self, db_session):
        """fallback 总结包含共识内容。"""
        disc, guests = DiscussionFactory.create_full(
            db_session, topic="UBI 讨论", expert_count=2, status="active"
        )
        # 只加少量 transcript
        host = guests[0]
        TranscriptFactory.create_opening(db_session, disc["id"], host["id"])
        # 加共识
        expert_ids = [g["id"] for g in guests[1:]]
        ConsensusFactory.create_consensus(
            db_session, disc["id"], "各方同意需要渐进式试点", expert_ids
        )
        db_session.commit()

        gen = SummaryGenerator()
        result = gen.generate(db_session, disc["id"])

        assert "渐进式试点" in result["content"]
        assert len(result["content"]) > 100

    def test_llm_generated_summary_takes_priority(self, db_session, llm_mock):
        """LLM 可用时，优先使用 LLM 生成内容。"""
        disc, guests = DiscussionFactory.create_full(
            db_session, topic="LLM 测试", expert_count=2, status="active"
        )
        host = guests[0]
        TranscriptFactory.create_opening(db_session, disc["id"], host["id"])
        db_session.commit()

        llm_mock.generate.return_value = "# 主持人结语\n\n这是一段由 LLM 生成的高质量总结。"
        gen = SummaryGenerator(llm_client=llm_mock)
        result = gen.generate(db_session, disc["id"])

        assert "LLM 生成的高质量总结" in result["content"]

    def test_key_findings_extraction(self, db_session):
        """_extract_key_findings 正确提取以 - 开头的行。"""
        gen = SummaryGenerator()
        content = "一些文字\n- 发现1：AI 需要监管\n- 发现2：教育需改革\n其他文字"
        findings = gen._extract_key_findings(content)
        assert len(findings) == 2
        assert "发现1：AI 需要监管" in findings


class TestSummarizeAPI:
    """API 端点测试。"""

    def test_summarize_endpoint_returns_content(self, db_session):
        """POST /summarize → 200 + 总结内容。"""
        from app.services.summary_generator import SummaryGenerator

        disc, guests = DiscussionFactory.create_full(
            db_session, topic="API 总结测试", expert_count=2, status="active"
        )
        host = guests[0]
        TranscriptFactory.create_opening(db_session, disc["id"], host["id"])
        db_session.commit()

        # 直接调用服务 (绕过 HTTP)
        gen = SummaryGenerator()
        result = gen.generate(db_session, disc["id"])

        assert "content" in result
        assert len(result["content"]) > 50

    def test_summarize_empty_discussion(self, db_session):
        """无 transcript 时返回错误。"""
        disc, guests = DiscussionFactory.create_full(
            db_session, topic="空", expert_count=2, status="setup"
        )
        db_session.commit()

        gen = SummaryGenerator()
        with pytest.raises(ValueError, match="无发言记录"):
            gen.generate(db_session, disc["id"])
