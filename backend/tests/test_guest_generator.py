"""test_guest_generator.py — GuestGenerator 单元测试

TDD Phase: RED
当前 GuestGenerator.generate() 返回 None，以下测试预期全部失败。
Green Phase 将实现业务逻辑使测试通过。
"""

import pytest
from app.services.persona_generator import GuestGenerator


class TestGuestGeneratorGenerate:
    """测试 GuestGenerator.generate() 方法。"""

    def test_generate_returns_correct_guest_count(self, llm_mock):
        """
        [RED] 输入 topic + expert_count=3，预期返回 4 个 Guest (1 Host + 3 Expert)。

        当前状态: GuestGenerator.generate() 返回 None，
        因此访问 len() 或下标将触发 TypeError，测试失败 —— 符合 Red Phase 预期。
        """
        # Arrange
        generator = GuestGenerator(llm_client=llm_mock)
        topic = "AI会取代人类工作吗"
        expert_count = 3

        # Act
        result = generator.generate(topic=topic, expert_count=expert_count)

        # Assert — 正常路径预期
        assert result is not None, "generate() 返回了 None —— 方法尚未实现 (Red Phase 预期)"
        assert len(result) == 4, (
            f"期望 1 Host + 3 Expert = 4 位嘉宾, 实际 {len(result)} 位"
        )
        assert result[0].role == "host", (
            f"第一位嘉宾应为 host, 实际为 {result[0].role if hasattr(result[0], 'role') else 'N/A'}"
        )
        for i, guest in enumerate(result[1:], start=1):
            assert guest.role == "expert", (
                f"嘉宾[{i}] 应为 expert, 实际为 {guest.role if hasattr(guest, 'role') else 'N/A'}"
            )
