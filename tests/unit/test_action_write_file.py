"""Tests for WriteFileAction against a recording RepoFileWriter fake."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path, PurePosixPath

import pytest

import youtrack_aitrack.domain.actions  # noqa: F401
from youtrack_aitrack.domain.actions.write_file import RepoFileWriter, WriteFileAction
from youtrack_aitrack.domain.context import Context
from youtrack_aitrack.domain.event import IssueEvent
from youtrack_aitrack.domain.run import ActionResult
from youtrack_aitrack.registry import action_registry


class _FakeWriter:
    def __init__(self) -> None:
        self.written: list[tuple[Path, PurePosixPath, str]] = []
        self.commits: list[tuple[Path, list[PurePosixPath], str]] = []

    def write_text(self, repo_dir: Path, relative_path: PurePosixPath, text: str) -> None:
        self.written.append((repo_dir, relative_path, text))

    def commit_paths(self, repo_dir: Path, paths: list[PurePosixPath], message: str) -> str:
        self.commits.append((repo_dir, paths, message))
        return "abcdef1234567890"


def _accepts(w: RepoFileWriter) -> RepoFileWriter:
    return w


def _ctx(outputs: dict[str, ActionResult] | None = None) -> Context:
    event = IssueEvent(
        issue_id="PROJ-12",
        project="PROJ",
        event_kind="manual",
        timestamp=datetime(2026, 9, 21, tzinfo=UTC),
    )
    default = {"plan": ActionResult(action_id="plan", success=True, output={"text": "# Plan\n"})}
    return Context(
        issue=event,
        repo_path=Path("/repo"),
        action_outputs=outputs if outputs is not None else default,
    )


def test_registered_and_fake_satisfies_protocol() -> None:
    assert action_registry.get("write_file") is WriteFileAction
    w = _FakeWriter()
    assert _accepts(w) is w


@pytest.mark.asyncio
async def test_writes_source_text_to_templated_path_without_commit() -> None:
    w = _FakeWriter()
    action = WriteFileAction(id="save", source="plan", path="docs/plans/{task_id}.md", writer=w)

    result = await action.execute(_ctx())

    assert result.success is True
    assert w.written == [(Path("/repo"), PurePosixPath("docs/plans/PROJ-12.md"), "# Plan\n")]
    assert w.commits == []
    assert result.output == {
        "path": "docs/plans/PROJ-12.md",
        "committed_sha": None,
        "note": "wrote docs/plans/PROJ-12.md",
    }


@pytest.mark.asyncio
async def test_commits_when_message_given() -> None:
    w = _FakeWriter()
    action = WriteFileAction(
        id="save",
        source="plan",
        path="docs/plans/{task_id}.md",
        commit_message="docs: plan for {task_id}",
        writer=w,
    )

    result = await action.execute(_ctx())

    assert result.success is True
    assert w.commits == [
        (Path("/repo"), [PurePosixPath("docs/plans/PROJ-12.md")], "docs: plan for PROJ-12")
    ]
    assert result.output is not None
    assert result.output["committed_sha"] == "abcdef1234567890"
    assert result.output["note"] == "wrote docs/plans/PROJ-12.md; committed abcdef1234"


@pytest.mark.asyncio
async def test_fails_when_source_has_no_text() -> None:
    w = _FakeWriter()
    action = WriteFileAction(id="save", source="plan", path="x.md", writer=w)
    outputs = {"plan": ActionResult(action_id="plan", success=True, output={"fields": {}})}

    result = await action.execute(_ctx(outputs))

    assert result.success is False
    assert result.error is not None
    assert "no text output" in result.error
    assert w.written == []


@pytest.mark.asyncio
async def test_fails_when_source_missing() -> None:
    action = WriteFileAction(id="save", source="nope", path="x.md", writer=_FakeWriter())
    result = await action.execute(_ctx())
    assert result.success is False


@pytest.mark.parametrize("bad", ["/etc/passwd", "../outside.md", "docs/../../x.md", ""])
@pytest.mark.asyncio
async def test_rejects_paths_escaping_repo(bad: str) -> None:
    w = _FakeWriter()
    action = WriteFileAction(id="save", source="plan", path=bad, writer=w)

    result = await action.execute(_ctx())

    assert result.success is False
    assert result.error is not None
    assert "inside the repo" in result.error
    assert w.written == []


@pytest.mark.asyncio
async def test_default_noop_writer_succeeds_without_io() -> None:
    result = await WriteFileAction(id="save", source="plan", path="x.md").execute(_ctx())
    assert result.success is True
