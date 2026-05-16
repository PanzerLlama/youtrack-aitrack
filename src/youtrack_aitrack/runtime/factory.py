"""ActionFactory — rebuild ActionSpec instances with concrete adapter dependencies."""

from __future__ import annotations

from youtrack_aitrack.domain.action import ActionSpec
from youtrack_aitrack.domain.actions.ai_report import AiReportAction, LLMClient, PromptRenderer
from youtrack_aitrack.domain.actions.set_field import FieldWriter, SetFieldAction
from youtrack_aitrack.domain.actions.yt_comment import CommentPoster, YtCommentAction
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


class StubLLMClient:
    """Cost-free LLMClient — returns a marked placeholder instead of calling Anthropic.

    Used by --stub-llm to smoke-test the trigger -> dispatch -> action path without
    spending tokens. Output includes the requested model and rendered prompt length so
    users can verify their wiring (model config flowed through; prompt rendered to
    non-empty content).
    """

    async def complete(self, prompt: str, model: str) -> str:
        return (
            "[STUB LLM] action stub — no real Anthropic call was made.\n"
            "\n"
            f"Model requested: {model}\n"
            f"Prompt length: {len(prompt)} characters\n"
            "\n"
            "To get the real report, drop --stub-llm and ensure ANTHROPIC_API_KEY is set."
        )


class ActionFactory:
    def __init__(
        self,
        *,
        llm: LLMClient,
        renderer: PromptRenderer,
        writer: FieldWriter,
        poster: CommentPoster,
    ) -> None:
        self._llm = llm
        self._renderer = renderer
        self._writer = writer
        self._poster = poster

    def materialize(self, spec: ActionSpec) -> ActionSpec:
        data = spec.model_dump()
        match spec.type:
            case "ai_report":
                return AiReportAction(**data, llm=self._llm, renderer=self._renderer)
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
