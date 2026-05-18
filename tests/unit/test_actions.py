"""Tests for ai_report, yt_comment, set_field action stubs."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

# Importing the package executes the @register_action decorators.
import youtrack_aitrack.domain.actions  # noqa: F401
from youtrack_aitrack.domain.actions.ai_report import AiReportAction
from youtrack_aitrack.domain.actions.set_field import SetFieldAction
from youtrack_aitrack.domain.actions.yt_comment import YtCommentAction
from youtrack_aitrack.domain.agent_runner import AgentResult, AgentRunnerError
from youtrack_aitrack.domain.context import Context
from youtrack_aitrack.domain.event import IssueEvent
from youtrack_aitrack.registry import action_registry


def _ctx(*, commit_sha: str | None = None, repo_path: Path | None = None) -> Context:
    return Context(
        issue=IssueEvent(
            issue_id="DEMO-1",
            project="DEMO",
            event_kind="manual",
            timestamp=datetime(2026, 5, 9, tzinfo=UTC),
        ),
        commit_sha=commit_sha,
        repo_path=repo_path,
    )


# --- Registration ---


def test_ai_report_registered() -> None:
    assert action_registry.get("ai_report") is AiReportAction


def test_yt_comment_registered() -> None:
    assert action_registry.get("yt_comment") is YtCommentAction


def test_set_field_registered() -> None:
    assert action_registry.get("set_field") is SetFieldAction


# --- AiReportAction ---


class _RecordingAgentRunner:
    def __init__(self, *, raise_on_run: AgentRunnerError | None = None) -> None:
        self.calls: list[dict[str, object]] = []
        self._raise = raise_on_run

    async def run(
        self,
        prompt: str,
        *,
        cwd: Path,
        commit_sha: str | None,
        timeout_s: float,
        model: str | None = None,
    ) -> AgentResult:
        self.calls.append(
            {
                "prompt": prompt,
                "cwd": cwd,
                "commit_sha": commit_sha,
                "timeout_s": timeout_s,
                "model": model,
            }
        )
        if self._raise is not None:
            raise self._raise
        return AgentResult(output="stub-output", exit_code=0, duration_s=0.0, model_used=model)


class _RecordingRenderer:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def render(self, template: str, ctx: Context) -> str:
        self.calls.append(template)
        return f"rendered::{template}"


@pytest.mark.asyncio
async def test_ai_report_default_stubs_are_no_op() -> None:
    a = AiReportAction(id="a1", prompt="hello", model="claude-sonnet-4-6")
    result = await a.execute(_ctx())
    assert result.success is True
    assert result.action_id == "a1"
    assert result.output == {"text": "", "model": "claude-sonnet-4-6"}


@pytest.mark.asyncio
async def test_ai_report_uses_injected_runner_and_renderer() -> None:
    runner = _RecordingAgentRunner()
    renderer = _RecordingRenderer()
    a = AiReportAction(
        id="a1",
        prompt="security",
        model="claude-sonnet-4-6",
        runner=runner,
        renderer=renderer,
    )
    result = await a.execute(_ctx())
    assert renderer.calls == ["security"]
    assert runner.calls[0]["prompt"] == "rendered::security"
    assert runner.calls[0]["model"] == "claude-sonnet-4-6"
    assert result.output == {"text": "stub-output", "model": "claude-sonnet-4-6"}


@pytest.mark.asyncio
async def test_ai_report_threads_repo_path_and_commit_sha_from_context() -> None:
    runner = _RecordingAgentRunner()
    a = AiReportAction(id="a1", prompt="p", model="m", runner=runner)
    await a.execute(_ctx(commit_sha="deadbeef", repo_path=Path("/tmp/repo")))
    assert runner.calls[0]["cwd"] == Path("/tmp/repo")
    assert runner.calls[0]["commit_sha"] == "deadbeef"


@pytest.mark.asyncio
async def test_ai_report_passes_configured_timeout_to_runner() -> None:
    runner = _RecordingAgentRunner()
    a = AiReportAction(id="a1", prompt="p", model="m", runner=runner, timeout_s=45.0)
    await a.execute(_ctx())
    assert runner.calls[0]["timeout_s"] == 45.0


@pytest.mark.asyncio
async def test_ai_report_falls_back_to_current_dir_when_repo_path_unset() -> None:
    runner = _RecordingAgentRunner()
    a = AiReportAction(id="a1", prompt="p", model="m", runner=runner)
    await a.execute(_ctx())  # repo_path None
    assert runner.calls[0]["cwd"] == Path(".")


@pytest.mark.asyncio
async def test_ai_report_returns_failure_action_result_on_agent_runner_error() -> None:
    runner = _RecordingAgentRunner(raise_on_run=AgentRunnerError("backend died"))
    a = AiReportAction(id="a1", prompt="p", model="m", runner=runner)
    result = await a.execute(_ctx())
    assert result.success is False
    assert result.error is not None and "backend died" in result.error


def test_ai_report_agent_defaults_to_none() -> None:
    a = AiReportAction(id="a1", prompt="p", model="m")
    assert a.agent is None


def test_ai_report_accepts_agent_backend_name() -> None:
    a = AiReportAction(id="a1", prompt="p", model="m", agent="claude_code_cli")
    assert a.agent == "claude_code_cli"


@pytest.mark.asyncio
async def test_ai_report_agent_field_does_not_alter_execute() -> None:
    runner = _RecordingAgentRunner()
    a = AiReportAction(
        id="a1",
        prompt="p",
        model="m",
        agent="claude_code_cli",
        runner=runner,
    )
    result = await a.execute(_ctx())
    assert runner.calls[0]["prompt"] == "p"
    assert result.output == {"text": "stub-output", "model": "m"}


# --- YtCommentAction ---


class _RecordingPoster:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    async def post_comment(self, issue_id: str, body: str) -> None:
        self.calls.append((issue_id, body))


@pytest.mark.asyncio
async def test_yt_comment_default_stub_is_no_op() -> None:
    a = YtCommentAction(id="c1", body="hi")
    result = await a.execute(_ctx())
    assert result.success is True
    assert result.output == {"issue_id": "DEMO-1", "body": "hi"}


@pytest.mark.asyncio
async def test_yt_comment_uses_injected_poster() -> None:
    poster = _RecordingPoster()
    a = YtCommentAction(id="c1", body="hi", poster=poster)
    await a.execute(_ctx())
    assert poster.calls == [("DEMO-1", "hi")]


# --- SetFieldAction ---


class _RecordingWriter:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, str]]] = []

    async def set_fields(self, issue_id: str, fields: dict[str, str]) -> None:
        self.calls.append((issue_id, fields))


@pytest.mark.asyncio
async def test_set_field_default_stub_is_no_op() -> None:
    a = SetFieldAction(id="s1", fields={"Audit Status": "done"})
    result = await a.execute(_ctx())
    assert result.success is True
    assert result.output == {"issue_id": "DEMO-1", "fields": {"Audit Status": "done"}}


@pytest.mark.asyncio
async def test_set_field_uses_injected_writer() -> None:
    writer = _RecordingWriter()
    a = SetFieldAction(id="s1", fields={"Audit Status": "done"}, writer=writer)
    await a.execute(_ctx())
    assert writer.calls == [("DEMO-1", {"Audit Status": "done"})]
