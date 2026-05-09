"""OutputSpec — declarative sink for an action's result."""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field


class CustomFieldOutput(BaseModel):
    kind: Literal["custom_field"] = "custom_field"
    name: str

    model_config = ConfigDict(frozen=True)


class CommentOutput(BaseModel):
    kind: Literal["comment"] = "comment"
    template: str | None = None

    model_config = ConfigDict(frozen=True)


OutputSpec = Annotated[
    CustomFieldOutput | CommentOutput,
    Field(discriminator="kind"),
]
