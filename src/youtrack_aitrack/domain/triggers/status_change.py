"""StatusChangeTrigger — fires when an issue moves between states."""

from __future__ import annotations

from typing import Literal

from youtrack_aitrack.domain.event import STATE_FIELD_NAME, IssueEvent
from youtrack_aitrack.domain.trigger import TriggerSpec
from youtrack_aitrack.registry import register_trigger


@register_trigger("status_change")
class StatusChangeTrigger(TriggerSpec):
    type: Literal["status_change"] = "status_change"
    from_state: str = "*"
    to_state: str

    def matches(self, event: IssueEvent) -> bool:
        from_actual, to_actual = _state_transition_values(event)
        if to_actual is None:
            return False
        if self.from_state != "*" and from_actual != self.from_state:
            return False
        return to_actual == self.to_state


def _state_transition_values(event: IssueEvent) -> tuple[str | None, str | None]:
    """Extract (from, to) for a state transition, regardless of producer.

    Coexist mode: poller emits event_kind='field_change' with field_name=='State'
    and from_value/to_value populated; manual constructions and legacy paths emit
    event_kind='status_change' with from_state/to_state. Both shapes are
    accepted; anything else yields (None, None) so the matcher rejects.
    """
    if event.event_kind == "status_change":
        return event.from_state, event.to_state
    if event.event_kind == "field_change" and event.field_name == STATE_FIELD_NAME:
        return event.from_value, event.to_value
    return None, None
