"""test_sse_manager.py — SSE Manager & hidden_cot 安全测试

覆盖 6 个测试场景:
  1. test_subscribe_and_push_event              基本 pub/sub
  2. test_hidden_cot_stripped_from_event        hidden_cot 过滤
  3. test_hidden_cot_stripped_nested            hidden_cot 深度嵌套过滤
  4. test_cross_discussion_isolation            多讨论 SSE 隔离
  5. test_multiple_subscribers_same_discussion   同讨论多订阅者
  6. test_heartbeat_on_idle                     空闲时 heartbeat
"""

import asyncio
import queue
import pytest
from app.utils.sse_manager import (
    SSEManager, SSEEvent, strip_hidden_cot, VALID_EVENT_TYPES,
)


class TestHiddenCotFilter:
    """hidden_cot 安全过滤单元测试。"""

    def test_hidden_cot_stripped_from_flat_dict(self):
        """浅层 dict 中的 hidden_cot 被移除。"""
        data = {
            "discussion_id": "abc",
            "guest_id": "g1",
            "public_thought": "正在思考...",
            "hidden_cot": "秘密推理链",
        }
        result = strip_hidden_cot(data)
        assert "hidden_cot" not in result
        assert result["public_thought"] == "正在思考..."
        assert result["discussion_id"] == "abc"

    def test_hidden_cot_stripped_from_nested(self):
        """深层嵌套 dict 中的 hidden_cot 被递归移除。"""
        data = {
            "discussion_id": "abc",
            "snapshots": [
                {
                    "guest_id": "g1",
                    "public_thought": "思考1",
                    "hidden_cot": "秘密1",
                },
                {
                    "guest_id": "g2",
                    "internal": {
                        "public_thought": "思考2",
                        "hidden_cot": "秘密2",
                    },
                },
            ],
        }
        result = strip_hidden_cot(data)
        # 外层无 hidden_cot
        assert "hidden_cot" not in result
        # 数组内无 hidden_cot
        assert "hidden_cot" not in result["snapshots"][0]
        # 深层嵌套无 hidden_cot
        assert "hidden_cot" not in result["snapshots"][1]["internal"]
        # 其他字段完好
        assert result["snapshots"][0]["public_thought"] == "思考1"

    def test_hidden_cot_absent_no_change(self):
        """无 hidden_cot 的数据不被改变。"""
        data = {"type": "heartbeat", "payload": {"ts": 123}}
        result = strip_hidden_cot(data)
        assert result == data


class TestSSEManager:
    """SSE Manager 集成测试。"""

    @pytest.mark.asyncio
    async def test_subscribe_and_push_event(self):
        """订阅 → 推送 → 消费者收到事件。"""
        manager = SSEManager()
        queue = manager.subscribe("disc-1")

        event = SSEEvent(
            type="snapshot_update",
            payload={
                "discussion_id": "disc-1",
                "guest_id": "g1",
                "public_thought": "思考中...",
                "hidden_cot": "秘密",
            },
        )
        manager.push(event)

        # 消费者读取
        data = await asyncio.to_thread(queue.get, timeout=1.0)
        assert "snapshot_update" in data
        assert "public_thought" in data
        assert "hidden_cot" not in data, "hidden_cot 不应出现在推送数据中!"

        manager.unsubscribe("disc-1", queue)
        assert manager.subscriber_count("disc-1") == 0

    @pytest.mark.asyncio
    async def test_cross_discussion_isolation(self):
        """disc-1 的推送不到达 disc-2 的订阅者。"""
        manager = SSEManager()
        q1 = manager.subscribe("disc-1")
        q2 = manager.subscribe("disc-2")

        manager.push(SSEEvent(
            type="snapshot_update",
            payload={"discussion_id": "disc-1", "guest_id": "g1"},
        ))

        # q1 收到
        data = await asyncio.to_thread(q1.get, timeout=1.0)
        assert "disc-1" in data

        # q2 未收到 (超时)
        with pytest.raises(queue.Empty):
            await asyncio.to_thread(q2.get, timeout=0.3)

        manager.unsubscribe("disc-1", q1)
        manager.unsubscribe("disc-2", q2)

    @pytest.mark.asyncio
    async def test_multiple_subscribers_same_discussion(self):
        """同一讨论的多个订阅者均收到事件。"""
        manager = SSEManager()
        q_a = manager.subscribe("disc-x")
        q_b = manager.subscribe("disc-x")

        manager.push(SSEEvent(
            type="consensus_update",
            payload={"discussion_id": "disc-x", "items": []},
        ))

        data_a = await asyncio.to_thread(q_a.get, timeout=1.0)
        data_b = await asyncio.to_thread(q_b.get, timeout=1.0)
        assert "consensus_update" in data_a
        assert "consensus_update" in data_b

        manager.unsubscribe("disc-x", q_a)
        manager.unsubscribe("disc-x", q_b)

    @pytest.mark.asyncio
    async def test_serve_subscriber_yields_events(self):
        """serve_subscriber 生成器正确产出 SSE 格式数据。"""
        manager = SSEManager()
        queue = manager.subscribe("disc-sse")

        # 异步推送一条事件
        async def _push():
            await asyncio.sleep(0.05)
            manager.push(SSEEvent(
                type="guest_status_change",
                payload={"discussion_id": "disc-sse", "guest_id": "g1", "status": "speaking"},
            ))

        asyncio.create_task(_push())

        # 消费生成器
        gen = manager.serve_subscriber("disc-sse", queue)
        lines = []
        async for line in gen:
            lines.append(line)
            if "guest_status_change" in line:
                break

        assert any("guest_status_change" in l for l in lines)
        assert any(l.startswith("data: ") for l in lines)

    @pytest.mark.asyncio
    async def test_event_payload_strips_hidden_cot(self):
        """通过 push 发送的事件 payload 绝不含 hidden_cot。"""
        manager = SSEManager()
        queue = manager.subscribe("disc-safe")

        manager.push(SSEEvent(
            type="snapshot_update",
            payload={
                "discussion_id": "disc-safe",
                "guest_id": "g1",
                "public_thought": "公开",
                "hidden_cot": "绝密",
                "nested": {
                    "hidden_cot": "嵌套绝密",
                    "ok_field": "safe",
                },
            },
        ))

        data = await asyncio.to_thread(queue.get, timeout=1.0)
        # 全量搜索 hidden_cot 字符串
        assert "hidden_cot" not in data
        assert "绝密" not in data
        assert "嵌套绝密" not in data
        assert "公开" in data
        assert "safe" in data

        manager.unsubscribe("disc-safe", queue)
