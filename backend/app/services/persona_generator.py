"""GuestGenerator — 嘉宾阵容生成服务

完整实现:
  - Pydantic GuestModel 严格类型约束
  - 参数校验 (topic 非空, 2 <= expert_count <= 8)
  - LLM 调用抽象 (通过 llm_client 注入)
  - Host 颜色强制金色, 专家颜色唯一分配
  - LLM 失败优雅降级
"""

import json
from typing import Any

from pydantic import BaseModel, Field, field_validator


# =============================================================================
# 专家颜色池 (与 frontend/css/tokens.css 一致)
# =============================================================================

EXPERT_COLORS = [
    "#4a90d9",  # 蓝
    "#d94a4a",  # 红
    "#50b86c",  # 绿
    "#7b61ff",  # 紫
    "#ff8c42",  # 橙
    "#20b2aa",  # 青
    "#ff6b6b",  # 珊瑚
    "#b8860b",  # 暗金
]

HOST_COLOR = "#E8A840"  # 主持人专属金色


# =============================================================================
# GuestModel — Pydantic 数据模型
# =============================================================================

class GuestModel(BaseModel):
    """嘉宾数据对象。对应数据库 guests 表。"""

    role: str = Field(..., description="角色类型: host | expert")
    name: str = Field(default="", min_length=1, max_length=50, description="嘉宾姓名")
    title: str | None = Field(default=None, description="职业/头衔")
    stance: str | None = Field(default=None, description="立场描述")
    stance_label: str | None = Field(default=None, description="立场短标签")
    color: str | None = Field(default=None, description="专属颜色 Hex")
    bio: str | None = Field(default=None, description="简短背景介绍")
    persona_prompt: str | None = Field(default=None, description="LLM 人格提示词片段")

    @field_validator("role")
    @classmethod
    def role_must_be_valid(cls, v: str) -> str:
        if v not in ("host", "expert"):
            raise ValueError(f"role 必须是 'host' 或 'expert', 实际: '{v}'")
        return v


# =============================================================================
# GuestGenerator
# =============================================================================

class GuestGenerator:
    """基于 LLM 的嘉宾阵容生成器。"""

    # LLM 提示词模板
    PROMPT_TEMPLATE = """你是一位专业的节目策划人。请为一场关于"{topic}"的圆桌讨论生成嘉宾阵容。

要求:
1. 生成 1 位主持人和 {expert_count} 位专家
2. 每位嘉宾包含: name(姓名), title(职业/头衔), bio(简短背景), stance(立场描述), stance_label(立场短标签)
3. 专家立场应多样化, 覆盖不同视角
4. 主持人保持中立客观

请以 JSON 格式返回:
{{"guests": [{{"role": "host", "name": "...", "title": "...", "bio": "...", "stance": "...", "stance_label": "主持人"}}, ...]}}
"""

    def __init__(self, llm_client: Any = None):
        self._llm = llm_client

    # -------------------------------------------------------------------------
    # Public API
    # -------------------------------------------------------------------------

    def generate(self, topic: str, expert_count: int) -> list[GuestModel]:
        """根据话题和专家人数生成嘉宾阵容。

        Args:
            topic: 讨论话题 (非空)。
            expert_count: 专家人数 (2-8)。

        Returns:
            list[GuestModel]: [Host, Expert_0, ..., Expert_{N-1}]。

        Raises:
            ValueError: topic 为空或 expert_count 越界。
            RuntimeError: LLM 调用失败。
        """
        self._validate_input(topic, expert_count)
        raw_data = self._call_llm(topic, expert_count)
        guests = self._parse_and_enrich(raw_data, expert_count)
        return guests

    # -------------------------------------------------------------------------
    # Private: 校验
    # -------------------------------------------------------------------------

    def _validate_input(self, topic: str, expert_count: int) -> None:
        """校验输入参数。"""
        if not topic or not topic.strip():
            raise ValueError("话题不能为空")
        if not (2 <= expert_count <= 8):
            raise ValueError(f"专家人数必须介于 2 和 8 之间, 实际: {expert_count}")

    # -------------------------------------------------------------------------
    # Private: LLM 调用
    # -------------------------------------------------------------------------

    def _call_llm(self, topic: str, expert_count: int) -> list[dict]:
        """调用 LLM 生成嘉宾数据。

        如果 llm_client 未注入 (测试模式), 返回空列表让 _parse_and_enrich 降级。
        """
        if self._llm is None:
            return []

        prompt = self.PROMPT_TEMPLATE.format(topic=topic, expert_count=expert_count)
        try:
            response = self._llm.generate(prompt)
            # 兼容 AsyncMock (返回 coroutine)
            if hasattr(response, "__await__"):
                import asyncio
                response = asyncio.run(response)
        except Exception as exc:
            raise RuntimeError(f"LLM 调用失败: {exc}") from exc

        data = json.loads(response) if isinstance(response, str) else response
        return data.get("guests", [])

    # -------------------------------------------------------------------------
    # Private: 解析与增强
    # -------------------------------------------------------------------------

    def _parse_and_enrich(self, raw_guests: list[dict], expert_count: int) -> list[GuestModel]:
        """解析 LLM 原始输出 → 校验 → 增强 → GuestModel 列表。

        增强步骤:
          1. Host 颜色强制设为 #E8A840
          2. Expert 颜色从 EXPERT_COLORS 按序分配, 确保唯一
          3. 缺少 persona_prompt 时自动生成
        """
        if not raw_guests:
            # 降级: LLM 未注入时返回 mock 数据
            return self._fallback_guests()

        guests: list[GuestModel] = []
        color_idx = 0

        for item in raw_guests:
            role = item.get("role", "expert")

            # 分配颜色
            if role == "host":
                item["color"] = HOST_COLOR
            else:
                item["color"] = EXPERT_COLORS[color_idx % len(EXPERT_COLORS)]
                color_idx += 1

            # 自动生成 persona_prompt
            if "persona_prompt" not in item or not item.get("persona_prompt"):
                item["persona_prompt"] = (
                    f"你是{item.get('name', '嘉宾')}, {item.get('title', '专家')}。"
                    f"你的核心立场是: {item.get('stance', '请根据讨论内容独立思考')}。"
                    f"在讨论中保持专业视角, 主动发言、补充、反驳, 但保持礼貌。"
                )

            guest = GuestModel(**item)
            guests.append(guest)

        return guests

    # -------------------------------------------------------------------------
    # Private: 降级 (LLM 不可用时)
    # -------------------------------------------------------------------------

    def _fallback_guests(self) -> list[GuestModel]:
        """LLM 未注入时的降级 mock 数据。"""
        guests = [
            GuestModel(
                role="host", name="主持人", title="资深主持人",
                stance="中立客观", stance_label="主持人",
                color=HOST_COLOR, bio="经验丰富的主持人",
                persona_prompt="你是本次讨论的主持人, 负责引导讨论、提问和总结。"
            ),
        ]
        for i in range(3):
            guests.append(GuestModel(
                role="expert", name=f"专家{i+1}", title=f"领域专家{i+1}",
                stance=f"立场{i+1}", stance_label=f"观点{i+1}",
                color=EXPERT_COLORS[i % len(EXPERT_COLORS)],
                bio=f"专家{i+1}的背景简介",
                persona_prompt=f"你是专家{i+1}, 在讨论中保持专业视角。"
            ))
        return guests
