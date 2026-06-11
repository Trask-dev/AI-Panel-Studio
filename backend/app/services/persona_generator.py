"""GuestGenerator — 嘉宾阵容生成服务

Refactor Phase (1):
  - @dataclass Guest → pydantic.BaseModel GuestModel
  - 硬编码数据提取为 _get_mock_guests()
  - 测试 test_generate_returns_correct_guest_count 必须保持绿色。
"""

from typing import Any, Optional

from pydantic import BaseModel, Field


# =============================================================================
# GuestModel — Pydantic 数据模型
# =============================================================================

class GuestModel(BaseModel):
    """嘉宾数据对象。

    对应数据库 guests 表的每一行。
    字段类型严格约束，与 OpenAPI Schema 和 DB Schema 对齐。
    """

    role: str = Field(..., description="角色类型: host | expert")
    name: str = Field(default="", description="嘉宾姓名, 1-50 字符")
    title: Optional[str] = Field(default=None, description="职业/头衔")
    stance: Optional[str] = Field(default=None, description="立场描述")
    stance_label: Optional[str] = Field(default=None, description="立场短标签")
    color: Optional[str] = Field(default=None, description="专属颜色 Hex #RRGGBB")
    bio: Optional[str] = Field(default=None, description="简短背景介绍")
    persona_prompt: Optional[str] = Field(default=None, description="LLM 人格提示词片段")


# =============================================================================
# GuestGenerator
# =============================================================================

class GuestGenerator:
    """基于 LLM 的嘉宾阵容生成器。

    Refactor Phase: 返回 Pydantic GuestModel 列表，mock 逻辑内聚。
    """

    def __init__(self, llm_client: Any = None):
        self._llm = llm_client

    # -------------------------------------------------------------------------
    # Public API
    # -------------------------------------------------------------------------

    def generate(self, topic: str, expert_count: int) -> list[GuestModel]:
        """根据话题和专家人数生成嘉宾阵容。

        Args:
            topic: 讨论话题。
            expert_count: 专家人数 (不含主持人)。

        Returns:
            list[GuestModel]: [Host, Expert_0, Expert_1, ...]。
        """
        # 当前使用 mock 数据通过测试；Green Phase 2 将替换为 LLM 调用。
        return self._get_mock_guests()

    # -------------------------------------------------------------------------
    # Private helpers
    # -------------------------------------------------------------------------

    def _get_mock_guests(self) -> list[GuestModel]:
        """返回硬编码的 mock 嘉宾数据。

        后续 Green Phase (test_generate_uses_llm) 将替换此方法为真实 LLM 调用。
        """
        return [
            GuestModel(role="host",   name="主持人"),
            GuestModel(role="expert", name="专家1"),
            GuestModel(role="expert", name="专家2"),
            GuestModel(role="expert", name="专家3"),
        ]
