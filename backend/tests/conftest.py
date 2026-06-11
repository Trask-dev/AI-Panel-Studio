"""pytest 共享 fixtures。

提供三个核心 fixture:
  - db_session    SQLite :memory: 独立事务，测试结束自动回滚
  - llm_mock      模拟 LLM 客户端的所有异步调用
  - async_client  httpx AsyncClient 用于测试 FastAPI 端点

生命周期:
  db_session   → function 级 (每个测试独立 session)
  llm_mock     → function 级 (每个测试独立 mock)
  async_client → session 级  (复用 HTTP client)

使用示例:
  def test_something(db_session, llm_mock):
      ...
"""

import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, MagicMock
from sqlalchemy.orm import Session

from app.database import get_test_engine, get_test_session, init_db


# =============================================================================
# Database Fixtures
# =============================================================================

@pytest.fixture(scope="function")
def db_engine():
    """创建独立的 :memory: SQLite 引擎并初始化 Schema。

    每个测试函数获得独立的 engine 实例，
    表结构在 setup 阶段创建，teardown 阶段销毁。

    注意: 如需真正的隔离（测试间共享 engine 但隔离事务），
    使用下面的 db_session fixture。
    """
    from sqlalchemy import create_engine, event

    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
    )

    @event.listens_for(engine, "connect")
    def _pragma(conn, _record):  # noqa: ARG001
        conn.execute("PRAGMA foreign_keys = ON")

    init_db(engine)
    yield engine
    engine.dispose()


@pytest.fixture(scope="function")
def db_session(db_engine) -> Session:
    """提供独立事务的 SQLAlchemy Session。

    使用方式:
      def test_xxx(db_session):
          db_session.execute(text("INSERT INTO ..."))
          db_session.commit()

    测试结束后自动 rollback 未提交的事务，
    确保下一个测试获得干净的数据库状态。

    如果不需要 engine 级隔离，可以直接使用:
      from app.database import get_test_session
    """
    from sqlalchemy.orm import sessionmaker

    SessionLocal = sessionmaker(bind=db_engine, autoflush=False)
    session = SessionLocal()

    yield session

    # Teardown: 回滚未提交事务，归还连接
    session.rollback()
    session.close()


# =============================================================================
# LLM Mock Fixture
# =============================================================================

@pytest.fixture(scope="function")
def llm_mock() -> MagicMock:
    """模拟 LLM 客户端。

    返回一个 MagicMock，其所有异步方法 (generate, chat, ...)
    默认返回 AsyncMock，可在测试中按需定制:

      llm_mock.generate.return_value = {"guests": [...]}
      llm_mock.generate.side_effect = TimeoutError("LLM timeout")
      llm_mock.generate.assert_called_once_with(...)

    Red Phase: 返回空 mock，GuestGenerator 尚未使用。
    Green Phase: 各测试预设 return_value / side_effect。
    """
    mock = MagicMock(name="LLMClient")
    # 将常用方法预设为 AsyncMock
    mock.generate = AsyncMock(name="llm.generate")
    mock.chat = AsyncMock(name="llm.chat")
    mock.analyze = AsyncMock(name="llm.analyze")
    return mock


# =============================================================================
# HTTP Client Fixture
# =============================================================================

@pytest_asyncio.fixture(scope="session")
async def async_client():
    """httpx AsyncClient，用于测试 FastAPI 端点。

    注意: 此 fixture 假设 FastAPI app 已在 app.main 中创建。
    Red Phase 阶段 app 可能尚未完整构建——测试导入失败时
    返回 None 作为占位。
    """
    try:
        from app.main import app
        from httpx import AsyncClient, ASGITransport

        transport = ASGITransport(app=app)
        async with AsyncClient(
            transport=transport,
            base_url="http://test/api/v1",
        ) as client:
            yield client
    except ImportError:
        # Red Phase: app.main 尚未创建
        yield None


# =============================================================================
# UUID Helper
# =============================================================================

@pytest.fixture(scope="session")
def new_uuid():
    """返回新的 UUID 字符串。"""
    import uuid
    return lambda: str(uuid.uuid4())
