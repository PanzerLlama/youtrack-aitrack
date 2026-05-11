"""IssueEvent — incoming event from YouTrack (or fabricated for manual runs)."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

EventKind = Literal["status_change", "field_change", "manual"]

STATE_FIELD_NAME = "State"
"""Canonical YouTrack field name for state transitions in the activities feed."""


class IssueEvent(BaseModel):
    issue_id: str
    project: str
    event_kind: EventKind
    from_state: str | None = None
    to_state: str | None = None
    field_name: str | None = None
    from_value: str | None = None
    to_value: str | None = None
    actor: str | None = None
    timestamp: datetime
    raw: dict[str, Any] = Field(default_factory=dict)

    model_config = ConfigDict(frozen=True)
