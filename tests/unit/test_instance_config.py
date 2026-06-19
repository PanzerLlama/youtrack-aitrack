"""Tests for InstanceConfig pydantic model and YAML loader."""

from __future__ import annotations

from pathlib import Path

import pytest

from youtrack_aitrack.config import (
    InstanceConfig,
    InstanceConfigError,
    load_instance_config,
)

VALID_YAML = """
youtrack:
  url: https://yt.example.com
  token: ${YT_TOKEN}
  project: ABC
anthropic:
  api_key: ${ANTHROPIC_KEY}
"""


def _write(tmp_path: Path, name: str, text: str) -> Path:
    p = tmp_path / name
    p.write_text(text)
    return p


def test_load_happy_path_with_defaults(tmp_path: Path) -> None:
    path = _write(tmp_path, "config.yaml", VALID_YAML)
    cfg = load_instance_config(path, env={"YT_TOKEN": "tk", "ANTHROPIC_KEY": "sk"})
    assert isinstance(cfg, InstanceConfig)
    assert cfg.youtrack.url == "https://yt.example.com"
    assert cfg.youtrack.token == "tk"
    assert cfg.youtrack.project == "ABC"
    assert cfg.anthropic.api_key == "sk"
    assert cfg.defaults.default_agent == "claude_code_cli"
    assert cfg.paths.workflows_dir == Path("workflows")
    assert cfg.paths.prompts_dir == Path("prompts")
    assert cfg.paths.runs_dir == Path("runs")
    assert cfg.defaults.branch_pattern == "{task_id}-*"
    assert cfg.defaults.poll_interval_seconds == 60


def test_path_helpers_resolve_relative_to_config_dir(tmp_path: Path) -> None:
    path = _write(tmp_path, "config.yaml", VALID_YAML)
    cfg = load_instance_config(path, env={"YT_TOKEN": "tk", "ANTHROPIC_KEY": "sk"})
    cd = Path("/home/u/.youtrack-aitrack")
    assert cfg.workflows_path(cd) == cd / "workflows"
    assert cfg.prompts_path(cd) == cd / "prompts"
    assert cfg.runs_path(cd) == cd / "runs"


def test_env_var_expansion_in_token_and_api_key(tmp_path: Path) -> None:
    path = _write(tmp_path, "config.yaml", VALID_YAML)
    cfg = load_instance_config(path, env={"YT_TOKEN": "secret-1", "ANTHROPIC_KEY": "secret-2"})
    assert cfg.youtrack.token == "secret-1"
    assert cfg.anthropic.api_key == "secret-2"


def test_custom_paths_override_defaults(tmp_path: Path) -> None:
    text = """
youtrack:
  url: https://yt.example.com
  token: t
  project: P
anthropic:
  api_key: k
paths:
  workflows_dir: my-workflows
  prompts_dir: my-prompts
  runs_dir: my-runs
defaults:
  branch_pattern: "feat/{task_id}"
  poll_interval_seconds: 30
"""
    path = _write(tmp_path, "config.yaml", text)
    cfg = load_instance_config(path, env={})
    assert cfg.paths.workflows_dir == Path("my-workflows")
    assert cfg.paths.prompts_dir == Path("my-prompts")
    assert cfg.paths.runs_dir == Path("my-runs")
    assert cfg.defaults.branch_pattern == "feat/{task_id}"
    assert cfg.defaults.poll_interval_seconds == 30


def test_missing_required_field_raises_naming_field(tmp_path: Path) -> None:
    text = """
youtrack:
  url: https://yt.example.com
  project: ABC
anthropic:
  api_key: k
"""
    path = _write(tmp_path, "config.yaml", text)
    with pytest.raises(InstanceConfigError) as exc:
        load_instance_config(path, env={})
    msg = str(exc.value)
    assert "youtrack.token" in msg
    assert str(path) in msg


def test_missing_env_var_raises(tmp_path: Path) -> None:
    path = _write(tmp_path, "config.yaml", VALID_YAML)
    with pytest.raises(InstanceConfigError) as exc:
        load_instance_config(path, env={"YT_TOKEN": "tk"})
    assert "ANTHROPIC_KEY" in str(exc.value)


def test_invalid_yaml_reports_path(tmp_path: Path) -> None:
    path = _write(tmp_path, "bad.yaml", "youtrack:\n  url: x\n  bad: : :\n")
    with pytest.raises(InstanceConfigError) as exc:
        load_instance_config(path, env={})
    assert str(path) in str(exc.value)


def test_root_must_be_mapping(tmp_path: Path) -> None:
    path = _write(tmp_path, "list.yaml", "- a\n- b\n")
    with pytest.raises(InstanceConfigError) as exc:
        load_instance_config(path, env={})
    assert "mapping" in str(exc.value)
