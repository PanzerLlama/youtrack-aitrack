"""Tests for the top-level CLI entry point — version flag + subcommand."""

from __future__ import annotations

from importlib.metadata import version

from typer.testing import CliRunner

from youtrack_aitrack.cli.main import app

_RUNNER = CliRunner()


def _installed_version() -> str:
    return version("youtrack-aitrack")


def test_version_flag_long_form_prints_and_exits() -> None:
    result = _RUNNER.invoke(app, ["--version"])
    assert result.exit_code == 0
    assert f"youtrack-aitrack {_installed_version()}" in result.output


def test_version_flag_short_form_prints_and_exits() -> None:
    result = _RUNNER.invoke(app, ["-V"])
    assert result.exit_code == 0
    assert f"youtrack-aitrack {_installed_version()}" in result.output


def test_version_subcommand_still_works() -> None:
    result = _RUNNER.invoke(app, ["version"])
    assert result.exit_code == 0
    assert f"youtrack-aitrack {_installed_version()}" in result.output


def test_version_flag_does_not_require_config_dir_to_exist(tmp_path: object) -> None:
    # --version should short-circuit before config-dir loading. Pass a deliberately
    # non-existent --config-dir and verify the flag still works rather than erroring.
    result = _RUNNER.invoke(app, ["--config-dir", "/definitely/not/a/real/path", "--version"])
    assert result.exit_code == 0
    assert "youtrack-aitrack" in result.output


def test_version_output_matches_pyproject_distribution_version() -> None:
    # If pyproject.toml is bumped, the CLI output must update without a code change.
    # This test guards against a future regression where someone hardcodes the version.
    result = _RUNNER.invoke(app, ["--version"])
    assert _installed_version() in result.output
    # Sanity: the installed version is not the literal sentinel string.
    assert _installed_version() != "unknown"


def test_version_subcommand_help_is_present() -> None:
    result = _RUNNER.invoke(app, ["version", "--help"])
    assert result.exit_code == 0
    assert "Print the installed package version" in result.output
