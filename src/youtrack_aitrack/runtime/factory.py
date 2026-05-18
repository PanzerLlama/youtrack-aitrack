"""ActionFactory — rebuild ActionSpec instances with concrete adapter dependencies."""

from __future__ import annotations

from pathlib import Path

from youtrack_aitrack.domain.action import ActionSpec
from youtrack_aitrack.domain.actions.ai_report import AiReportAction, PromptRenderer
from youtrack_aitrack.domain.actions.set_field import FieldWriter, SetFieldAction
from youtrack_aitrack.domain.actions.yt_comment import CommentPoster, YtCommentAction
from youtrack_aitrack.domain.agent_runner import AgentResult, AgentRunner
from youtrack_aitrack.domain.output import CommentOutput, CustomFieldOutput
from youtrack_aitrack.domain.workflow import Workflow


class NoOpFieldWriter:
    """Dry-run FieldWriter — accepts calls, performs no I/O."""

    async def set_fields(self, issue_id: str, fields: dict[str, str]) -> None:
        return None


class NoOpCommentPoster:
    """Dry-run CommentPoster — accepts calls, performs no I/O."""

    async def post_comment(self, issue_id: str, body: str) -> None:
        return None


class StandardOutputSink:
    """Dispatches OutputSpec writes to the appropriate adapter by ``spec.kind``.

    Holds the same FieldWriter / CommentPoster the ActionFactory uses, so swapping in
    NoOp adapters (dry-run) automatically suppresses output writes too.
    """

    def __init__(self, *, writer: FieldWriter, poster: CommentPoster) -> None:
        self._writer = writer
        self._poster = poster

    async def write(
        self, *, issue_id: str, spec: CustomFieldOutput | CommentOutput, value: str
    ) -> None:
        if isinstance(spec, CustomFieldOutput):
            await self._writer.set_fields(issue_id, {spec.name: value})
        elif isinstance(spec, CommentOutput):
            await self._poster.post_comment(issue_id, value)


class StubAgentRunner:
    """Cost-free AgentRunner — returns a marked placeholder instead of invoking a backend.

    Used by --stub-llm to smoke-test the trigger -> dispatch -> action path without
    spending tokens or shelling out. Output echoes the request fields so users can
    verify their wiring (model flowed through, prompt rendered to non-empty content,
    repo + commit context plumbed correctly).
    """

    async def run(
        self,
        prompt: str,
        *,
        cwd: Path,
        commit_sha: str | None,
        timeout_s: float,
        model: str | None = None,
    ) -> AgentResult:
        body = (
            "[STUB AGENT] action stub — no real agent backend was invoked.\n"
            "\n"
            f"Model requested: {model}\n"
            f"Prompt length: {len(prompt)} characters\n"
            f"Working dir: {cwd}\n"
            f"Commit SHA: {commit_sha}\n"
            "\n"
            "To get the real report, drop --stub-llm and ensure the configured "
            "agent backend is reachable."
        )
        return AgentResult(output=body, exit_code=0, duration_s=0.0, model_used=model)


class ActionFactory:
    def __init__(
        self,
        *,
        agents: dict[str, AgentRunner],
        default_agent: str,
        renderer: PromptRenderer,
        writer: FieldWriter,
        poster: CommentPoster,
        agent_timeout_seconds: float = 300.0,
    ) -> None:
        if default_agent not in agents:
            raise ValueError(
                f"default_agent {default_agent!r} not in agent registry: {sorted(agents)}"
            )
        self._agents = agents
        self._default_agent = default_agent
        self._renderer = renderer
        self._writer = writer
        self._poster = poster
        self._timeout_s = agent_timeout_seconds

    def materialize(self, spec: ActionSpec) -> ActionSpec:
        data = spec.model_dump()
        match spec.type:
            case "ai_report":
                name = data.get("agent") or self._default_agent
                runner = self._agents.get(name)
                if runner is None:
                    raise ValueError(
                        f"ai_report action {spec.id!r} requests agent {name!r}, "
                        f"not in registry: {sorted(self._agents)}"
                    )
                return AiReportAction(
                    **data,
                    runner=runner,
                    renderer=self._renderer,
                    timeout_s=self._timeout_s,
                )
            case "set_field":
                return SetFieldAction(**data, writer=self._writer)
            case "yt_comment":
                return YtCommentAction(**data, poster=self._poster)
            case _:
                return spec

    def materialize_workflow(self, wf: Workflow) -> Workflow:
        return wf.model_copy(
            update={
                "actions": [self.materialize(a) for a in wf.actions],
                "on_success": [self.materialize(a) for a in wf.on_success],
                "on_failure": [self.materialize(a) for a in wf.on_failure],
            }
        )
