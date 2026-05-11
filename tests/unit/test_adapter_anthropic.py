"""Tests for AnthropicLLMClient adapter (no real API calls)."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest
from anthropic import AsyncAnthropic
from anthropic.types import TextBlock

from youtrack_aitrack.adapters.llm.anthropic import AnthropicLLMClient
from youtrack_aitrack.domain.actions.ai_report import LLMClient


def _accepts_llm(client: LLMClient) -> LLMClient:
    return client


def _text_block(text: str) -> TextBlock:
    return TextBlock(type="text", text=text, citations=None)


def _make_adapter(create_fn: Any) -> AnthropicLLMClient:
    """Build an adapter with a fake messages.create on a real SDK client."""
    real = AsyncAnthropic(api_key="test")
    real.messages.create = create_fn  # type: ignore[method-assign]
    return AnthropicLLMClient("test", client=real)


def test_adapter_satisfies_llm_client_protocol() -> None:
    adapter = _make_adapter(None)
    accepted = _accepts_llm(adapter)
    assert accepted is adapter


async def test_complete_returns_concatenated_text() -> None:
    async def fake_create(**_: Any) -> SimpleNamespace:
        return SimpleNamespace(content=[_text_block("hello")])

    adapter = _make_adapter(fake_create)
    out = await adapter.complete("prompt", "claude-sonnet-4-6")
    assert out == "hello"


async def test_complete_forwards_model_and_prompt() -> None:
    captured: dict[str, Any] = {}

    async def fake_create(**kwargs: Any) -> SimpleNamespace:
        captured.update(kwargs)
        return SimpleNamespace(content=[_text_block("ok")])

    adapter = _make_adapter(fake_create)
    await adapter.complete("hello there", "claude-opus-4-7")
    assert captured["model"] == "claude-opus-4-7"
    assert captured["messages"] == [{"role": "user", "content": "hello there"}]
    assert captured["max_tokens"] == 4096


async def test_complete_concatenates_multiple_text_blocks() -> None:
    async def fake_create(**_: Any) -> SimpleNamespace:
        return SimpleNamespace(
            content=[_text_block("part-a"), _text_block(" part-b"), _text_block(" part-c")]
        )

    adapter = _make_adapter(fake_create)
    assert await adapter.complete("p", "m") == "part-a part-b part-c"


async def test_complete_skips_non_text_blocks() -> None:
    async def fake_create(**_: Any) -> SimpleNamespace:
        return SimpleNamespace(
            content=[
                _text_block("keep-1"),
                SimpleNamespace(type="tool_use", text="ignored"),
                _text_block("keep-2"),
            ]
        )

    adapter = _make_adapter(fake_create)
    assert await adapter.complete("p", "m") == "keep-1keep-2"


async def test_complete_propagates_sdk_errors() -> None:
    async def fake_create(**_: Any) -> SimpleNamespace:
        raise RuntimeError("rate limited")

    adapter = _make_adapter(fake_create)
    with pytest.raises(RuntimeError, match="rate limited"):
        await adapter.complete("p", "m")


def test_custom_max_tokens_is_used() -> None:
    captured: dict[str, Any] = {}

    async def fake_create(**kwargs: Any) -> SimpleNamespace:
        captured.update(kwargs)
        return SimpleNamespace(content=[_text_block("x")])

    real = AsyncAnthropic(api_key="test")
    real.messages.create = fake_create  # type: ignore[method-assign]
    adapter = AnthropicLLMClient("test", max_tokens=512, client=real)

    import asyncio

    asyncio.run(adapter.complete("p", "m"))
    assert captured["max_tokens"] == 512
