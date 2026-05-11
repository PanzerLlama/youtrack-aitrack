"""Resolve the per-instance config directory (CLI flag > env var > default)."""

from __future__ import annotations

import os
from pathlib import Path

ENV_VAR = "YOUTRACK_AITRACK_HOME"
DEFAULT_DIR_NAME = ".youtrack-aitrack"


def resolve_config_dir(
    explicit: Path | None = None,
    *,
    env: dict[str, str] | os._Environ[str] | None = None,
    home: Path | None = None,
) -> Path:
    """Return the config directory using precedence: *explicit* > env > ``~/<default>``."""
    if explicit is not None:
        return explicit.expanduser()
    src_env = env if env is not None else os.environ
    if val := src_env.get(ENV_VAR):
        return Path(val).expanduser()
    base = home if home is not None else Path.home()
    return base / DEFAULT_DIR_NAME
