"""Tests for ``workflows list`` and ``workflows validate`` subcommands."""

from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

from youtrack_aitrack.cli.config_dir import ENV_VAR
from youtrack_aitrack.cli.init import scaffold
from youtrack_aitrack.cli.main import app

runner = CliRunner()


@pytest.fixture(autouse=True)
def _stub_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Populate the env vars referenced by the scaffolded config.yaml."""
    monkeypatch.setenv("YOUTRACK_URL", "https://yt.example.com")
    monkeypatch.setenv("YOUTRACK_TOKEN", "tok")
    monkeypatch.setenv("YOUTRACK_PROJECT", "ABC")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")


VALID_WORKFLOW = """\
name: ready-for-testing-audit
trigger:
  type: status_change
  to_state: "Ready for testing"
actions:
  - id: security_audit
    type: ai_report
    inputs: [git_diff]
    output: { kind: custom_field, name: "Security Audit" }
    prompt: "audit prompt"
    model: claude-sonnet-4-6
"""

INVALID_WORKFLOW = """\
name: broken
trigger: { type: nope }
actions: []
"""


def _make_config(tmp_path: Path) -> Path:
    """Scaffold a config dir and return it."""
    cfg = tmp_path / "cfg"
    scaffold(cfg)
    return cfg


def _write_workflow(cfg: Path, name: str, content: str) -> Path:
    target = cfg / "workflows" / name
    target.write_text(content)
    return target


def test_list_with_no_workflows(tmp_path: Path) -> None:
    cfg = _make_config(tmp_path)
    result = runner.invoke(app, ["--config-dir", str(cfg), "workflows", "list"])
    assert result.exit_code == 0
    assert "No workflows found" in result.output


def test_list_with_valid_and_invalid_workflows(tmp_path: Path) -> None:
    cfg = _make_config(tmp_path)
    _write_workflow(cfg, "good.yaml", VALID_WORKFLOW)
    _write_workflow(cfg, "bad.yaml", INVALID_WORKFLOW)
    result = runner.invoke(app, ["--config-dir", str(cfg), "workflows", "list"])
    assert result.exit_code == 0
    assert "good.yaml" in result.output
    assert "ready-for-testing-audit" in result.output
    assert "status_change" in result.output
    assert "ERROR:" in result.output
    assert "bad.yaml" in result.output


def test_validate_passes_when_all_valid(tmp_path: Path) -> None:
    cfg = _make_config(tmp_path)
    _write_workflow(cfg, "good.yaml", VALID_WORKFLOW)
    result = runner.invoke(app, ["--config-dir", str(cfg), "workflows", "validate"])
    assert result.exit_code == 0
    assert result.output == ""


def test_validate_fails_and_names_broken_file(tmp_path: Path) -> None:
    cfg = _make_config(tmp_path)
    _write_workflow(cfg, "good.yaml", VALID_WORKFLOW)
    _write_workflow(cfg, "bad.yaml", INVALID_WORKFLOW)
    result = runner.invoke(app, ["--config-dir", str(cfg), "workflows", "validate"])
    assert result.exit_code == 1
    combined = result.output + (result.stderr if result.stderr_bytes is not None else "")
    assert "bad.yaml" in combined
    assert "ERROR" in combined


def test_validate_verbose_lists_each_file(tmp_path: Path) -> None:
    cfg = _make_config(tmp_path)
    _write_workflow(cfg, "good.yaml", VALID_WORKFLOW)
    _write_workflow(cfg, "also.yaml", VALID_WORKFLOW.replace("ready-for-testing-audit", "second"))
    result = runner.invoke(app, ["--config-dir", str(cfg), "workflows", "validate", "--verbose"])
    assert result.exit_code == 0
    assert "OK: good.yaml" in result.output
    assert "OK: also.yaml" in result.output
    assert "2 workflow(s) OK" in result.output


def test_missing_config_yaml_errors(tmp_path: Path) -> None:
    cfg = tmp_path / "empty"
    cfg.mkdir()
    result = runner.invoke(app, ["--config-dir", str(cfg), "workflows", "list"])
    assert result.exit_code != 0


def test_workflows_respects_env_var(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    cfg = _make_config(tmp_path)
    _write_workflow(cfg, "good.yaml", VALID_WORKFLOW)
    monkeypatch.setenv(ENV_VAR, str(cfg))
    monkeypatch.setenv("HOME", str(tmp_path / "fake-home"))
    result = runner.invoke(app, ["workflows", "list"])
    assert result.exit_code == 0
    assert "good.yaml" in result.output


def test_workflows_explicit_overrides_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    env_cfg = _make_config(tmp_path / "env")
    _write_workflow(env_cfg, "from-env.yaml", VALID_WORKFLOW)
    explicit_cfg = _make_config(tmp_path / "explicit")
    _write_workflow(explicit_cfg, "from-explicit.yaml", VALID_WORKFLOW)
    monkeypatch.setenv(ENV_VAR, str(env_cfg))
    result = runner.invoke(app, ["--config-dir", str(explicit_cfg), "workflows", "list"])
    assert result.exit_code == 0
    assert "from-explicit.yaml" in result.output
    assert "from-env.yaml" not in result.output
