"""Workflow run lifecycle primitives."""

from __future__ import annotations

from enum import StrEnum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field


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


class RunReport(BaseModel):
    run_id: str = Field(default_factory=lambda: uuid4().hex)
    workflow_name: str
    state: RunState
    action_results: list[ActionResult] = Field(default_factory=list)
    hook_results: list[ActionResult] = Field(default_factory=list)

    model_config = ConfigDict(frozen=True)
