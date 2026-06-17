"""LLM Client — 大模型调用抽象层。

支持:
  - Deepseek V4 (OpenAI 兼容 API)
  - 异步调用 (async/await)
  - 超时控制 (默认 30s)
  - 自动重试 (默认 1 次, 指数退避)
"""

import asyncio
import time
from typing import Optional


class LLMClient:
    """LLM API 调用客户端。

    Args:
        api_key: LLM 服务 API Key。
        model: 模型标识 (deepseek-chat, deepseek-reasoner 等)。
        base_url: API 基础 URL。
        timeout: 单次请求超时秒数。
        max_retries: 失败后最大重试次数 (0 = 不重试)。
    """

    def __init__(
        self,
        api_key: str,
        model: str,
        base_url: str,
        timeout: float = 30.0,
        max_retries: int = 1,
    ):
        self.api_key = api_key
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.max_retries = max_retries
        self._call_count = 0
        self._last_prompt: Optional[str] = None

    # -------------------------------------------------------------------------
    # Public API
    # -------------------------------------------------------------------------

    async def generate(self, prompt: str) -> str:
        """异步调用 LLM 生成响应。"""
        self._last_prompt = prompt
        last_exc = None

        for attempt in range(self.max_retries + 1):
            self._call_count += 1
            try:
                return await asyncio.wait_for(
                    self._do_generate(prompt),
                    timeout=self.timeout,
                )
            except asyncio.TimeoutError as exc:
                last_exc = exc
                if attempt < self.max_retries:
                    await asyncio.sleep(2 ** attempt)
            except Exception as exc:
                last_exc = exc
                if attempt < self.max_retries:
                    await asyncio.sleep(2 ** attempt)

        raise RuntimeError(
            f"LLM 调用失败 (已重试 {self.max_retries} 次): {last_exc}"
        )

    def generate_sync(self, prompt: str) -> str:
        """同步便捷方法。"""
        return asyncio.run(self.generate(prompt))

    # -------------------------------------------------------------------------
    # Private: HTTP 调用
    # -------------------------------------------------------------------------

    async def _do_generate(self, prompt: str) -> str:
        """实际 LLM HTTP 调用 — Deepseek / OpenAI 兼容 API。"""
        import httpx

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        body = {
            "model": self.model,
            "messages": [
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.7,
            "max_tokens": 2048,
        }

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            resp = await client.post(
                f"{self.base_url}/chat/completions",
                json=body,
                headers=headers,
            )
            resp.raise_for_status()
            data = resp.json()
            return data["choices"][0]["message"]["content"]

    # -------------------------------------------------------------------------
    # 测试辅助
    # -------------------------------------------------------------------------

    @property
    def call_count(self) -> int:
        return self._call_count


class MockLLMClient(LLMClient):
    """测试用 Mock LLM 客户端。"""

    def __init__(self, preset_response: str = "{}", **kwargs):
        super().__init__(api_key="mock", **kwargs)
        self.preset_response = preset_response

    async def _do_generate(self, prompt: str) -> str:
        return self.preset_response
