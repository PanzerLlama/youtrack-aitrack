"""Plugin registries for trigger and action types."""

from youtrack_aitrack.domain.action import ActionSpec
from youtrack_aitrack.domain.trigger import TriggerSpec
from youtrack_aitrack.registry.store import Registry

trigger_registry: Registry[TriggerSpec] = Registry("trigger")
action_registry: Registry[ActionSpec] = Registry("action")

register_trigger = trigger_registry.register
register_action = action_registry.register

__all__ = [
    "Registry",
    "action_registry",
    "register_action",
    "register_trigger",
    "trigger_registry",
]
