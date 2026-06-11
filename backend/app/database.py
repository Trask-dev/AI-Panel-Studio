"""数据库连接管理。

测试环境使用 SQLite :memory:，生产环境使用 data/dev.db。
每个测试用例获得独立的 session，事务回滚保证隔离。
"""

import os
from pathlib import Path

from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker, Session

# 项目根目录 (backend/app/database.py → backend/ → 项目根)
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
SCHEMA_PATH = PROJECT_ROOT / "docs" / "database_schema.sql"


def get_engine(db_url: str | None = None):
    """创建 SQLAlchemy 引擎。

    Args:
        db_url: SQLite 连接字符串。
                默认使用 :memory: (测试)，
                生产环境传入 "sqlite:///data/dev.db"。
    """
    if db_url is None:
        db_url = "sqlite:///:memory:"

    engine = create_engine(
        db_url,
        echo=False,                        # 测试时不输出 SQL 日志
        connect_args={"check_same_thread": False},  # SQLite 多线程
    )

    # 启用外键约束 (SQLite 默认关闭)
    @event.listens_for(engine, "connect")
    def _set_sqlite_pragma(dbapi_connection, connection_record):  # noqa: ARG001
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys = ON")
        cursor.execute("PRAGMA journal_mode = WAL")
        cursor.close()

    return engine


def init_db(engine) -> None:
    """从 docs/database_schema.sql 初始化数据库表结构。

    仅执行 CREATE TABLE / CREATE INDEX 语句，
    跳过 PRAGMA 设置 (已在 engine connect 事件中处理)。
    """
    if not SCHEMA_PATH.exists():
        raise FileNotFoundError(
            f"Schema 文件不存在: {SCHEMA_PATH}\n"
            f"请确认 docs/database_schema.sql 存在。"
        )

    schema_sql = SCHEMA_PATH.read_text(encoding="utf-8")

    # 移除 PRAGMA 行 (已在 engine connect 事件中设置)
    lines = schema_sql.split("\n")
    ddl_lines = [
        line for line in lines
        if not line.strip().upper().startswith("PRAGMA")
    ]
    ddl_sql = "\n".join(ddl_lines)

    # 拆分多语句: SQLite 单次 execute 只能执行一条语句
    # 使用原始 DBAPI 连接的 executescript() 支持多语句
    raw_conn = engine.raw_connection()
    try:
        raw_conn.executescript(ddl_sql)
        raw_conn.commit()
    finally:
        raw_conn.close()


def create_session_factory(engine) -> sessionmaker[Session]:
    """创建 session factory。"""
    return sessionmaker(bind=engine, autoflush=False, autocommit=False)


# ---- 模块级默认实例 (测试用) ----
_engine = None
_SessionLocal = None


def get_test_engine():
    """获取测试用 engine (单例)。"""
    global _engine
    if _engine is None:
        _engine = get_engine("sqlite:///:memory:")
        init_db(_engine)
    return _engine


def get_test_session() -> Session:
    """获取测试用 session。

    每个测试用例调用此函数获得独立 session，
    测试结束后调用 session.rollback() 恢复干净状态。
    """
    global _SessionLocal
    if _SessionLocal is None:
        _SessionLocal = create_session_factory(get_test_engine())
    return _SessionLocal()
