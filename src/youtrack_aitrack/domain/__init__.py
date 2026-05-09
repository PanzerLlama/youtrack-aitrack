"""Pure domain types for the workflow engine."""

from youtrack_aitrack.domain.action import ActionSpec
from youtrack_aitrack.domain.context import Context
from youtrack_aitrack.domain.event import EventKind, IssueEvent
from youtrack_aitrack.domain.output import (
    CommentOutput,
    CustomFieldOutput,
    OutputSpec,
)
from youtrack_aitrack.domain.run import ActionResult, RunState
from youtrack_aitrack.domain.trigger import TriggerSpec
from youtrack_aitrack.domain.workflow import Workflow

__all__ = [
    "ActionResult",
    "ActionSpec",
    "CommentOutput",
    "Context",
    "CustomFieldOutput",
    "EventKind",
    "IssueEvent",
    "OutputSpec",
    "RunState",
    "TriggerSpec",
    "Workflow",
]
