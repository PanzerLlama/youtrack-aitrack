"""Concrete action types. Importing this module registers all actions."""

from youtrack_aitrack.domain.actions.ai_report import AiReportAction
from youtrack_aitrack.domain.actions.set_field import SetFieldAction
from youtrack_aitrack.domain.actions.yt_comment import YtCommentAction

__all__ = ["AiReportAction", "SetFieldAction", "YtCommentAction"]
