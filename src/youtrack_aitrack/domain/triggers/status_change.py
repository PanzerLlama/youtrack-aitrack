"""StatusChangeTrigger — fires when an issue moves between states."""

from __future__ import annotations

from typing import Literal

from youtrack_aitrack.domain.event import IssueEvent
from youtrack_aitrack.domain.trigger import TriggerSpec
from youtrack_aitrack.registry import register_trigger


@register_trigger("status_change")
class StatusChangeTrigger(TriggerSpec):
    type: Literal["status_change"] = "status_change"
    from_state: str = "*"
    to_state: str

    def matches(self, event: IssueEvent) -> bool:
        if event.event_kind != "status_change":
            return False
        if self.from_state != "*" and event.from_state != self.from_state:
            return False
        return event.to_state == self.to_state
