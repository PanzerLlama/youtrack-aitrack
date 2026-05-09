"""Export the workflow JSON Schema derived from the pydantic model."""

from __future__ import annotations

from typing import Any

from youtrack_aitrack.domain.workflow import Workflow


def export_workflow_schema() -> dict[str, Any]:
    """Return the JSON Schema for :class:`Workflow` as a plain dict."""
    return Workflow.model_json_schema()
