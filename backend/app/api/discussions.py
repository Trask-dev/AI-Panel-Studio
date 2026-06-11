"""Discussions API — 讨论会话 REST 端点。

注入依赖:
  - get_db: SQLAlchemy Session
  - get_orchestrator: Orchestrator
  - get_guest_generator: GuestGenerator
"""

import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.database import get_test_session
from app.services.orchestrator import Orchestrator
from app.services.persona_generator import GuestGenerator

router = APIRouter(tags=["Discussions"])


# =============================================================================
# Pydantic Schemas (内联 — 与 openapi.yaml 对齐)
# =============================================================================

class DiscussionCreate(BaseModel):
    topic: str = Field(..., min_length=1, max_length=200)
    expert_count: int = Field(default=3, ge=2, le=8)
    host_style: str = Field(default="socratic")
    max_rounds: Optional[int] = Field(default=None, ge=1, le=50)
    llm_model: str = Field(default="claude-sonnet-4-20250514")
    interjection_mode: str = Field(default="moderated")


class DiscussionResponse(BaseModel):
    id: str
    topic: str
    status: str
    expert_count: int
    round_count: int
    created_at: str


class ErrorResponse(BaseModel):
    code: str
    message: str


# =============================================================================
# 依赖注入 (测试环境)
# =============================================================================

def get_db():
    """获取数据库 session (generator, FastAPI 自动管理生命周期)。

    生产环境应从连接池获取；测试环境复用 :memory: session。
    """
    session = get_test_session()
    try:
        yield session
    finally:
        session.close()


def get_orchestrator(db: Session = Depends(get_db)) -> Orchestrator:
    return Orchestrator(db)


def get_guest_generator() -> GuestGenerator:
    return GuestGenerator()


# =============================================================================
# CRUD Endpoints
# =============================================================================

@router.post("/discussions", status_code=201)
def create_discussion(
    body: DiscussionCreate,
    db: Session = Depends(get_db),
):
    """创建新讨论。"""
    did = str(uuid.uuid4())
    now = _now()
    db.execute(
        text(
            "INSERT INTO discussions (id, topic, host_style, expert_count, "
            "status, max_rounds, llm_model, interjection_mode, llm_config, "
            "created_at, updated_at) "
            "VALUES (:id, :topic, :host, :cnt, 'setup', :max_r, :model, "
            ":mode, '{}', :now, :now)"
        ),
        {
            "id": did, "topic": body.topic, "host": body.host_style,
            "cnt": body.expert_count, "max_r": body.max_rounds,
            "model": body.llm_model, "mode": body.interjection_mode,
            "now": now,
        },
    )
    db.commit()
    return {"id": did, "topic": body.topic, "status": "setup"}


@router.get("/discussions")
def list_discussions(
    status: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    """获取讨论列表。"""
    query = "SELECT id, topic, status, expert_count, round_count, created_at FROM discussions"
    params = {}
    if status:
        query += " WHERE status = :st"
        params["st"] = status
    query += " ORDER BY created_at DESC"
    rows = db.execute(text(query), params).fetchall()
    return [dict(r._mapping) for r in rows]


@router.get("/discussions/{discussion_id}")
def get_discussion(
    discussion_id: str,
    db: Session = Depends(get_db),
):
    """获取讨论详情 + 嘉宾列表。"""
    disc = db.execute(
        text("SELECT * FROM discussions WHERE id = :did"), {"did": discussion_id}
    ).fetchone()
    if disc is None:
        raise HTTPException(404, {"code": "NOT_FOUND", "message": "讨论不存在"})

    guests = db.execute(
        text("SELECT * FROM guests WHERE discussion_id = :did AND is_active = 1 ORDER BY speech_order"),
        {"did": discussion_id},
    ).fetchall()

    return {
        "discussion": dict(disc._mapping),
        "guests": [dict(g._mapping) for g in guests],
    }


@router.post("/discussions/{discussion_id}/start")
def start_discussion(
    discussion_id: str,
    db: Session = Depends(get_db),
    orch: Orchestrator = Depends(get_orchestrator),
):
    """开始讨论 (setup → active)。"""
    try:
        orch.start(discussion_id)
    except ValueError as exc:
        raise HTTPException(409, {"code": "CONFLICT", "message": str(exc)})
    db.commit()
    return {"discussion_id": discussion_id, "status": "active"}


@router.post("/discussions/{discussion_id}/end")
def end_discussion(
    discussion_id: str,
    force: bool = Query(False),
    db: Session = Depends(get_db),
    orch: Orchestrator = Depends(get_orchestrator),
):
    """结束讨论 (→ summarizing → finished)。"""
    try:
        if force:
            orch.force_stop(discussion_id)
        else:
            orch.finish(discussion_id)
    except ValueError as exc:
        raise HTTPException(409, {"code": "CONFLICT", "message": str(exc)})
    db.commit()
    return {"discussion_id": discussion_id, "status": "finished" if force else "summarizing"}


@router.delete("/discussions/{discussion_id}", status_code=204)
def delete_discussion(
    discussion_id: str,
    db: Session = Depends(get_db),
):
    """删除讨论 (级联删除)。"""
    db.execute(
        text("DELETE FROM discussions WHERE id = :did"), {"did": discussion_id}
    )
    db.commit()


# =============================================================================
# 辅助
# =============================================================================

def _now() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
