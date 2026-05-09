"""SetFieldAction — write values to YouTrack issue custom fields."""

from __future__ import annotations

from typing import Any, Literal, Protocol

from pydantic import PrivateAttr

from youtrack_aitrack.domain.action import ActionSpec
from youtrack_aitrack.domain.context import Context
from youtrack_aitrack.domain.run import ActionResult
from youtrack_aitrack.registry import register_action


class FieldWriter(Protocol):
    async def set_fields(self, issue_id: str, fields: dict[str, str]) -> None: ...


class _NoOpFieldWriter:
    async def set_fields(self, issue_id: str, fields: dict[str, str]) -> None:
        return None


@register_action("set_field")
class SetFieldAction(ActionSpec):
    type: Literal["set_field"] = "set_field"
    fields: dict[str, str]

    _writer: FieldWriter = PrivateAttr()

    def __init__(self, *, writer: FieldWriter | None = None, **data: Any) -> None:
        super().__init__(**data)
        self._writer = writer if writer is not None else _NoOpFieldWriter()

    async def execute(self, ctx: Context) -> ActionResult:
        await self._writer.set_fields(ctx.issue.issue_id, dict(self.fields))
        return ActionResult(
            action_id=self.id,
            success=True,
            output={"issue_id": ctx.issue.issue_id, "fields": dict(self.fields)},
        )
