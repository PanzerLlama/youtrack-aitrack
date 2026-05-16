"""OutputSpec — declarative sink for an action's result."""

from __future__ import annotations

from typing import Annotated, Literal, Protocol

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


class OutputSink(Protocol):
    """Writes an action's result to the sink declared by its OutputSpec.

    Engine convention: invoked once per non-skipped non-failed action whose spec has
    a non-null `output`. The action's :class:`ActionResult.output` dict must include
    a ``"text"`` key; the engine extracts it and passes it as ``value``. Actions
    whose result lacks ``"text"`` are silently skipped (e.g. ``set_field`` results).
    """

    async def write(
        self, *, issue_id: str, spec: CustomFieldOutput | CommentOutput, value: str
    ) -> None: ...
