"""SSE Manager — Server-Sent Events 通道管理 (线程安全版)。

修复: 使用 queue.Queue (线程安全) 替代 asyncio.Queue，
      解决 sync 线程 (Orchestrator) 无法向 async 订阅者推送的问题。
"""

import asyncio
import json
import queue
import time
from dataclasses import dataclass, field
from typing import AsyncGenerator, Optional


VALID_EVENT_TYPES = {
    "guest_status_change", "snapshot_update", "transcript_delta",
    "transcript_append", "consensus_update", "divergence_update",
    "round_advance", "discussion_status_change", "heartbeat", "error",
}


@dataclass
class SSEEvent:
    type: str
    payload: dict
    timestamp: float = field(default_factory=time.time)


def strip_hidden_cot(data: dict) -> dict:
    if isinstance(data, dict):
        return {k: strip_hidden_cot(v) for k, v in data.items() if k != "hidden_cot"}
    elif isinstance(data, list):
        return [strip_hidden_cot(item) for item in data]
    return data


class SSEManager:
    """线程安全的 SSE 事件通道。"""

    def __init__(self):
        self._channels: dict[str, set[queue.Queue]] = {}

    def subscribe(self, discussion_id: str) -> queue.Queue:
        q: queue.Queue = queue.Queue()
        if discussion_id not in self._channels:
            self._channels[discussion_id] = set()
        self._channels[discussion_id].add(q)
        return q

    def unsubscribe(self, discussion_id: str, q: queue.Queue) -> None:
        if discussion_id in self._channels:
            self._channels[discussion_id].discard(q)
            if not self._channels[discussion_id]:
                del self._channels[discussion_id]

    def push(self, event: SSEEvent) -> None:
        """线程安全推送。可从 sync 或 async 代码调用。"""
        event.payload = strip_hidden_cot(event.payload)
        data = json.dumps(
            {"type": event.type, "payload": event.payload},
            ensure_ascii=False,
        )
        disc_id = event.payload.get("discussion_id", "")
        if disc_id in self._channels:
            for q in list(self._channels[disc_id]):
                try:
                    q.put_nowait(data)
                except queue.Full:
                    pass

    async def serve_subscriber(
        self,
        discussion_id: str,
        q: queue.Queue,
    ) -> AsyncGenerator[str, None]:
        """SSE 事件流生成器。从线程安全队列轮询数据。"""
        try:
            while True:
                try:
                    data = await asyncio.to_thread(q.get, timeout=1.0)
                    yield f"data: {data}\n\n"
                except queue.Empty:
                    yield ":heartbeat\n\n"
        finally:
            self.unsubscribe(discussion_id, q)

    @property
    def channel_count(self) -> int:
        return len(self._channels)

    def subscriber_count(self, discussion_id: str) -> int:
        return len(self._channels.get(discussion_id, set()))


_default_manager: Optional[SSEManager] = None


def get_sse_manager() -> SSEManager:
    global _default_manager
    if _default_manager is None:
        _default_manager = SSEManager()
    return _default_manager
