"""Tests for Poller — cursor round-trip + bounded loop."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from pathlib import Path

from youtrack_aitrack.config.instance import (
    AnthropicSection,
    DefaultsSection,
    InstanceConfig,
    PathsSection,
    YouTrackSection,
)
from youtrack_aitrack.domain.actions.set_field import SetFieldAction
from youtrack_aitrack.domain.event import IssueEvent
from youtrack_aitrack.domain.run import RunReport
from youtrack_aitrack.domain.triggers.status_change import StatusChangeTrigger
from youtrack_aitrack.domain.workflow import Workflow
from youtrack_aitrack.engine import WorkflowEngine
from youtrack_aitrack.runtime.factory import ActionFactory
from youtrack_aitrack.runtime.poller import Poller, PollResult
from youtrack_aitrack.runtime.runner import Runner


class _FakeFeed:
    def __init__(self, batches: list[tuple[list[IssueEvent], str | None]]) -> None:
        self._batches = list(batches)
        self.calls: list[str | None] = []

    async def changed_issues_since(self, cursor: str | None) -> tuple[list[IssueEvent], str | None]:
        self.calls.append(cursor)
        if not self._batches:
            return [], cursor
        return self._batches.pop(0)


class _FakeGit:
    def resolve_branch(self, task_id: str, *, repo_dir: Path, pattern: str) -> str | None:
        return None

    def diff(self, repo_dir: Path, branch: str, base: str = "main") -> str:
        return ""

    def commit_sha(self, repo_dir: Path, branch: str) -> str:
        return ""


class _FakeStateLookup:
    async def get_issue_state(self, issue_id: str) -> str | None:
        return None


class _FakeWriter:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, str]]] = []

    async def set_fields(self, issue_id: str, fields: dict[str, str]) -> None:
        self.calls.append((issue_id, fields))


class _FakePoster:
    async def post_comment(self, issue_id: str, body: str) -> None:
        return None


class _FakeLLM:
    async def complete(self, prompt: str, model: str) -> str:
        return ""


class _FakeRenderer:
    def render(self, template: str, ctx: object) -> str:
        return template


class _RunStore:
    def __init__(self) -> None:
        self.saved_runs: list[RunReport] = []
        self._cursor: str | None = None
        self.cursor_history: list[str | None] = []
        self._idem: dict[str, str] = {}

    def save_run(self, report: RunReport) -> None:
        self.saved_runs.append(report)

    def load_run(self, run_id: str) -> RunReport | None:
        return None

    def save_cursor(self, token: str | None) -> None:
        self._cursor = token
        self.cursor_history.append(token)

    def load_cursor(self) -> str | None:
        return self._cursor

    def has_processed(self, key: str) -> bool:
        return key in self._idem

    def mark_processed(self, key: str, run_id: str) -> None:
        self._idem[key] = run_id


def _config() -> InstanceConfig:
    return InstanceConfig(
        youtrack=YouTrackSection(url="https://yt.example.com", token="t", project="DEMO"),
        anthropic=AnthropicSection(api_key="k"),
        paths=PathsSection(),
        defaults=DefaultsSection(branch_pattern="{task_id}-*", poll_interval_seconds=1),
    )


def _state_event(issue_id: str, to_state: str) -> IssueEvent:
    return IssueEvent(
        issue_id=issue_id,
        project="DEMO",
        event_kind="field_change",
        field_name="State",
        from_value="In progress",
        to_value=to_state,
        from_state="In progress",
        to_state=to_state,
        timestamp=datetime(2026, 5, 11, tzinfo=UTC),
    )


def _build_poller(
    feed: _FakeFeed,
    run_store: _RunStore,
    writer: _FakeWriter,
) -> Poller:
    wf = Workflow(
        name="audit",
        trigger=StatusChangeTrigger(to_state="Ready for testing"),
        actions=[SetFieldAction(id="mark", fields={"Status": "audited"})],
    )
    factory = ActionFactory(
        llm=_FakeLLM(), renderer=_FakeRenderer(), writer=writer, poster=_FakePoster()
    )
    workflows = [factory.materialize_workflow(wf)]
    runner = Runner(
        config=_config(),
        workflows=workflows,
        engine=WorkflowEngine(idempotency_store=run_store),
        git_provider=_FakeGit(),
        repo_dir=Path("/tmp/fakerepo"),
        run_store=run_store,
        state_lookup=_FakeStateLookup(),
    )
    return Poller(runner=runner, run_store=run_store, activity_feed=feed)


async def test_poll_once_dispatches_events_and_saves_cursor() -> None:
    events = [_state_event("DEMO-1", "Ready for testing"), _state_event("DEMO-2", "Done")]
    feed = _FakeFeed([(events, "cur-2")])
    run_store = _RunStore()
    writer = _FakeWriter()
    poller = _build_poller(feed, run_store, writer)

    result = await poller.poll_once()

    assert feed.calls == [None]
    assert run_store._cursor == "cur-2"
    assert result.cursor_before is None
    assert result.cursor_after == "cur-2"
    assert result.event_count == 2
    # Only the first event matches the trigger (to_state="Ready for testing").
    assert writer.calls == [("DEMO-1", {"Status": "audited"})]
    assert len(result.reports) == 1


async def test_poll_once_uses_existing_cursor() -> None:
    feed = _FakeFeed([([], "cur-x")])
    run_store = _RunStore()
    run_store.save_cursor("cur-prev")
    poller = _build_poller(feed, run_store, _FakeWriter())

    await poller.poll_once()

    assert feed.calls == ["cur-prev"]
    assert run_store._cursor == "cur-x"


async def test_poll_loop_runs_max_iterations_and_exits() -> None:
    feed = _FakeFeed([([], "c1"), ([], "c2"), ([], "c3")])
    run_store = _RunStore()
    poller = _build_poller(feed, run_store, _FakeWriter())
    stop = asyncio.Event()
    results: list[PollResult] = []

    iterations = await poller.poll_loop(
        interval_seconds=0.001,
        stop=stop,
        on_iteration=results.append,
        max_iterations=2,
    )

    assert iterations == 2
    assert run_store.cursor_history == ["c1", "c2"]
    assert len(results) == 2


async def test_poll_loop_stop_event_short_circuits() -> None:
    feed = _FakeFeed([([], "c1"), ([], "c2"), ([], "c3")])
    run_store = _RunStore()
    poller = _build_poller(feed, run_store, _FakeWriter())
    stop = asyncio.Event()
    stop.set()

    iterations = await poller.poll_loop(
        interval_seconds=0.001,
        stop=stop,
    )

    assert iterations == 0
