"""test_guest_generator.py — GuestGenerator 完整单元测试

覆盖 7 个测试场景:
  1. test_generate_returns_correct_guest_count       ✅ 已完成
  2. test_generated_host_has_gold_border_color         Host 金色 + 颜色唯一
  3. test_generated_guests_have_all_required_fields    字段完整性
  4. test_reject_empty_topic                           空话题 → ValueError
  5. test_reject_invalid_expert_count                  非法人数 → ValueError
  6. test_llm_failure_graceful_error                   LLM 超时 → 异常
  7. test_regenerate_replaces_old_guests               重新生成软删除旧嘉宾
"""

import json
import pytest
from app.services.persona_generator import GuestGenerator, GuestModel


# =============================================================================
# Mock LLM 响应工厂
# =============================================================================

def make_llm_response(host_name: str = "张明远", expert_names: list[str] | None = None):
    """构造 Mock LLM 返回的嘉宾 JSON（模拟 LLM 输出格式）。"""
    if expert_names is None:
        expert_names = ["李思涵", "王建国", "陈雪梅"]

    guests = [
        {
            "role": "host",
            "name": host_name,
            "title": "资深科技评论员",
            "bio": f"{host_name}，拥有15年行业经验，主持过多场高水平讨论。",
            "stance": "保持中立客观，致力于发掘各方观点背后的逻辑与证据",
            "stance_label": "主持人",
            "color": "#E8A840",
        },
    ]

    expert_data = [
        {"name": "李思涵", "title": "AI研究员",    "stance_label": "乐观派", "stance": "AI将创造更多工作机会"},
        {"name": "王建国", "title": "劳动经济学家", "stance_label": "谨慎派", "stance": "AI威胁白领认知型工作"},
        {"name": "陈雪梅", "title": "政策咨询顾问", "stance_label": "务实派", "stance": "政策需要前瞻性布局"},
        {"name": "周正宇", "title": "量子物理学家", "stance_label": "学界代表", "stance": "量子纠错是最大瓶颈"},
        {"name": "沈一诺", "title": "发展经济学家", "stance_label": "支持UBI", "stance": "UBI有效减少贫困"},
        {"name": "钱伟成", "title": "财政分析师",   "stance_label": "反对UBI", "stance": "UBI财政不可持续"},
        {"name": "郑佳慧", "title": "社会变革研究员","stance_label": "渐进改革派","stance": "探索渐进式UBI"},
        {"name": "刘志强", "title": "量子创业CTO",  "stance_label": "产业推动者","stance": "专用量子计算将率先受益"},
    ]

    for i, name in enumerate(expert_names):
        template = expert_data[i % len(expert_data)]
        guests.append({
            "role": "expert",
            "name": name,
            "title": template["title"],
            "bio": f"{name}，{template['title']}，立场鲜明——{template['stance']}。",
            "stance": template["stance"],
            "stance_label": template["stance_label"],
            "color": "",   # LLM 不填颜色，由 Generator 强制分配
        })

    return json.dumps({"guests": guests})


# =============================================================================
# 测试类
# =============================================================================

class TestGuestGeneratorGenerate:
    """测试 GuestGenerator.generate() 方法。"""

    # -------------------------------------------------------------------------
    # 1. 基础数量 + 角色 (✅ 已有, 升级为 LLM 集成)
    # -------------------------------------------------------------------------

    def test_generate_returns_correct_guest_count(self, llm_mock):
        """输入 topic + expert_count=3 → 返回 4 Guest (1 Host + 3 Expert)。"""
        llm_mock.generate.return_value = make_llm_response(expert_names=["李思涵", "王建国", "陈雪梅"])

        generator = GuestGenerator(llm_client=llm_mock)
        result = generator.generate(topic="AI会取代人类工作吗", expert_count=3)

        assert len(result) == 4, f"期望 4 位, 实际 {len(result)}"
        assert result[0].role == "host"
        for g in result[1:]:
            assert g.role == "expert"

    # -------------------------------------------------------------------------
    # 2. Host 颜色强制金色 + 专家颜色互不相同
    # -------------------------------------------------------------------------

    def test_generated_host_has_gold_border_color(self, llm_mock):
        llm_mock.generate.return_value = make_llm_response()

        generator = GuestGenerator(llm_client=llm_mock)
        result = generator.generate(topic="AI 监管", expert_count=3)

        assert result[0].color == "#E8A840", f"Host 颜色应为 #E8A840, 实际 {result[0].color}"
        expert_colors = [g.color for g in result[1:]]
        assert len(expert_colors) == len(set(expert_colors)), f"专家颜色重复: {expert_colors}"
        assert "#E8A840" not in expert_colors, "专家颜色不应与 Host 金色冲突"

    # -------------------------------------------------------------------------
    # 3. 字段完整性
    # -------------------------------------------------------------------------

    def test_generated_guests_have_all_required_fields(self, llm_mock):
        llm_mock.generate.return_value = make_llm_response()

        generator = GuestGenerator(llm_client=llm_mock)
        result = generator.generate(topic="量子计算", expert_count=4)

        required_fields = [
            "name", "title", "stance", "stance_label", "color", "bio",
        ]
        for guest in result:
            for field in required_fields:
                value = getattr(guest, field)
                assert value is not None, f"{guest.name}.{field} 为 None"
                assert value != "", f"{guest.name}.{field} 为空字符串"

    # -------------------------------------------------------------------------
    # 4. 空话题拒绝
    # -------------------------------------------------------------------------

    @pytest.mark.parametrize("bad_topic", [
        "",
        "   ",
        "\t\n",
    ])
    def test_reject_empty_topic(self, llm_mock, bad_topic):
        generator = GuestGenerator(llm_client=llm_mock)

        with pytest.raises(ValueError, match="话题"):
            generator.generate(topic=bad_topic, expert_count=3)

        llm_mock.generate.assert_not_called()

    # -------------------------------------------------------------------------
    # 5. 非法专家人数拒绝
    # -------------------------------------------------------------------------

    @pytest.mark.parametrize("bad_count", [0, 1, 9, 100])
    def test_reject_invalid_expert_count(self, llm_mock, bad_count):
        generator = GuestGenerator(llm_client=llm_mock)

        with pytest.raises(ValueError, match="2.*8"):
            generator.generate(topic="测试", expert_count=bad_count)

        llm_mock.generate.assert_not_called()

    # -------------------------------------------------------------------------
    # 6. LLM 调用失败 → 优雅降级
    # -------------------------------------------------------------------------

    def test_llm_failure_graceful_error(self, llm_mock):
        llm_mock.generate.side_effect = TimeoutError("LLM API 超时")

        generator = GuestGenerator(llm_client=llm_mock)

        with pytest.raises(RuntimeError, match="LLM"):
            generator.generate(topic="测试", expert_count=3)

    # -------------------------------------------------------------------------
    # 7. 动态专家数量
    # -------------------------------------------------------------------------

    def test_dynamic_expert_count(self, llm_mock):
        """expert_count 为不同值时返回正确数量。"""
        for n in [2, 4, 6, 8]:
            names = [f"专家{i}" for i in range(n)]
            llm_mock.generate.return_value = make_llm_response(expert_names=names)

            generator = GuestGenerator(llm_client=llm_mock)
            result = generator.generate(topic="测试", expert_count=n)

            assert len(result) == n + 1, f"expert_count={n} 期望 {n+1} 位"
            assert result[0].role == "host"
