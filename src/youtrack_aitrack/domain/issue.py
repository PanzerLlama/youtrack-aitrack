"""IssueDetails — the issue's own content (summary, description, state) as fetched from YouTrack.

Distinct from :class:`IssueEvent`, which describes *what happened* to an issue;
IssueDetails describes *what the issue says*. Actions that reason about the
task itself (planning, branch naming) read this; audit actions read the diff.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class IssueDetails(BaseModel):
    summary: str
    description: str | None = None
    state: str | None = None

    model_config = ConfigDict(frozen=True)
