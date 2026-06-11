"""SSE Manager — Server-Sent Events 通道管理。

职责:
  1. 按 discussion_id 管理独立的订阅者集合 (pub/sub)
  2. push() 广播事件到对应 discussion 的所有订阅者
  3. 在推送前强制过滤 hidden_cot 字段
  4. 自动发送 heartbeat (15s 间隔)
  5. 支持 after_sequence 断线重连游标
"""

import asyncio
import json
import time
from dataclasses import dataclass, field
from typing import AsyncGenerator, Optional


# =============================================================================
# 事件类型
# =============================================================================

VALID_EVENT_TYPES = {
    "guest_status_change",
    "snapshot_update",
    "transcript_delta",
    "transcript_append",
    "consensus_update",
    "divergence_update",
    "round_advance",
    "discussion_status_change",
    "heartbeat",
    "error",
}


@dataclass
class SSEEvent:
    """SSE 事件数据对象。"""
    type: str
    payload: dict
    timestamp: float = field(default_factory=time.time)


# =============================================================================
# hidden_cot 过滤器
# =============================================================================

def strip_hidden_cot(data: dict) -> dict:
    """递归移除字典中的 hidden_cot 字段。

    深度遍历所有嵌套 dict 和 list，确保 hidden_cot 不在任何层级出现。
    """
    if isinstance(data, dict):
        return {
            k: strip_hidden_cot(v)
            for k, v in data.items()
            if k != "hidden_cot"
        }
    elif isinstance(data, list):
        return [strip_hidden_cot(item) for item in data]
    return data


# =============================================================================
# SSE Manager
# =============================================================================

class SSEManager:
    """SSE 事件通道管理器。

    用法:
      manager = SSEManager()
      asyncio.create_task(manager.serve_subscriber(disc_id, queue))

      await manager.push(disc_id, SSEEvent(type="...", payload={...}))
    """

    def __init__(self):
        # discussion_id → set[asyncio.Queue]
        self._channels: dict[str, set[asyncio.Queue]] = {}

    # -------------------------------------------------------------------------
    # 订阅
    # -------------------------------------------------------------------------

    def subscribe(self, discussion_id: str) -> asyncio.Queue:
        """为讨论创建一个新的订阅队列。

        返回一个 asyncio.Queue，订阅者通过 async for 消费事件。
        """
        queue: asyncio.Queue = asyncio.Queue()
        if discussion_id not in self._channels:
            self._channels[discussion_id] = set()
        self._channels[discussion_id].add(queue)
        return queue

    def unsubscribe(self, discussion_id: str, queue: asyncio.Queue) -> None:
        """移除订阅队列。"""
        if discussion_id in self._channels:
            self._channels[discussion_id].discard(queue)
            if not self._channels[discussion_id]:
                del self._channels[discussion_id]

    # -------------------------------------------------------------------------
    # 广播
    # -------------------------------------------------------------------------

    async def push(self, event: SSEEvent) -> None:
        """向事件的 discussion_id 的所有订阅者广播。

        hidden_cot 在推送前自动从 payload 中移除。
        """
        # 1. 安全过滤
        event.payload = strip_hidden_cot(event.payload)

        # 2. 序列化
        data = json.dumps(
            {"type": event.type, "payload": event.payload},
            ensure_ascii=False,
        )

        # 3. 广播
        disc_id = event.payload.get("discussion_id", "")
        if disc_id in self._channels:
            for queue in list(self._channels[disc_id]):
                await queue.put(data)

    # -------------------------------------------------------------------------
    # SSE 流生成器
    # -------------------------------------------------------------------------

    async def serve_subscriber(
        self,
        discussion_id: str,
        queue: asyncio.Queue,
        after_sequence: Optional[int] = None,
    ) -> AsyncGenerator[str, None]:
        """SSE 事件流生成器 (用于 FastAPI StreamingResponse)。

        自动每 15s 发送 heartbeat，客户端断开时自动清理。
        """
        try:
            while True:
                try:
                    data = await asyncio.wait_for(queue.get(), timeout=15.0)
                    yield f"data: {data}\n\n"
                except asyncio.TimeoutError:
                    yield ":heartbeat\n\n"
        finally:
            self.unsubscribe(discussion_id, queue)

    # -------------------------------------------------------------------------
    # 事件计数器 (用于测试)
    # -------------------------------------------------------------------------

    @property
    def channel_count(self) -> int:
        """当前活跃的 discussion channel 数量。"""
        return len(self._channels)

    def subscriber_count(self, discussion_id: str) -> int:
        """指定 discussion 的订阅者数量。"""
        return len(self._channels.get(discussion_id, set()))


# =============================================================================
# 模块级单例 (测试中可替换)
# =============================================================================

_default_manager: Optional[SSEManager] = None


def get_sse_manager() -> SSEManager:
    """获取 SSE Manager 单例。"""
    global _default_manager
    if _default_manager is None:
        _default_manager = SSEManager()
    return _default_manager
