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

    测试环境 (PYTEST_RUNNING=1) 用 :memory:，生产环境用 data/dev.db。
    """
    import os
    from pathlib import Path
    from app.database import get_engine, init_db, create_session_factory

    if os.getenv("PYTEST_RUNNING") == "1":
        db_url = "sqlite:///:memory:"
    else:
        db_url = os.getenv("DATABASE_URL", "sqlite:///data/dev.db")
        # 确保 data 目录存在
        if db_url.startswith("sqlite:///") and not db_url.startswith("sqlite:///:memory:"):
            db_path = Path(db_url.replace("sqlite:///", ""))
            if not db_path.is_absolute():
                db_path = Path.cwd() / db_path
            db_path.parent.mkdir(parents=True, exist_ok=True)

    engine = get_engine(db_url)
    init_db(engine)
    factory = create_session_factory(engine)
    session = factory()
    try:
        yield session
    finally:
        session.close()


def get_orchestrator(db: Session = Depends(get_db)) -> Orchestrator:
    """创建 Orchestrator，注入 LLM 驱动的发言生成器。"""
    from app.services.speech_generator import SpeechGenerator
    from app.utils.sse_manager import get_sse_manager

    sse = get_sse_manager()
    llm = _make_llm_client()
    if not llm:
        return Orchestrator(db, sse_manager=sse, llm_client=None)

    gen = SpeechGenerator(llm)

    def llm_speech(guest_name: str, entry_type: str) -> str:
        return gen.generate_by_name(db, guest_name, entry_type)

    return Orchestrator(db, speech_fn=llm_speech, sse_manager=sse, llm_client=llm)


def _make_llm_client():
    """从环境变量创建 LLMClient 实例。无 API Key 则返回 None。"""
    import os
    from app.services.llm_client import LLMClient

    api_key = os.getenv("LLM_API_KEY", "")
    if not api_key:
        return None
    return LLMClient(
        api_key=api_key,
        model=os.getenv("LLM_MODEL", "deepseek-chat"),
        base_url=os.getenv("LLM_BASE_URL", "https://api.deepseek.com/v1"),
        timeout=int(os.getenv("LLM_TIMEOUT", "60")),          # 发言生成可能较慢
        max_retries=int(os.getenv("LLM_MAX_RETRIES", "2")),   # 限流/超时后多重试1次
    )


def get_guest_generator() -> GuestGenerator:
    return GuestGenerator(llm_client=_make_llm_client())


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


@router.post("/discussions/{discussion_id}/guests/generate")
def generate_guests(
    discussion_id: str,
    db: Session = Depends(get_db),
):
    """LLM 生成嘉宾阵容并持久化到数据库。

    流程:
      1. 从 DB 读取讨论的 topic + expert_count
      2. 调用 GuestGenerator (Mock LLM) 生成 1 Host + N Expert
      3. 将嘉宾写入 guests 表
      4. 返回完整的嘉宾列表

    调用时机: 创建讨论后、开始讨论前。必需步骤，否则 /start 会 409。
    """
    # 1. 读取讨论信息
    disc = db.execute(
        text("SELECT * FROM discussions WHERE id = :did"), {"did": discussion_id}
    ).fetchone()
    if disc is None:
        raise HTTPException(404, {"code": "NOT_FOUND", "message": "讨论不存在"})

    # 2. 检查是否已有活跃嘉宾 (防止重复生成)
    existing = db.execute(
        text(
            "SELECT COUNT(*) as c FROM guests "
            "WHERE discussion_id = :did AND is_active = 1"
        ),
        {"did": discussion_id},
    ).fetchone().c
    if existing > 0:
        # 已有嘉宾，直接返回
        guests = db.execute(
            text(
                "SELECT * FROM guests "
                "WHERE discussion_id = :did AND is_active = 1 "
                "ORDER BY speech_order"
            ),
            {"did": discussion_id},
        ).fetchall()
        return {
            "discussion_id": discussion_id,
            "guests": [dict(g._mapping) for g in guests],
            "generated": False,
        }

    # 3. 调用 GuestGenerator
    gen = get_guest_generator()  # 从环境变量读取 LLM 配置
    try:
        guest_list = gen.generate(
            topic=disc.topic,
            expert_count=disc.expert_count,
        )
    except ValueError as exc:
        raise HTTPException(400, {"code": "BAD_REQUEST", "message": str(exc)})

    # 4. 持久化到数据库
    import uuid
    from datetime import datetime, timezone

    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    for idx, guest in enumerate(guest_list):
        gid = str(uuid.uuid4())
        db.execute(
            text(
                "INSERT INTO guests "
                "(id, discussion_id, role, name, title, bio, stance, stance_label, "
                " color, avatar_url, status, speech_order, persona_prompt, is_active, "
                " created_at, updated_at) "
                "VALUES "
                "(:id, :did, :role, :name, :title, :bio, :stance, :stance_label, "
                " :color, NULL, 'idle', :order, :prompt, 1, :now, :now)"
            ),
            {
                "id": gid,
                "did": discussion_id,
                "role": guest.role,
                "name": guest.name,
                "title": guest.title,
                "bio": guest.bio,
                "stance": guest.stance or "",
                "stance_label": guest.stance_label or "",
                "color": guest.color or "#9090a0",
                "order": idx,
                "prompt": guest.persona_prompt or "",
                "now": now,
            },
        )
    db.commit()

    # 5. 返回结果
    saved = db.execute(
        text(
            "SELECT * FROM guests "
            "WHERE discussion_id = :did AND is_active = 1 "
            "ORDER BY speech_order"
        ),
        {"did": discussion_id},
    ).fetchall()

    return {
        "discussion_id": discussion_id,
        "guests": [dict(g._mapping) for g in saved],
        "generated": True,
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


@router.post("/discussions/{discussion_id}/rounds/next")
def advance_round(
    discussion_id: str,
    db: Session = Depends(get_db),
    orch: Orchestrator = Depends(get_orchestrator),
):
    """推进一轮讨论 (主持人提问 → 各专家依次发言 → 轮次+1)。

    每调用一次，所有专家依次发言一轮。达到 max_rounds 时自动变为 summarizing。
    调用时机: /start 之后, /end 之前。
    """
    try:
        result = orch.run_round(discussion_id)
    except ValueError as exc:
        raise HTTPException(409, {"code": "CONFLICT", "message": str(exc)})
    db.commit()

    disc = db.execute(
        text("SELECT round_count, status FROM discussions WHERE id = :did"),
        {"did": discussion_id},
    ).fetchone()

    return {
        "discussion_id": discussion_id,
        "round_count": disc.round_count,
        "status": disc.status,
        "consensus": result.get("consensus", []),
        "divergences": result.get("divergences", []),
    }


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


@router.post("/discussions/{discussion_id}/summarize")
def summarize_discussion(
    discussion_id: str,
    db: Session = Depends(get_db),
):
    """生成讨论总结 (LLM 驱动, 持久化到 discussion_summaries)。"""
    from app.services.summary_generator import SummaryGenerator

    llm = _make_llm_client()  # API Key 存在则用真实 LLM，否则 fallback

    generator = SummaryGenerator(llm_client=llm)
    try:
        result = generator.generate(db, discussion_id)
    except ValueError as exc:
        raise HTTPException(400, {"code": "BAD_REQUEST", "message": str(exc)})
    except RuntimeError as exc:
        raise HTTPException(502, {"code": "UPSTREAM_ERROR", "message": str(exc)})

    return result


# =============================================================================
# 查询端点 (前端数据源)
# =============================================================================

@router.get("/discussions/{discussion_id}/messages")
def list_messages(
    discussion_id: str,
    cursor: int = Query(0),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
):
    """获取发言记录（游标分页）。

    首次请求 cursor=0，后续传上次返回的 next_cursor。
    """
    rows = db.execute(
        text(
            "SELECT te.*, g.name as guest_name, g.title as guest_title, "
            "g.color as guest_color, g.role as guest_role "
            "FROM transcript_entries te "
            "JOIN guests g ON te.guest_id = g.id "
            "WHERE te.discussion_id = :did AND te.sequence_number > :cur "
            "ORDER BY te.sequence_number ASC "
            "LIMIT :lim"
        ),
        {"did": discussion_id, "cur": cursor, "lim": limit},
    ).fetchall()

    items = [dict(r._mapping) for r in rows]
    next_cursor = items[-1]["sequence_number"] if items else cursor
    total = db.execute(
        text(
            "SELECT COUNT(*) as c FROM transcript_entries "
            "WHERE discussion_id = :did"
        ),
        {"did": discussion_id},
    ).fetchone().c

    return {
        "items": items,
        "has_more": len(items) == limit,
        "next_cursor": next_cursor,
        "total": total,
    }


@router.get("/discussions/{discussion_id}/consensus")
def list_consensus(
    discussion_id: str,
    include_inactive: bool = Query(False),
    db: Session = Depends(get_db),
):
    """获取共识列表。"""
    clause = "" if include_inactive else " AND is_active = 1"
    rows = db.execute(
        text(
            "SELECT * FROM consensus_items "
            "WHERE discussion_id = :did" + clause + " ORDER BY first_identified_at"
        ),
        {"did": discussion_id},
    ).fetchall()
    return {"items": [dict(r._mapping) for r in rows]}


@router.get("/discussions/{discussion_id}/divergences")
def list_divergences(
    discussion_id: str,
    include_resolved: bool = Query(False),
    db: Session = Depends(get_db),
):
    """获取分歧列表。"""
    clause = "" if include_resolved else " AND is_active = 1 AND resolved = 0"
    rows = db.execute(
        text(
            "SELECT * FROM divergence_items "
            "WHERE discussion_id = :did" + clause + " ORDER BY first_identified_at"
        ),
        {"did": discussion_id},
    ).fetchall()
    return {"items": [dict(r._mapping) for r in rows]}


@router.get("/discussions/{discussion_id}/summary")
def get_summary(
    discussion_id: str,
    db: Session = Depends(get_db),
):
    """获取讨论总结。"""
    row = db.execute(
        text("SELECT * FROM discussion_summaries WHERE discussion_id = :did"),
        {"did": discussion_id},
    ).fetchone()
    if row is None:
        raise HTTPException(404, {"code": "NOT_FOUND", "message": "总结尚未生成"})
    return dict(row._mapping)


# =============================================================================
# SSE 实时事件流
# =============================================================================

@router.get("/discussions/{discussion_id}/events")
async def stream_events(
    discussion_id: str,
    after_sequence: int = Query(0),
):
    """SSE 实时事件流端点。

    连接后持续推送 transcript_delta / guest_status_change 等事件。
    前端通过 EventSource 连接此端点。
    """
    from fastapi.responses import StreamingResponse
    from app.utils.sse_manager import get_sse_manager

    manager = get_sse_manager()
    q = manager.subscribe(discussion_id)

    async def event_generator():
        import asyncio
        import queue
        try:
            while True:
                try:
                    data = await asyncio.to_thread(q.get, timeout=1.0)
                    yield f"data: {data}\n\n"
                except queue.Empty:
                    yield ":heartbeat\n\n"
        finally:
            manager.unsubscribe(discussion_id, q)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


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
