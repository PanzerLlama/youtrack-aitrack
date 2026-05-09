"""ActionSpec — base for action declarations parsed from YAML."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from youtrack_aitrack.domain.output import OutputSpec


class ActionSpec(BaseModel):
    id: str
    type: str
    depends_on: list[str] = Field(default_factory=list)
    inputs: list[str] = Field(default_factory=list)
    output: OutputSpec | None = None

    # extra="allow" keeps type-specific fields until registry promotes to a concrete subclass
    model_config = ConfigDict(frozen=True, extra="allow")
