"""AnthropicLLMClient — wraps the anthropic SDK as an LLMClient adapter."""

from __future__ import annotations

from anthropic import AsyncAnthropic
from anthropic.types import TextBlock


class AnthropicLLMClient:
    def __init__(
        self,
        api_key: str,
        *,
        base_url: str | None = None,
        max_tokens: int = 4096,
        timeout_seconds: float = 60.0,
        client: AsyncAnthropic | None = None,
    ) -> None:
        self._max_tokens = max_tokens
        if client is not None:
            self._client = client
        elif base_url is not None:
            self._client = AsyncAnthropic(
                api_key=api_key, base_url=base_url, timeout=timeout_seconds
            )
        else:
            self._client = AsyncAnthropic(api_key=api_key, timeout=timeout_seconds)

    async def complete(self, prompt: str, model: str) -> str:
        msg = await self._client.messages.create(
            model=model,
            max_tokens=self._max_tokens,
            messages=[{"role": "user", "content": prompt}],
        )
        parts: list[str] = []
        for block in msg.content:
            if isinstance(block, TextBlock):
                parts.append(block.text)
        return "".join(parts)
