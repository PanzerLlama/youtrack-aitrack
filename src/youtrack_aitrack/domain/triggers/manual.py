"""Manual trigger — fires only on explicit CLI run command."""

from __future__ import annotations

from typing import Literal

from youtrack_aitrack.domain.event import IssueEvent
from youtrack_aitrack.domain.trigger import TriggerSpec
from youtrack_aitrack.registry import register_trigger


@register_trigger("manual")
class ManualTrigger(TriggerSpec):
    type: Literal["manual"] = "manual"

    def matches(self, event: IssueEvent) -> bool:
        return event.event_kind == "manual"
