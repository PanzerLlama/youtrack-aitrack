"""InstanceConfig — per-instance YAML config (one YouTrack project per daemon)."""

from __future__ import annotations

import os
from collections.abc import Mapping
from pathlib import Path
from typing import Any, Literal

import yaml  # type: ignore[import-untyped]
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from youtrack_aitrack.config.loader import expand_env


class InstanceConfigError(ValueError):
    """Raised when an instance config YAML file cannot be loaded or validated."""

    def __init__(
        self,
        message: str,
        *,
        path: Path | None = None,
        line: int | None = None,
        column: int | None = None,
    ) -> None:
        location = str(path) if path else "<instance-config>"
        if line is not None:
            location += f":{line}"
            if column is not None:
                location += f":{column}"
        super().__init__(f"{location}: {message}")
        self.path = path
        self.line = line
        self.column = column


class YouTrackSection(BaseModel):
    url: str
    token: str
    project: str

    model_config = ConfigDict(frozen=True)


class AnthropicSection(BaseModel):
    api_key: str
    default_model: str = "claude-sonnet-4-6"

    model_config = ConfigDict(frozen=True)


class PathsSection(BaseModel):
    workflows_dir: Path = Path("workflows")
    prompts_dir: Path = Path("prompts")
    runs_dir: Path = Path("runs")

    model_config = ConfigDict(frozen=True)


class DefaultsSection(BaseModel):
    branch_pattern: str = "{task_id}-*"
    poll_interval_seconds: int = 60
    poll_lookback_seconds: int = 3600
    base_url: str | None = None
    git_base_branch: str = "main"
    include_tags: list[str] = Field(default_factory=list)
    default_agent: str = "anthropic_api"
    agent_timeout_seconds: int = 300
    cli_agent_concurrency: int = 1
    cli_agent_mode: Literal["bare", "oauth"] = "oauth"

    model_config = ConfigDict(frozen=True)


class InstanceConfig(BaseModel):
    youtrack: YouTrackSection
    anthropic: AnthropicSection
    paths: PathsSection = Field(default_factory=PathsSection)
    defaults: DefaultsSection = Field(default_factory=DefaultsSection)

    model_config = ConfigDict(frozen=True)

    def workflows_path(self, config_dir: Path) -> Path:
        return config_dir / self.paths.workflows_dir

    def prompts_path(self, config_dir: Path) -> Path:
        return config_dir / self.paths.prompts_dir

    def runs_path(self, config_dir: Path) -> Path:
        return config_dir / self.paths.runs_dir


def load_instance_config(
    path: Path,
    *,
    env: Mapping[str, str] | None = None,
) -> InstanceConfig:
    """Read *path*, expand ${VAR} references, validate against :class:`InstanceConfig`."""
    raw_text = path.read_text()
    raw = _parse_yaml(raw_text, path)
    if not isinstance(raw, dict):
        raise InstanceConfigError("instance config root must be a mapping", path=path)
    try:
        expanded = expand_env(raw, env if env is not None else os.environ)
    except ValueError as exc:
        raise InstanceConfigError(str(exc).split(": ", 1)[-1], path=path) from exc
    try:
        return InstanceConfig(**expanded)
    except ValidationError as exc:
        raise InstanceConfigError(_format_validation_errors(exc), path=path) from exc


def _parse_yaml(text: str, path: Path) -> Any:
    try:
        return yaml.safe_load(text)
    except yaml.MarkedYAMLError as exc:
        mark = exc.problem_mark
        line = mark.line + 1 if mark is not None else None
        column = mark.column + 1 if mark is not None else None
        raise InstanceConfigError(
            exc.problem or "invalid YAML", path=path, line=line, column=column
        ) from exc
    except yaml.YAMLError as exc:
        raise InstanceConfigError(str(exc), path=path) from exc


def _format_validation_errors(exc: ValidationError) -> str:
    parts = []
    for err in exc.errors():
        loc = ".".join(str(p) for p in err["loc"]) or "<root>"
        parts.append(f"{loc}: {err['msg']}")
    return "; ".join(parts)
