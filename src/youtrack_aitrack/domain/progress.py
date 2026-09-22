"""Progress events emitted while a workflow run executes.

Pure domain vocabulary: the engine emits these as actions move through the
graph; an injected callback (supplied by the runtime/CLI) renders them. The
engine never imports a renderer — it only calls the callback if one is given.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Literal

from pydantic import BaseModel, ConfigDict

ProgressPhase = Literal["queued", "started", "finished"]
ActionOutcome = Literal["ok", "fail", "skipped"]


class ProgressEvent(BaseModel):
    workflow_name: str
    action_id: str
    phase: ProgressPhase
    is_hook: bool = False
    outcome: ActionOutcome | None = None
    duration_ms: int | None = None

    model_config = ConfigDict(frozen=True)


ProgressCallback = Callable[[ProgressEvent], None]

SkipReason = Literal["trigger_mismatch", "already_dispatched"]


class WorkflowSkipped(BaseModel):
    """Why the engine did not run a workflow for an event.

    ``trigger_mismatch``: the trigger rejected the event. ``already_dispatched``:
    the idempotency store had already seen this (workflow, issue, state, commit).
    Emitted so the CLI can tell the two apart instead of one opaque "no match".
    """

    workflow_name: str
    reason: SkipReason
    idempotency_key: str | None = None

    model_config = ConfigDict(frozen=True)


SkipCallback = Callable[[WorkflowSkipped], None]
