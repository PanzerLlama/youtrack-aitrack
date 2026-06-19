"""Tests for the init scaffold command and config-dir resolution."""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from typer.testing import CliRunner

from youtrack_aitrack.cli.config_dir import ENV_VAR, resolve_config_dir
from youtrack_aitrack.cli.init import scaffold
from youtrack_aitrack.cli.main import app
from youtrack_aitrack.config import load_instance_config

runner = CliRunner()


# --- resolve_config_dir ---


def test_resolve_explicit_wins_over_env_and_home(tmp_path: Path) -> None:
    explicit = tmp_path / "explicit"
    env = {ENV_VAR: str(tmp_path / "from-env")}
    out = resolve_config_dir(explicit, env=env, home=tmp_path / "home")
    assert out == explicit


def test_resolve_env_wins_over_home(tmp_path: Path) -> None:
    env = {ENV_VAR: str(tmp_path / "from-env")}
    out = resolve_config_dir(None, env=env, home=tmp_path / "home")
    assert out == tmp_path / "from-env"


def test_resolve_falls_back_to_home_default(tmp_path: Path) -> None:
    out = resolve_config_dir(None, env={}, home=tmp_path)
    assert out == tmp_path / ".youtrack-aitrack"


# --- scaffold (pure) ---


def test_scaffold_creates_full_layout(tmp_path: Path) -> None:
    cfg = tmp_path / "cfg"
    written = scaffold(cfg)
    assert (cfg / "config.yaml").is_file()
    assert (cfg / ".env.example").is_file()
    for sub in ("workflows", "prompts", "runs"):
        assert (cfg / sub).is_dir()
        assert (cfg / sub / ".gitkeep").is_file()
    assert len(written) == 5


def test_scaffold_is_idempotent(tmp_path: Path) -> None:
    cfg = tmp_path / "cfg"
    scaffold(cfg)
    (cfg / "config.yaml").write_text("custom-content")
    written = scaffold(cfg)
    assert written == []
    assert (cfg / "config.yaml").read_text() == "custom-content"


def test_scaffold_force_rewrites_files(tmp_path: Path) -> None:
    cfg = tmp_path / "cfg"
    scaffold(cfg)
    (cfg / "config.yaml").write_text("custom-content")
    written = scaffold(cfg, force=True)
    assert (cfg / "config.yaml") in written
    assert "youtrack:" in (cfg / "config.yaml").read_text()


def test_scaffolded_config_loads_with_env(tmp_path: Path) -> None:
    cfg = tmp_path / "cfg"
    scaffold(cfg)
    env = {
        "YOUTRACK_URL": "https://yt.example.com",
        "YOUTRACK_TOKEN": "tk",
        "YOUTRACK_PROJECT": "ABC",
        "ANTHROPIC_API_KEY": "sk",
    }
    inst = load_instance_config(cfg / "config.yaml", env=env)
    assert inst.youtrack.url == "https://yt.example.com"
    assert inst.youtrack.token == "tk"
    assert inst.anthropic.api_key == "sk"
    assert inst.defaults.default_agent == "claude_code_cli"
    assert inst.defaults.branch_pattern == "{task_id}-*"


# --- CLI surface ---


def test_init_command_with_explicit_config_dir(tmp_path: Path) -> None:
    cfg = tmp_path / "cfg"
    result = runner.invoke(app, ["--config-dir", str(cfg), "init"])
    assert result.exit_code == 0, result.output
    assert (cfg / "config.yaml").is_file()
    assert (cfg / "workflows" / ".gitkeep").is_file()
    assert str(cfg) in result.output


def test_init_uses_env_var(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    cfg = tmp_path / "from-env"
    monkeypatch.setenv(ENV_VAR, str(cfg))
    monkeypatch.setenv("HOME", str(tmp_path / "fake-home"))
    result = runner.invoke(app, ["init"])
    assert result.exit_code == 0, result.output
    assert (cfg / "config.yaml").is_file()


def test_init_explicit_overrides_env_var(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    env_cfg = tmp_path / "from-env"
    explicit_cfg = tmp_path / "explicit"
    monkeypatch.setenv(ENV_VAR, str(env_cfg))
    result = runner.invoke(app, ["--config-dir", str(explicit_cfg), "init"])
    assert result.exit_code == 0, result.output
    assert (explicit_cfg / "config.yaml").is_file()
    assert not env_cfg.exists()


def test_init_idempotent_via_cli(tmp_path: Path) -> None:
    cfg = tmp_path / "cfg"
    runner.invoke(app, ["--config-dir", str(cfg), "init"])
    (cfg / "config.yaml").write_text("custom")
    result = runner.invoke(app, ["--config-dir", str(cfg), "init"])
    assert result.exit_code == 0
    assert "already initialized" in result.output
    assert (cfg / "config.yaml").read_text() == "custom"


def test_init_force_overwrites_via_cli(tmp_path: Path) -> None:
    cfg = tmp_path / "cfg"
    runner.invoke(app, ["--config-dir", str(cfg), "init"])
    (cfg / "config.yaml").write_text("custom")
    result = runner.invoke(app, ["--config-dir", str(cfg), "init", "--force"])
    assert result.exit_code == 0
    assert "youtrack:" in (cfg / "config.yaml").read_text()


def test_dotenv_autoloaded_before_subcommand(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cfg = tmp_path / "cfg"
    cfg.mkdir()
    (cfg / ".env").write_text("AITRACK_TEST_VAR=loaded-from-dotenv\n")
    monkeypatch.delenv("AITRACK_TEST_VAR", raising=False)
    runner.invoke(app, ["--config-dir", str(cfg), "version"])
    assert os.environ.get("AITRACK_TEST_VAR") == "loaded-from-dotenv"
