"""Context — immutable execution context passed to actions during a run."""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from youtrack_aitrack.domain.event import IssueEvent
from youtrack_aitrack.domain.issue import IssueDetails
from youtrack_aitrack.domain.run import ActionResult


class Context(BaseModel):
    issue: IssueEvent
    issue_details: IssueDetails | None = None
    branch: str | None = None
    diff: str | None = None
    base_url: str | None = None
    commit_sha: str | None = None
    repo_path: Path | None = None
    action_outputs: dict[str, ActionResult] = Field(default_factory=dict)

    model_config = ConfigDict(frozen=True)
