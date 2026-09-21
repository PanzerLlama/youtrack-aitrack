"""BdIssueAction — persist an upstream text output as a beads issue in the target repo.

Beads (``bd``) is optional tooling, so availability is decided here, deterministically
(binary on PATH and a ``.beads/`` workspace in the repo), never by the agent. When
beads is unavailable the plan is written to ``fallback_path`` instead, or the action
skips itself when no fallback is configured.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Literal, Protocol

from pydantic import BaseModel, ConfigDict, PrivateAttr

from youtrack_aitrack.domain.action import ActionSpec
from youtrack_aitrack.domain.actions.write_file import (
    NoOpRepoFileWriter,
    RepoFileWriter,
    safe_relative_path,
)
from youtrack_aitrack.domain.context import Context
from youtrack_aitrack.domain.run import ActionResult
from youtrack_aitrack.registry import register_action

_UNAVAILABLE_NO_FALLBACK = (
    "beads unavailable (bd not on PATH or no .beads/ in repo); no fallback_path configured"
)


class TrackedIssue(BaseModel):
    title: str
    body: str
    issue_type: str = "task"
    priority: int = 2
    external_ref: str | None = None

    model_config = ConfigDict(frozen=True)


class IssueTrackerClient(Protocol):
    def is_available(self, repo_dir: Path) -> bool: ...

    def create_issue(self, repo_dir: Path, issue: TrackedIssue) -> str: ...


class _NoOpIssueTracker:
    def is_available(self, repo_dir: Path) -> bool:
        return False

    def create_issue(self, repo_dir: Path, issue: TrackedIssue) -> str:
        return ""


@register_action("bd_issue")
class BdIssueAction(ActionSpec):
    type: Literal["bd_issue"] = "bd_issue"
    source: str
    title: str = "{task_id}: {summary}"
    issue_type: str = "task"
    priority: int = 2
    external_ref: str | None = "{task_id}"
    fallback_path: str | None = None
    fallback_commit_message: str | None = None

    _tracker: IssueTrackerClient = PrivateAttr()
    _writer: RepoFileWriter = PrivateAttr()

    def __init__(
        self,
        *,
        tracker: IssueTrackerClient | None = None,
        writer: RepoFileWriter | None = None,
        **data: Any,
    ) -> None:
        super().__init__(**data)
        self._tracker = tracker if tracker is not None else _NoOpIssueTracker()
        self._writer = writer if writer is not None else NoOpRepoFileWriter()

    async def execute(self, ctx: Context) -> ActionResult:
        text = _source_text(ctx, self.source)
        if text is None:
            return ActionResult(
                action_id=self.id,
                success=False,
                error=f"source action {self.source!r} produced no text output",
            )
        repo = ctx.repo_path if ctx.repo_path is not None else Path(".")
        if self._tracker.is_available(repo):
            return self._track(ctx, repo, text)
        if self.fallback_path is not None:
            return self._fallback(ctx, repo, text)
        return ActionResult(
            action_id=self.id,
            success=True,
            skipped=True,
            skip_reason=_UNAVAILABLE_NO_FALLBACK,
        )

    def _track(self, ctx: Context, repo: Path, text: str) -> ActionResult:
        issue = TrackedIssue(
            title=_fill(self.title, ctx).strip(" :-"),
            body=text,
            issue_type=self.issue_type,
            priority=self.priority,
            external_ref=_fill(self.external_ref, ctx) if self.external_ref else None,
        )
        issue_id = self._tracker.create_issue(repo, issue)
        return ActionResult(
            action_id=self.id,
            success=True,
            output={
                "tracker": "beads",
                "issue_id": issue_id,
                "note": f"created beads issue {issue_id}",
                "text": f"Implementation plan tracked in beads as {issue_id}.",
            },
        )

    def _fallback(self, ctx: Context, repo: Path, text: str) -> ActionResult:
        assert self.fallback_path is not None
        try:
            rel = safe_relative_path(_fill(self.fallback_path, ctx))
        except ValueError as exc:
            return ActionResult(action_id=self.id, success=False, error=str(exc))
        self._writer.write_text(repo, rel, text)
        sha: str | None = None
        if self.fallback_commit_message is not None:
            sha = self._writer.commit_paths(repo, [rel], _fill(self.fallback_commit_message, ctx))
        note = f"beads unavailable; wrote {rel}" + (f"; committed {sha[:10]}" if sha else "")
        return ActionResult(
            action_id=self.id,
            success=True,
            output={
                "tracker": "file",
                "path": str(rel),
                "committed_sha": sha,
                "note": note,
                "text": f"Implementation plan saved to {rel} on the branch.",
            },
        )


def _fill(template: str, ctx: Context) -> str:
    summary = ctx.issue_details.summary if ctx.issue_details is not None else ""
    return template.replace("{task_id}", ctx.issue.issue_id).replace("{summary}", summary)


def _source_text(ctx: Context, source: str) -> str | None:
    result = ctx.action_outputs.get(source)
    if result is None or result.output is None:
        return None
    text = result.output.get("text")
    return text if isinstance(text, str) else None
