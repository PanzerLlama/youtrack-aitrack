"""Concrete trigger types. Importing this module registers all triggers."""

from youtrack_aitrack.domain.triggers.manual import ManualTrigger
from youtrack_aitrack.domain.triggers.status_change import StatusChangeTrigger

__all__ = ["ManualTrigger", "StatusChangeTrigger"]
