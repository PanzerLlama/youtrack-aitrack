"""Tests for ActionFactory — adapter injection into materialized actions."""

from __future__ import annotations

from typing import cast

from youtrack_aitrack.domain.actions.ai_report import AiReportAction
from youtrack_aitrack.domain.actions.set_field import SetFieldAction
from youtrack_aitrack.domain.actions.yt_comment import YtCommentAction
from youtrack_aitrack.domain.context import Context
from youtrack_aitrack.domain.triggers.manual import ManualTrigger
from youtrack_aitrack.domain.workflow import Workflow
from youtrack_aitrack.runtime.factory import ActionFactory


class _FakeLLM:
    async def complete(self, prompt: str, model: str) -> str:
        return f"llm[{model}]:{prompt}"


class _FakeRenderer:
    def render(self, template: str, ctx: Context) -> str:
        return f"rendered:{template}"


class _FakeWriter:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, str]]] = []

    async def set_fields(self, issue_id: str, fields: dict[str, str]) -> None:
        self.calls.append((issue_id, fields))


class _FakePoster:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    async def post_comment(self, issue_id: str, body: str) -> None:
        self.calls.append((issue_id, body))


def _factory(
    *,
    writer: _FakeWriter | None = None,
    poster: _FakePoster | None = None,
) -> ActionFactory:
    return ActionFactory(
        llm=_FakeLLM(),
        renderer=_FakeRenderer(),
        writer=writer or _FakeWriter(),
        poster=poster or _FakePoster(),
    )


def test_materialize_ai_report_injects_llm_and_renderer() -> None:
    spec = AiReportAction(id="a", prompt="security_audit.md", model="claude-sonnet-4-6")
    materialized = _factory().materialize(spec)
    assert isinstance(materialized, AiReportAction)
    assert materialized.prompt == "security_audit.md"
    assert materialized.model == "claude-sonnet-4-6"
    assert isinstance(cast(AiReportAction, materialized)._llm, _FakeLLM)
    assert isinstance(cast(AiReportAction, materialized)._renderer, _FakeRenderer)


def test_materialize_set_field_injects_writer() -> None:
    writer = _FakeWriter()
    spec = SetFieldAction(id="s", fields={"Status": "done"})
    materialized = _factory(writer=writer).materialize(spec)
    assert isinstance(materialized, SetFieldAction)
    assert materialized.fields == {"Status": "done"}
    assert cast(SetFieldAction, materialized)._writer is writer


def test_materialize_yt_comment_injects_poster() -> None:
    poster = _FakePoster()
    spec = YtCommentAction(id="c", body="hello")
    materialized = _factory(poster=poster).materialize(spec)
    assert isinstance(materialized, YtCommentAction)
    assert materialized.body == "hello"
    assert cast(YtCommentAction, materialized)._poster is poster


def test_materialize_workflow_rewires_all_action_groups() -> None:
    writer = _FakeWriter()
    poster = _FakePoster()
    wf = Workflow(
        name="wf",
        trigger=ManualTrigger(),
        actions=[
            AiReportAction(id="a", prompt="p.md", model="m"),
            SetFieldAction(id="s", fields={"X": "1"}),
        ],
        on_success=[YtCommentAction(id="ok", body="done")],
        on_failure=[SetFieldAction(id="bad", fields={"Status": "failed"})],
    )

    rewired = _factory(writer=writer, poster=poster).materialize_workflow(wf)

    ai = cast(AiReportAction, rewired.actions[0])
    sf = cast(SetFieldAction, rewired.actions[1])
    ok = cast(YtCommentAction, rewired.on_success[0])
    bad = cast(SetFieldAction, rewired.on_failure[0])
    assert isinstance(ai._llm, _FakeLLM)
    assert sf._writer is writer
    assert ok._poster is poster
    assert bad._writer is writer
    assert rewired.name == "wf"
    assert [a.id for a in rewired.actions] == ["a", "s"]
