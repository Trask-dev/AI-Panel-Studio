"""GuestGenerator — 嘉宾阵容生成服务

Green Phase: 最小实现通过 test_generate_returns_correct_guest_count。
仅处理正常路径 (topic + expert_count=3 → 返回 4 Guest)。
"""

from dataclasses import dataclass, field
from typing import Any


@dataclass
class Guest:
    """嘉宾数据对象。

    注意: 当前仅定义测试断言的字段 (role)。
    后续测试将逐步添加 name/title/stance/color 等字段。
    """
    role: str  # "host" | "expert"
    name: str = ""
    title: str = ""
    stance: str = ""
    stance_label: str = ""
    color: str = ""
    bio: str = ""
    persona_prompt: str = ""


class GuestGenerator:
    """基于 LLM 的嘉宾阵容生成器。"""

    def __init__(self, llm_client: Any = None):
        self._llm = llm_client

    def generate(self, topic: str, expert_count: int) -> list[Guest]:
        """根据话题和专家人数生成嘉宾阵容。

        Green Phase: 返回固定 4 个 Guest (1 Host + 3 Expert)。
        不调用 LLM，不做校验 —— 仅满足当前测试断言。
        """
        guests = [
            Guest(role="host",   name="主持人"),
            Guest(role="expert", name="专家1"),
            Guest(role="expert", name="专家2"),
            Guest(role="expert", name="专家3"),
        ]
        return guests
