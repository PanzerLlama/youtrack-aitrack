"""AiReportAction — render a prompt and write LLM output to an issue field/comment."""

from __future__ import annotations

from typing import Any, Literal, Protocol

from pydantic import PrivateAttr

from youtrack_aitrack.domain.action import ActionSpec
from youtrack_aitrack.domain.context import Context
from youtrack_aitrack.domain.run import ActionResult
from youtrack_aitrack.registry import register_action


class LLMClient(Protocol):
    async def complete(self, prompt: str, model: str) -> str: ...


class PromptRenderer(Protocol):
    def render(self, template: str, ctx: Context) -> str: ...


class _NoOpLLM:
    async def complete(self, prompt: str, model: str) -> str:
        return ""


class _IdentityRenderer:
    def render(self, template: str, ctx: Context) -> str:
        return template


@register_action("ai_report")
class AiReportAction(ActionSpec):
    type: Literal["ai_report"] = "ai_report"
    prompt: str
    model: str

    _llm: LLMClient = PrivateAttr()
    _renderer: PromptRenderer = PrivateAttr()

    def __init__(
        self,
        *,
        llm: LLMClient | None = None,
        renderer: PromptRenderer | None = None,
        **data: Any,
    ) -> None:
        super().__init__(**data)
        self._llm = llm if llm is not None else _NoOpLLM()
        self._renderer = renderer if renderer is not None else _IdentityRenderer()

    async def execute(self, ctx: Context) -> ActionResult:
        rendered = self._renderer.render(self.prompt, ctx)
        text = await self._llm.complete(rendered, self.model)
        return ActionResult(
            action_id=self.id,
            success=True,
            output={"text": text, "model": self.model},
        )
