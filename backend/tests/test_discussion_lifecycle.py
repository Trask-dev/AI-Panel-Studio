"""test_discussion_lifecycle.py — Discussion 状态机 API 端点测试

使用 db_session fixture 直接测试端点函数 (绕过 HTTP 层)。
覆盖 7 个测试场景:
  1. test_create_discussion
  2. test_get_discussion_detail_with_guests
  3. test_start_requires_host
  4. test_valid_state_transitions
  5. test_illegal_transition_rejected
  6. test_delete_cascades
  7. test_force_stop_skips_summary
"""

import uuid
import pytest
from sqlalchemy import text

from app.services.orchestrator import Orchestrator
from tests.factories import DiscussionFactory, GuestFactory, TranscriptFactory


# =============================================================================
# 端点函数封装 (直接调用, 不走 HTTP)
# =============================================================================

def api_create_discussion(db, topic, expert_count=3, max_rounds=None):
    """模拟 POST /discussions"""
    did = str(uuid.uuid4())
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    db.execute(text(
        "INSERT INTO discussions (id, topic, host_style, expert_count, "
        "status, max_rounds, llm_model, interjection_mode, llm_config, "
        "created_at, updated_at) "
        "VALUES (:id, :topic, 'socratic', :cnt, 'setup', :max_r, "
        "'claude-sonnet', 'moderated', '{}', :now, :now)"
    ), {"id": did, "topic": topic, "cnt": expert_count, "max_r": max_rounds, "now": now})
    db.commit()
    return {"id": did, "topic": topic, "status": "setup"}


def api_get_discussion(db, did):
    """模拟 GET /discussions/{id}"""
    disc = db.execute(text("SELECT * FROM discussions WHERE id=:did"), {"did": did}).fetchone()
    if disc is None:
        raise ValueError("NOT_FOUND")
    guests = db.execute(text(
        "SELECT * FROM guests WHERE discussion_id=:did AND is_active=1 ORDER BY speech_order"
    ), {"did": did}).fetchall()
    return {"discussion": dict(disc._mapping), "guests": [dict(g._mapping) for g in guests]}


def api_start_discussion(db, orch, did):
    """模拟 POST /discussions/{id}/start"""
    orch.start(did)
    db.commit()
    return {"discussion_id": did, "status": "active"}


def api_end_discussion(db, orch, did, force=False):
    """模拟 POST /discussions/{id}/end"""
    if force:
        orch.force_stop(did)
    else:
        orch.finish(did)
    db.commit()


def api_delete_discussion(db, did):
    """模拟 DELETE /discussions/{id}"""
    db.execute(text("DELETE FROM discussions WHERE id=:did"), {"did": did})
    db.commit()


# =============================================================================
# 测试
# =============================================================================

class TestDiscussionCRUD:
    """基础 CRUD 测试。"""

    def test_create_discussion(self, db_session):
        result = api_create_discussion(db_session, "测试话题", expert_count=3)
        assert result["status"] == "setup"
        assert result["topic"] == "测试话题"
        assert "id" in result

        count = db_session.execute(text(
            "SELECT COUNT(*) as c FROM discussions"
        )).fetchone().c
        assert count == 1

    def test_get_discussion_detail_with_guests(self, db_session):
        disc, guests = DiscussionFactory.create_full(
            db_session, topic="详情测试", expert_count=3, status="setup"
        )
        result = api_get_discussion(db_session, disc["id"])
        assert result["discussion"]["topic"] == "详情测试"
        assert len(result["guests"]) == 4  # 1 Host + 3 Expert
        assert result["guests"][0]["role"] == "host"

    def test_delete_cascades(self, db_session):
        disc, guests = DiscussionFactory.create_full(
            db_session, topic="待删除", expert_count=2, status="active"
        )
        TranscriptFactory.create_full_flow(db_session, disc["id"], guests, num_rounds=2)
        db_session.commit()

        api_delete_discussion(db_session, disc["id"])

        counts = db_session.execute(text(
            "SELECT (SELECT COUNT(*) FROM discussions WHERE id=:did) as d_cnt,"
            "       (SELECT COUNT(*) FROM guests WHERE discussion_id=:did) as g_cnt,"
            "       (SELECT COUNT(*) FROM transcript_entries WHERE discussion_id=:did) as t_cnt"
        ), {"did": disc["id"]}).fetchone()._mapping
        assert counts["d_cnt"] == 0
        assert counts["g_cnt"] == 0
        assert counts["t_cnt"] == 0


class TestGuestGeneration:
    """嘉宾生成端点测试 (新增)。"""

    def test_generate_guests_saves_to_db(self, db_session):
        """POST /guests/generate → 嘉宾写入 DB → /start 成功。"""
        # 1. 创建讨论
        result = api_create_discussion(db_session, "测试嘉宾生成", expert_count=3)

        # 2. 生成嘉宾 (直接调用服务模拟)
        from app.services.persona_generator import GuestGenerator
        from app.api.discussions import generate_guests

        gen = GuestGenerator()
        guests = gen.generate(
            topic=db_session.execute(
                text("SELECT topic FROM discussions WHERE id=:did"),
                {"did": result["id"]},
            ).fetchone().topic,
            expert_count=3,
        )

        # 3. 手动插入嘉宾 (模拟端点行为)
        import uuid
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        for idx, g in enumerate(guests):
            db_session.execute(
                text(
                    "INSERT INTO guests "
                    "(id, discussion_id, role, name, title, stance, stance_label, "
                    " color, status, speech_order, persona_prompt, is_active, created_at, updated_at) "
                    "VALUES (:id, :did, :role, :name, :title, :stance, :label, "
                    " :color, 'idle', :order, :prompt, 1, :now, :now)"
                ),
                {
                    "id": str(uuid.uuid4()), "did": result["id"],
                    "role": g.role, "name": g.name, "title": g.title or "",
                    "stance": g.stance or "", "label": g.stance_label or "",
                    "color": g.color or "#9090a0", "order": idx,
                    "prompt": g.persona_prompt or "", "now": now,
                },
            )
        db_session.commit()

        # 4. 验证嘉宾已入库
        count = db_session.execute(
            text(
                "SELECT COUNT(*) as c FROM guests "
                "WHERE discussion_id = :did AND is_active = 1"
            ),
            {"did": result["id"]},
        ).fetchone().c
        assert count == 4  # 1 Host + 3 Expert

        # 5. 现在 /start 应该成功 (不再 409)
        from app.services.orchestrator import Orchestrator
        orch = Orchestrator(db_session)
        orch.start(result["id"])
        db_session.commit()

        status = db_session.execute(
            text("SELECT status FROM discussions WHERE id=:did"),
            {"did": result["id"]},
        ).fetchone().status
        assert status == "active"

    def test_full_flow_create_generate_start(self, db_session):
        """端到端: 创建 → 生成嘉宾 → 开始讨论。"""
        # Create
        result = api_create_discussion(db_session, "端到端测试", expert_count=2)

        # Generate guests
        from app.services.persona_generator import GuestGenerator
        gen = GuestGenerator()
        guests = gen.generate(topic="端到端测试", expert_count=2)

        import uuid
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        for idx, g in enumerate(guests):
            db_session.execute(
                text(
                    "INSERT INTO guests "
                    "(id, discussion_id, role, name, title, stance, stance_label, "
                    " color, status, speech_order, persona_prompt, is_active, created_at, updated_at) "
                    "VALUES (:id, :did, :role, :name, :title, :stance, :label, "
                    " :color, 'idle', :order, :prompt, 1, :now, :now)"
                ),
                {
                    "id": str(uuid.uuid4()), "did": result["id"],
                    "role": g.role, "name": g.name, "title": g.title or "",
                    "stance": g.stance or "", "label": g.stance_label or "",
                    "color": g.color or "#9090a0", "order": idx,
                    "prompt": g.persona_prompt or "", "now": now,
                },
            )
        db_session.commit()

        # Start — now succeeds
        from app.services.orchestrator import Orchestrator
        orch = Orchestrator(db_session)
        orch.start(result["id"])
        db_session.commit()

        # Verify
        status = db_session.execute(
            text("SELECT status FROM discussions WHERE id=:did"),
            {"did": result["id"]},
        ).fetchone().status
        assert status == "active"

        # Verify opening statement
        entries = db_session.execute(
            text(
                "SELECT COUNT(*) as c FROM transcript_entries "
                "WHERE discussion_id = :did"
            ),
            {"did": result["id"]},
        ).fetchone().c
        assert entries == 1


class TestDiscussionLifecycle:
    """状态机流转测试。"""

    def test_start_requires_host(self, db_session):
        result = api_create_discussion(db_session, "无嘉宾", expert_count=3)
        orch = Orchestrator(db_session)

        with pytest.raises(ValueError, match="缺少主持人"):
            api_start_discussion(db_session, orch, result["id"])

    def test_valid_state_transitions(self, db_session):
        # 创建 + 生成嘉宾
        result = api_create_discussion(db_session, "状态机测试", expert_count=2)
        GuestFactory.create_lineup(db_session, result["id"], expert_count=2)
        db_session.commit()

        orch = Orchestrator(db_session)

        # setup → active
        resp = api_start_discussion(db_session, orch, result["id"])
        assert resp["status"] == "active"
        assert db_session.execute(text(
            "SELECT status FROM discussions WHERE id=:did"
        ), {"did": result["id"]}).fetchone().status == "active"

        # active → finished (正常结束)
        api_end_discussion(db_session, orch, result["id"])
        assert db_session.execute(text(
            "SELECT status FROM discussions WHERE id=:did"
        ), {"did": result["id"]}).fetchone().status == "finished"

    def test_illegal_transition_rejected(self, db_session):
        result = api_create_discussion(db_session, "非法转换", expert_count=2)
        GuestFactory.create_lineup(db_session, result["id"], expert_count=2)
        db_session.commit()

        orch = Orchestrator(db_session)
        api_start_discussion(db_session, orch, result["id"])
        api_end_discussion(db_session, orch, result["id"], force=True)

        # finished → start 应被拒绝
        orch2 = Orchestrator(db_session)
        with pytest.raises(ValueError, match="setup"):
            orch2.start(result["id"])

    def test_force_stop_skips_summary(self, db_session):
        result = api_create_discussion(db_session, "强制终止", expert_count=2)
        GuestFactory.create_lineup(db_session, result["id"], expert_count=2)
        db_session.commit()

        orch = Orchestrator(db_session)
        api_start_discussion(db_session, orch, result["id"])
        api_end_discussion(db_session, orch, result["id"], force=True)

        count = db_session.execute(text(
            "SELECT COUNT(*) as c FROM transcript_entries "
            "WHERE discussion_id=:did AND entry_type='host_summary'"
        ), {"did": result["id"]}).fetchone().c
        assert count == 0

    def test_list_filters_by_status(self, db_session):
        """按状态过滤讨论列表。"""
        # 创建两场不同状态的讨论
        r1 = api_create_discussion(db_session, "讨论A", expert_count=2)
        r2 = api_create_discussion(db_session, "讨论B", expert_count=3)

        GuestFactory.create_lineup(db_session, r1["id"], expert_count=2)
        db_session.commit()
        api_start_discussion(db_session, Orchestrator(db_session), r1["id"])

        # 查 setup
        rows = db_session.execute(text(
            "SELECT * FROM discussions WHERE status='setup' ORDER BY created_at"
        )).fetchall()
        assert len(rows) >= 1  # 至少 B 是 setup
