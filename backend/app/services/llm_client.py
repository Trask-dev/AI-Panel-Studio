"""LLM Client — 大模型调用抽象层。

支持:
  - 异步调用 (async/await)
  - 超时控制 (默认 30s)
  - 自动重试 (默认 1 次, 指数退避)
  - Mock 注入 (测试模式)

用法:
  client = LLMClient(api_key="...", model="claude-sonnet-4-20250514")
  response = await client.generate(prompt)
  response = client.generate_sync(prompt)   # 同步便捷方法
"""

import asyncio
import time
from typing import Optional


class LLMClient:
    """LLM API 调用客户端。

    Args:
        api_key: LLM 服务 API Key (从环境变量读取)。
        model: 模型标识。
        base_url: API 基础 URL。
        timeout: 单次请求超时秒数。
        max_retries: 失败后最大重试次数 (0 = 不重试)。
    """

    def __init__(
        self,
        api_key: str = "",
        model: str = "claude-sonnet-4-20250514",
        base_url: str = "https://api.anthropic.com/v1",
        timeout: float = 30.0,
        max_retries: int = 1,
    ):
        self.api_key = api_key
        self.model = model
        self.base_url = base_url
        self.timeout = timeout
        self.max_retries = max_retries
        self._call_count = 0          # 测试用: 记录调用次数
        self._last_prompt: Optional[str] = None

    # -------------------------------------------------------------------------
    # Public API
    # -------------------------------------------------------------------------

    async def generate(self, prompt: str) -> str:
        """异步调用 LLM 生成响应。

        Args:
            prompt: 提示词文本。

        Returns:
            LLM 生成的原始文本响应。

        Raises:
            RuntimeError: 所有重试均失败后抛出。
        """
        self._last_prompt = prompt

        last_exc = None
        for attempt in range(self.max_retries + 1):
            self._call_count += 1  # 每次尝试递增
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
        """同步便捷方法 (内部调用 asyncio.run)。"""
        return asyncio.run(self.generate(prompt))

    # -------------------------------------------------------------------------
    # Private
    # -------------------------------------------------------------------------

    async def _do_generate(self, prompt: str) -> str:
        """实际 LLM 调用逻辑。

        基类返回占位文本；子类或 Mock 可覆盖此方法。
        """
        # 模拟 LLM 响应 (真实实现替换为 HTTP 调用)
        return f'{{"guests": [{{"role": "host", "name": "主持人"}}]}}'

    # -------------------------------------------------------------------------
    # 测试辅助
    # -------------------------------------------------------------------------

    @property
    def call_count(self) -> int:
        """LLM 被调用的总次数 (测试断言用)。"""
        return self._call_count


class MockLLMClient(LLMClient):
    """测试用 Mock LLM 客户端。

    预设响应内容，不发起真实 HTTP 请求。
    """

    def __init__(self, preset_response: str = "{}", **kwargs):
        super().__init__(api_key="mock", **kwargs)
        self.preset_response = preset_response

    async def _do_generate(self, prompt: str) -> str:
        return self.preset_response
