"""YtCommentAction — post a comment back to the YouTrack issue."""

from __future__ import annotations

from typing import Any, Literal, Protocol

from pydantic import PrivateAttr

from youtrack_aitrack.domain.action import ActionSpec
from youtrack_aitrack.domain.context import Context
from youtrack_aitrack.domain.run import ActionResult
from youtrack_aitrack.registry import register_action


class CommentPoster(Protocol):
    async def post_comment(self, issue_id: str, body: str) -> None: ...


class _NoOpCommentPoster:
    async def post_comment(self, issue_id: str, body: str) -> None:
        return None


@register_action("yt_comment")
class YtCommentAction(ActionSpec):
    type: Literal["yt_comment"] = "yt_comment"
    body: str

    _poster: CommentPoster = PrivateAttr()

    def __init__(self, *, poster: CommentPoster | None = None, **data: Any) -> None:
        super().__init__(**data)
        self._poster = poster if poster is not None else _NoOpCommentPoster()

    async def execute(self, ctx: Context) -> ActionResult:
        await self._poster.post_comment(ctx.issue.issue_id, self.body)
        return ActionResult(
            action_id=self.id,
            success=True,
            output={"issue_id": ctx.issue.issue_id, "body": self.body},
        )
