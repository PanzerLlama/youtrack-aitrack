"""Workflow run lifecycle primitives."""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict


class RunState(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"


class ActionResult(BaseModel):
    action_id: str
    success: bool
    output: dict[str, Any] | None = None
    error: str | None = None
    duration_ms: int | None = None

    model_config = ConfigDict(frozen=True)
