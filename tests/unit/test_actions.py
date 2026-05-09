"""Tests for ai_report, yt_comment, set_field action stubs."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

# Importing the package executes the @register_action decorators.
import youtrack_aitrack.domain.actions  # noqa: F401
from youtrack_aitrack.domain.actions.ai_report import AiReportAction
from youtrack_aitrack.domain.actions.set_field import SetFieldAction
from youtrack_aitrack.domain.actions.yt_comment import YtCommentAction
from youtrack_aitrack.domain.context import Context
from youtrack_aitrack.domain.event import IssueEvent
from youtrack_aitrack.registry import action_registry


def _ctx() -> Context:
    return Context(
        issue=IssueEvent(
            issue_id="DEMO-1",
            project="DEMO",
            event_kind="manual",
            timestamp=datetime(2026, 5, 9, tzinfo=UTC),
        )
    )


# --- Registration ---


def test_ai_report_registered() -> None:
    assert action_registry.get("ai_report") is AiReportAction


def test_yt_comment_registered() -> None:
    assert action_registry.get("yt_comment") is YtCommentAction


def test_set_field_registered() -> None:
    assert action_registry.get("set_field") is SetFieldAction


# --- AiReportAction ---


class _RecordingLLM:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    async def complete(self, prompt: str, model: str) -> str:
        self.calls.append((prompt, model))
        return "stub-output"


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
async def test_ai_report_uses_injected_llm_and_renderer() -> None:
    llm = _RecordingLLM()
    renderer = _RecordingRenderer()
    a = AiReportAction(
        id="a1",
        prompt="security",
        model="claude-sonnet-4-6",
        llm=llm,
        renderer=renderer,
    )
    result = await a.execute(_ctx())
    assert renderer.calls == ["security"]
    assert llm.calls == [("rendered::security", "claude-sonnet-4-6")]
    assert result.output == {"text": "stub-output", "model": "claude-sonnet-4-6"}


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
