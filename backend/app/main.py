"""AI Panel Studio — FastAPI 应用入口。

集成:
  - CORS 中间件
  - 全局异常处理 (ValueError → 400, RuntimeError → 502)
  - 健康检查端点
  - Discussions API 路由
"""

# 自动加载 .env 文件（必须在其他导入之前）
from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text

app = FastAPI(
    title="AI Panel Studio",
    version="1.0.0",
    description="AI 圆桌讨论 Web App API",
)


# =============================================================================
# CORS 中间件
# =============================================================================

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://localhost:5173",
        "http://127.0.0.1:3000",
        "http://127.0.0.1:5500",    # Live Server
        "null",                      # file:// 协议
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# =============================================================================
# 全局异常处理
# =============================================================================

@app.exception_handler(ValueError)
async def value_error_handler(request: Request, exc: ValueError) -> JSONResponse:
    """ValueError → HTTP 400 Bad Request。"""
    return JSONResponse(
        status_code=400,
        content={
            "error": {
                "code": "BAD_REQUEST",
                "message": str(exc),
            }
        },
    )


@app.exception_handler(RuntimeError)
async def runtime_error_handler(request: Request, exc: RuntimeError) -> JSONResponse:
    """RuntimeError → HTTP 502 (LLM 调用失败等)。"""
    return JSONResponse(
        status_code=502,
        content={
            "error": {
                "code": "UPSTREAM_ERROR",
                "message": str(exc),
            }
        },
    )


@app.exception_handler(Exception)
async def generic_error_handler(request: Request, exc: Exception) -> JSONResponse:
    """未知异常 → HTTP 500。"""
    return JSONResponse(
        status_code=500,
        content={
            "error": {
                "code": "INTERNAL_ERROR",
                "message": "服务器内部错误",
            }
        },
    )


# =============================================================================
# 健康检查
# =============================================================================

@app.get("/health")
def health_check():
    """健康检查端点。

    返回:
      - status: "ok" | "degraded"
      - database: "connected" | "error"
      - llm: "configured" | "not_configured"
    """
    import os
    from app.database import get_engine, init_db, create_session_factory

    db_status = "error"
    try:
        if os.getenv("PYTEST_RUNNING") == "1":
            db_url = "sqlite:///:memory:"
        else:
            db_url = os.getenv("DATABASE_URL", "sqlite:///data/dev.db")
        engine = get_engine(db_url)
        init_db(engine)
        session = create_session_factory(engine)()
        session.execute(text("SELECT 1"))
        db_status = "connected"
        session.close()
    except Exception:
        pass

    import os
    llm_status = "configured" if os.getenv("LLM_API_KEY") else "not_configured"

    return {
        "status": "ok" if db_status == "connected" else "degraded",
        "database": db_status,
        "llm": llm_status,
    }


# =============================================================================
# 路由注册
# =============================================================================

from app.api.discussions import router as discussions_router  # noqa: E402

app.include_router(discussions_router, prefix="/api/v1")
