"""TriggerSpec — base for trigger declarations parsed from YAML."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class TriggerSpec(BaseModel):
    type: str

    # extra="allow" keeps type-specific fields until registry promotes to a concrete subclass
    model_config = ConfigDict(frozen=True, extra="allow")
