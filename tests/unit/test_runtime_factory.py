"""Tests for ActionFactory — adapter injection into materialized actions."""

from __future__ import annotations

from pathlib import Path
from typing import cast

import pytest

from youtrack_aitrack.domain.actions.ai_report import AiReportAction
from youtrack_aitrack.domain.actions.set_field import SetFieldAction
from youtrack_aitrack.domain.actions.yt_comment import YtCommentAction
from youtrack_aitrack.domain.agent_runner import AgentResult, AgentRunner
from youtrack_aitrack.domain.context import Context
from youtrack_aitrack.domain.output import CommentOutput, CustomFieldOutput
from youtrack_aitrack.domain.triggers.manual import ManualTrigger
from youtrack_aitrack.domain.workflow import Workflow
from youtrack_aitrack.runtime.factory import (
    ActionFactory,
    StandardOutputSink,
    StubAgentRunner,
)


class _FakeAgentRunner:
    def __init__(self, label: str = "fake") -> None:
        self.label = label

    async def run(
        self,
        prompt: str,
        *,
        cwd: Path,
        commit_sha: str | None,
        timeout_s: float,
        model: str | None = None,
    ) -> AgentResult:
        return AgentResult(
            output=f"{self.label}[{model}]:{prompt}",
            exit_code=0,
            duration_s=0.0,
            model_used=model,
        )


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
    agents: dict[str, AgentRunner] | None = None,
    default_agent: str = "anthropic_api",
    agent_timeout_seconds: float = 300.0,
) -> ActionFactory:
    return ActionFactory(
        agents=agents or {"anthropic_api": _FakeAgentRunner("anthropic")},
        default_agent=default_agent,
        renderer=_FakeRenderer(),
        writer=writer or _FakeWriter(),
        poster=poster or _FakePoster(),
        agent_timeout_seconds=agent_timeout_seconds,
    )


def test_materialize_ai_report_injects_runner_and_renderer() -> None:
    spec = AiReportAction(id="a", prompt="security_audit.md", model="claude-sonnet-4-6")
    runner = _FakeAgentRunner("anthropic")
    materialized = _factory(agents={"anthropic_api": runner}).materialize(spec)
    assert isinstance(materialized, AiReportAction)
    assert materialized.prompt == "security_audit.md"
    assert materialized.model == "claude-sonnet-4-6"
    assert cast(AiReportAction, materialized)._runner is runner
    assert isinstance(cast(AiReportAction, materialized)._renderer, _FakeRenderer)


def test_materialize_ai_report_routes_to_named_agent_when_set() -> None:
    spec = AiReportAction(id="a", prompt="p.md", model="m", agent="claude_code_cli")
    cli_runner = _FakeAgentRunner("cli")
    sdk_runner = _FakeAgentRunner("sdk")
    materialized = _factory(
        agents={"anthropic_api": sdk_runner, "claude_code_cli": cli_runner}
    ).materialize(spec)
    assert cast(AiReportAction, materialized)._runner is cli_runner


def test_materialize_ai_report_uses_default_agent_when_unset() -> None:
    spec = AiReportAction(id="a", prompt="p.md", model="m")  # agent None
    cli_runner = _FakeAgentRunner("cli")
    sdk_runner = _FakeAgentRunner("sdk")
    materialized = _factory(
        agents={"anthropic_api": sdk_runner, "claude_code_cli": cli_runner},
        default_agent="anthropic_api",
    ).materialize(spec)
    assert cast(AiReportAction, materialized)._runner is sdk_runner


def test_materialize_ai_report_raises_for_unknown_agent() -> None:
    spec = AiReportAction(id="a", prompt="p.md", model="m", agent="nonexistent_cli")
    with pytest.raises(ValueError, match="nonexistent_cli"):
        _factory().materialize(spec)


def test_factory_rejects_default_agent_not_in_registry() -> None:
    with pytest.raises(ValueError, match="default_agent 'codex_cli'"):
        ActionFactory(
            agents={"anthropic_api": _FakeAgentRunner()},
            default_agent="codex_cli",
            renderer=_FakeRenderer(),
            writer=_FakeWriter(),
            poster=_FakePoster(),
        )


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
    runner = _FakeAgentRunner("anthropic")
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

    rewired = _factory(
        writer=writer, poster=poster, agents={"anthropic_api": runner}
    ).materialize_workflow(wf)

    ai = cast(AiReportAction, rewired.actions[0])
    sf = cast(SetFieldAction, rewired.actions[1])
    ok = cast(YtCommentAction, rewired.on_success[0])
    bad = cast(SetFieldAction, rewired.on_failure[0])
    assert ai._runner is runner
    assert sf._writer is writer
    assert ok._poster is poster
    assert bad._writer is writer
    assert rewired.name == "wf"
    assert [a.id for a in rewired.actions] == ["a", "s"]


async def test_stub_agent_returns_marked_placeholder_with_request_fields() -> None:
    stub = StubAgentRunner()
    result = await stub.run(
        "hello world",
        cwd=Path("/tmp/x"),
        commit_sha="abc123",
        timeout_s=30.0,
        model="claude-sonnet-4-6",
    )

    assert "[STUB AGENT]" in result.output
    assert "claude-sonnet-4-6" in result.output
    assert "Prompt length: 11" in result.output
    assert "abc123" in result.output
    assert "/tmp/x" in result.output
    assert "--stub-llm" in result.output  # tells user how to disable
    assert result.exit_code == 0
    assert result.model_used == "claude-sonnet-4-6"


async def test_stub_agent_is_deterministic() -> None:
    stub = StubAgentRunner()
    a = await stub.run("x", cwd=Path("/"), commit_sha=None, timeout_s=1.0, model="m")
    b = await stub.run("x", cwd=Path("/"), commit_sha=None, timeout_s=1.0, model="m")
    assert a.output == b.output


async def test_standard_output_sink_custom_field_writes_via_field_writer() -> None:
    writer = _FakeWriter()
    poster = _FakePoster()
    sink = StandardOutputSink(writer=writer, poster=poster)

    await sink.write(
        issue_id="DEMO-1",
        spec=CustomFieldOutput(name="Security Audit"),
        value="audit body",
    )

    assert writer.calls == [("DEMO-1", {"Security Audit": "audit body"})]
    assert poster.calls == []


async def test_standard_output_sink_comment_writes_via_comment_poster() -> None:
    writer = _FakeWriter()
    poster = _FakePoster()
    sink = StandardOutputSink(writer=writer, poster=poster)

    await sink.write(
        issue_id="DEMO-1",
        spec=CommentOutput(),
        value="comment body",
    )

    assert poster.calls == [("DEMO-1", "comment body")]
    assert writer.calls == []
