"""Load and validate workflow YAML files into :class:`Workflow` objects."""

from __future__ import annotations

import os
import re
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import yaml  # type: ignore[import-untyped]
from pydantic import ValidationError

from youtrack_aitrack.domain.action import ActionSpec
from youtrack_aitrack.domain.trigger import TriggerSpec
from youtrack_aitrack.domain.workflow import Workflow
from youtrack_aitrack.registry import action_registry, trigger_registry


def _ensure_plugins_registered() -> None:
    """Import the trigger/action subpackages so their decorators populate the registries."""
    import youtrack_aitrack.domain.actions
    import youtrack_aitrack.domain.triggers  # noqa: F401


_ENV_PATTERN = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}")


class WorkflowParseError(ValueError):
    """Raised when a workflow YAML file cannot be loaded or validated."""

    def __init__(
        self,
        message: str,
        *,
        path: Path | None = None,
        line: int | None = None,
        column: int | None = None,
    ) -> None:
        location = str(path) if path else "<workflow>"
        if line is not None:
            location += f":{line}"
            if column is not None:
                location += f":{column}"
        super().__init__(f"{location}: {message}")
        self.path = path
        self.line = line
        self.column = column


def expand_env(value: Any, env: Mapping[str, str]) -> Any:
    """Recursively replace ``${VAR}`` references in strings using *env*."""
    if isinstance(value, str):
        return _expand_str(value, env)
    if isinstance(value, list):
        return [expand_env(v, env) for v in value]
    if isinstance(value, dict):
        return {k: expand_env(v, env) for k, v in value.items()}
    return value


def _expand_str(value: str, env: Mapping[str, str]) -> str:
    def _sub(match: re.Match[str]) -> str:
        name = match.group(1)
        if name not in env:
            raise WorkflowParseError(f"undefined environment variable ${{{name}}}")
        return env[name]

    return _ENV_PATTERN.sub(_sub, value)


def load_workflow(
    path: Path,
    *,
    env: Mapping[str, str] | None = None,
) -> Workflow:
    """Read *path*, expand env vars, and validate against :class:`Workflow`."""
    _ensure_plugins_registered()
    raw_text = path.read_text()
    raw = _parse_yaml(raw_text, path)
    if not isinstance(raw, dict):
        raise WorkflowParseError("workflow root must be a mapping", path=path)
    expanded = expand_env(raw, env if env is not None else os.environ)
    return _build_workflow(expanded, path=path)


def _parse_yaml(text: str, path: Path) -> Any:
    try:
        return yaml.safe_load(text)
    except yaml.MarkedYAMLError as exc:
        mark = exc.problem_mark
        line = mark.line + 1 if mark is not None else None
        column = mark.column + 1 if mark is not None else None
        raise WorkflowParseError(
            exc.problem or "invalid YAML", path=path, line=line, column=column
        ) from exc
    except yaml.YAMLError as exc:
        raise WorkflowParseError(str(exc), path=path) from exc


def _build_workflow(raw: dict[str, Any], *, path: Path) -> Workflow:
    trigger = _build_trigger(raw.get("trigger"), path=path)
    actions = _build_actions(raw.get("actions") or [], group="actions", path=path)
    on_success = _build_actions(raw.get("on_success") or [], group="on_success", path=path)
    on_failure = _build_actions(raw.get("on_failure") or [], group="on_failure", path=path)
    fields: dict[str, Any] = {
        "trigger": trigger,
        "actions": actions,
        "on_success": on_success,
        "on_failure": on_failure,
    }
    if "name" in raw:
        fields["name"] = raw["name"]
    if "description" in raw:
        fields["description"] = raw["description"]
    try:
        return Workflow(**fields)
    except ValidationError as exc:
        raise WorkflowParseError(_format_validation_errors(exc), path=path) from exc


def _build_trigger(raw: Any, *, path: Path) -> TriggerSpec:
    if not isinstance(raw, dict):
        raise WorkflowParseError("workflow.trigger must be a mapping", path=path)
    type_name = raw.get("type")
    if not isinstance(type_name, str):
        raise WorkflowParseError("workflow.trigger.type must be a string", path=path)
    try:
        cls = trigger_registry.get(type_name)
    except KeyError as exc:
        raise WorkflowParseError(str(exc), path=path) from exc
    try:
        return cls(**raw)
    except ValidationError as exc:
        raise WorkflowParseError(_format_validation_errors(exc), path=path) from exc


def _build_actions(raw: Any, *, group: str, path: Path) -> list[ActionSpec]:
    if not isinstance(raw, list):
        raise WorkflowParseError(f"workflow.{group} must be a list", path=path)
    return [_build_action(item, group=group, index=i, path=path) for i, item in enumerate(raw)]


def _build_action(raw: Any, *, group: str, index: int, path: Path) -> ActionSpec:
    locator = f"{group}[{index}]"
    if not isinstance(raw, dict):
        raise WorkflowParseError(f"{locator} must be a mapping", path=path)
    type_name = raw.get("type")
    if not isinstance(type_name, str):
        raise WorkflowParseError(f"{locator}.type must be a string", path=path)
    try:
        cls = action_registry.get(type_name)
    except KeyError as exc:
        raise WorkflowParseError(f"{locator}: {exc}", path=path) from exc
    try:
        return cls(**raw)
    except ValidationError as exc:
        raise WorkflowParseError(f"{locator}: {_format_validation_errors(exc)}", path=path) from exc


def _format_validation_errors(exc: ValidationError) -> str:
    parts = []
    for err in exc.errors():
        loc = ".".join(str(p) for p in err["loc"]) or "<root>"
        parts.append(f"{loc}: {err['msg']}")
    return "; ".join(parts)
