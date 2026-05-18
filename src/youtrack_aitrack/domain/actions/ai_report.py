"""AiReportAction — render a prompt and route it through an AgentRunner backend."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Literal, Protocol

from pydantic import PrivateAttr

from youtrack_aitrack.domain.action import ActionSpec
from youtrack_aitrack.domain.agent_runner import AgentResult, AgentRunner, AgentRunnerError
from youtrack_aitrack.domain.context import Context
from youtrack_aitrack.domain.run import ActionResult
from youtrack_aitrack.registry import register_action

_DEFAULT_TIMEOUT_S = 300.0


class PromptRenderer(Protocol):
    def render(self, template: str, ctx: Context) -> str: ...


class _NoOpAgentRunner:
    async def run(
        self,
        prompt: str,
        *,
        cwd: Path,
        commit_sha: str | None,
        timeout_s: float,
        model: str | None = None,
    ) -> AgentResult:
        return AgentResult(output="", exit_code=0, duration_s=0.0, model_used=model)


class _IdentityRenderer:
    def render(self, template: str, ctx: Context) -> str:
        return template


@register_action("ai_report")
class AiReportAction(ActionSpec):
    type: Literal["ai_report"] = "ai_report"
    prompt: str
    model: str
    agent: str | None = None

    _runner: AgentRunner = PrivateAttr()
    _renderer: PromptRenderer = PrivateAttr()
    _timeout_s: float = PrivateAttr()

    def __init__(
        self,
        *,
        runner: AgentRunner | None = None,
        renderer: PromptRenderer | None = None,
        timeout_s: float = _DEFAULT_TIMEOUT_S,
        **data: Any,
    ) -> None:
        super().__init__(**data)
        self._runner = runner if runner is not None else _NoOpAgentRunner()
        self._renderer = renderer if renderer is not None else _IdentityRenderer()
        self._timeout_s = timeout_s

    async def execute(self, ctx: Context) -> ActionResult:
        rendered = self._renderer.render(self.prompt, ctx)
        cwd = ctx.repo_path if ctx.repo_path is not None else Path(".")
        try:
            result = await self._runner.run(
                rendered,
                cwd=cwd,
                commit_sha=ctx.commit_sha,
                timeout_s=self._timeout_s,
                model=self.model,
            )
        except AgentRunnerError as exc:
            return ActionResult(action_id=self.id, success=False, error=str(exc))
        return ActionResult(
            action_id=self.id,
            success=True,
            output={"text": result.output, "model": result.model_used or self.model},
        )
