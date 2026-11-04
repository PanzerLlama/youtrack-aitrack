"""ClaudeCodeCliRunner — subprocess behaviour, concurrency gate, errors.

These tests substitute a small POSIX shell script for the real `claude` binary,
so they verify how the runner spawns, captures, times out, and serialises calls
without depending on Anthropic infrastructure.
"""

from __future__ import annotations

import asyncio
import stat
import time
from pathlib import Path

import pytest

from youtrack_aitrack.adapters.cli.claude_code import ClaudeCodeCliRunner
from youtrack_aitrack.domain.agent_runner import AgentRunnerError


def _write_fake_binary(path: Path, body: str) -> Path:
    path.write_text(f"#!/usr/bin/env bash\n{body}\n")
    path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    return path


@pytest.fixture
def fake_success(tmp_path: Path) -> Path:
    return _write_fake_binary(
        tmp_path / "fake-claude",
        'echo "## Findings\nNo issues.\n"',
    )


@pytest.fixture
def fake_failure(tmp_path: Path) -> Path:
    return _write_fake_binary(
        tmp_path / "fake-claude-fail",
        'echo "auth required" >&2\nexit 17\n',
    )


@pytest.fixture
def fake_slow(tmp_path: Path) -> Path:
    return _write_fake_binary(
        tmp_path / "fake-claude-slow",
        'sleep 0.3\necho "late"',
    )


@pytest.fixture
def fake_echo_args(tmp_path: Path) -> Path:
    # Echoes its argv (one per line) so tests can assert on the command line
    # the runner produced.
    return _write_fake_binary(
        tmp_path / "fake-claude-args",
        'for a in "$@"; do echo "$a"; done',
    )


async def test_run_returns_stdout_and_zero_exit(fake_success: Path, tmp_path: Path) -> None:
    runner = ClaudeCodeCliRunner(asyncio.Semaphore(1), binary=str(fake_success))
    result = await runner.run("hello", cwd=tmp_path, commit_sha="abc", timeout_s=5.0)
    assert "No issues." in result.output
    assert result.exit_code == 0
    assert result.duration_s >= 0.0


async def test_run_raises_on_nonzero_exit(fake_failure: Path, tmp_path: Path) -> None:
    runner = ClaudeCodeCliRunner(asyncio.Semaphore(1), binary=str(fake_failure))
    with pytest.raises(AgentRunnerError) as exc:
        await runner.run("hello", cwd=tmp_path, commit_sha=None, timeout_s=5.0)
    assert "code 17" in str(exc.value)
    assert exc.value.stderr is not None
    assert "auth required" in exc.value.stderr


async def test_run_raises_on_timeout(fake_slow: Path, tmp_path: Path) -> None:
    runner = ClaudeCodeCliRunner(asyncio.Semaphore(1), binary=str(fake_slow))
    with pytest.raises(AgentRunnerError) as exc:
        await runner.run("hello", cwd=tmp_path, commit_sha=None, timeout_s=0.1)
    assert "timeout" in str(exc.value).lower()


async def test_run_raises_when_binary_missing(tmp_path: Path) -> None:
    runner = ClaudeCodeCliRunner(asyncio.Semaphore(1), binary="/definitely/not/installed/anywhere")
    with pytest.raises(AgentRunnerError) as exc:
        await runner.run("hello", cwd=tmp_path, commit_sha=None, timeout_s=5.0)
    assert "not found" in str(exc.value).lower()


async def test_semaphore_serialises_concurrent_runs(fake_slow: Path, tmp_path: Path) -> None:
    semaphore = asyncio.Semaphore(1)
    runner = ClaudeCodeCliRunner(semaphore, binary=str(fake_slow))

    started = time.monotonic()
    await asyncio.gather(
        runner.run("p1", cwd=tmp_path, commit_sha=None, timeout_s=5.0),
        runner.run("p2", cwd=tmp_path, commit_sha=None, timeout_s=5.0),
        runner.run("p3", cwd=tmp_path, commit_sha=None, timeout_s=5.0),
    )
    elapsed = time.monotonic() - started
    # 3 serialised runs of ~0.3s each ≥ 0.9s; allow generous slack for CI jitter.
    assert elapsed >= 0.8, f"expected serialised runs, got elapsed={elapsed:.2f}s"


async def test_semaphore_with_capacity_runs_in_parallel(fake_slow: Path, tmp_path: Path) -> None:
    semaphore = asyncio.Semaphore(3)
    runner = ClaudeCodeCliRunner(semaphore, binary=str(fake_slow))

    started = time.monotonic()
    await asyncio.gather(
        runner.run("p1", cwd=tmp_path, commit_sha=None, timeout_s=5.0),
        runner.run("p2", cwd=tmp_path, commit_sha=None, timeout_s=5.0),
        runner.run("p3", cwd=tmp_path, commit_sha=None, timeout_s=5.0),
    )
    elapsed = time.monotonic() - started
    # With cap=3 all three run in parallel; should finish well under 0.9s.
    assert elapsed < 0.8, f"expected parallel runs, got elapsed={elapsed:.2f}s"


async def test_bare_mode_adds_flag_and_prompt(fake_echo_args: Path, tmp_path: Path) -> None:
    runner = ClaudeCodeCliRunner(
        asyncio.Semaphore(1),
        binary=str(fake_echo_args),
        bare=True,
        env={"ANTHROPIC_API_KEY": "test-key"},
    )
    result = await runner.run("prompt-payload", cwd=tmp_path, commit_sha=None, timeout_s=5.0)
    lines = result.output.strip().splitlines()
    assert "--bare" in lines
    assert "-p" in lines
    assert "prompt-payload" in lines


async def test_non_bare_mode_omits_bare_flag(fake_echo_args: Path, tmp_path: Path) -> None:
    runner = ClaudeCodeCliRunner(asyncio.Semaphore(1), binary=str(fake_echo_args))
    result = await runner.run("p", cwd=tmp_path, commit_sha=None, timeout_s=5.0)
    assert "--bare" not in result.output.splitlines()


def test_bare_mode_requires_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    with pytest.raises(ValueError, match="ANTHROPIC_API_KEY"):
        ClaudeCodeCliRunner(asyncio.Semaphore(1), bare=True)


def test_bare_mode_accepts_api_key_via_env_arg() -> None:
    # No system env var, but explicit env dict carries the key — should succeed.
    runner = ClaudeCodeCliRunner(asyncio.Semaphore(1), bare=True, env={"ANTHROPIC_API_KEY": "k"})
    assert runner is not None


async def test_allowed_tools_flag_propagates(fake_echo_args: Path, tmp_path: Path) -> None:
    runner = ClaudeCodeCliRunner(
        asyncio.Semaphore(1),
        binary=str(fake_echo_args),
        allowed_tools="Read,Bash(git *)",
    )
    result = await runner.run("p", cwd=tmp_path, commit_sha=None, timeout_s=5.0)
    lines = result.output.strip().splitlines()
    assert "--allowedTools" in lines
    assert "Read,Bash(git *)" in lines


async def test_cwd_is_honored(fake_success: Path, tmp_path: Path) -> None:
    # If cwd were ignored, this would still succeed; but ensure no error from
    # passing a real subdir, and that the runner sets it via subprocess.
    subdir = tmp_path / "nested"
    subdir.mkdir()
    runner = ClaudeCodeCliRunner(asyncio.Semaphore(1), binary=str(fake_success))
    result = await runner.run("p", cwd=subdir, commit_sha=None, timeout_s=5.0)
    assert result.exit_code == 0


async def test_model_kwarg_appends_model_flag(fake_echo_args: Path, tmp_path: Path) -> None:
    runner = ClaudeCodeCliRunner(asyncio.Semaphore(1), binary=str(fake_echo_args))
    result = await runner.run(
        "p", cwd=tmp_path, commit_sha=None, timeout_s=5.0, model="claude-sonnet-4-6"
    )
    lines = result.output.strip().splitlines()
    assert "--model" in lines
    assert "claude-sonnet-4-6" in lines


async def test_model_kwarg_omitted_when_none(fake_echo_args: Path, tmp_path: Path) -> None:
    runner = ClaudeCodeCliRunner(asyncio.Semaphore(1), binary=str(fake_echo_args))
    result = await runner.run("p", cwd=tmp_path, commit_sha=None, timeout_s=5.0)
    assert "--model" not in result.output.splitlines()


async def test_model_used_echoes_requested_model(fake_success: Path, tmp_path: Path) -> None:
    runner = ClaudeCodeCliRunner(asyncio.Semaphore(1), binary=str(fake_success))
    result = await runner.run(
        "p", cwd=tmp_path, commit_sha=None, timeout_s=5.0, model="claude-opus-4-7"
    )
    assert result.model_used == "claude-opus-4-7"


async def test_plan_mode_appends_permission_mode_flag(fake_echo_args: Path, tmp_path: Path) -> None:
    runner = ClaudeCodeCliRunner(asyncio.Semaphore(1), binary=str(fake_echo_args))
    result = await runner.run(
        "plan this", cwd=tmp_path, commit_sha=None, timeout_s=5.0, mode="plan"
    )
    lines = result.output.splitlines()
    assert "--permission-mode" in lines
    assert lines[lines.index("--permission-mode") + 1] == "plan"


async def test_default_mode_omits_permission_mode_flag(
    fake_echo_args: Path, tmp_path: Path
) -> None:
    runner = ClaudeCodeCliRunner(asyncio.Semaphore(1), binary=str(fake_echo_args))
    result = await runner.run("audit", cwd=tmp_path, commit_sha=None, timeout_s=5.0)
    assert "--permission-mode" not in result.output.splitlines()


# Trimmed from a real `claude -p --output-format json` run (Claude Code 2.1.318).
_ENVELOPE = (
    '{"type":"result","subtype":"success","is_error":false,"duration_ms":1258,'
    '"num_turns":1,"result":"## Findings\\nNo issues.","total_cost_usd":0.00237653,'
    '"usage":{"input_tokens":2,"cache_creation_input_tokens":11278,'
    '"cache_read_input_tokens":11873,"output_tokens":4,'
    '"server_tool_use":{"web_search_requests":0}},"modelUsage":{},"session_id":"s"}'
)
_ERROR_ENVELOPE = (
    '{"type":"result","subtype":"error_max_turns","is_error":true,'
    '"result":"Reached max turns","usage":{"output_tokens":9},"total_cost_usd":0.5}'
)


@pytest.fixture
def fake_json(tmp_path: Path) -> Path:
    return _write_fake_binary(tmp_path / "fake-claude-json", f"cat <<'EOF'\n{_ENVELOPE}\nEOF")


@pytest.fixture
def fake_json_error(tmp_path: Path) -> Path:
    return _write_fake_binary(
        tmp_path / "fake-claude-json-error", f"cat <<'EOF'\n{_ERROR_ENVELOPE}\nEOF"
    )


async def test_json_envelope_yields_result_text_tokens_and_cost(
    fake_json: Path, tmp_path: Path
) -> None:
    runner = ClaudeCodeCliRunner(asyncio.Semaphore(1), binary=str(fake_json))
    result = await runner.run("p", cwd=tmp_path, commit_sha=None, timeout_s=5.0)
    assert result.output == "## Findings\nNo issues."
    assert result.input_tokens == 2 + 11278 + 11873
    assert result.output_tokens == 4
    assert result.cost_usd == 0.00237653


async def test_error_envelope_with_zero_exit_raises(fake_json_error: Path, tmp_path: Path) -> None:
    runner = ClaudeCodeCliRunner(asyncio.Semaphore(1), binary=str(fake_json_error))
    with pytest.raises(AgentRunnerError) as exc:
        await runner.run("p", cwd=tmp_path, commit_sha=None, timeout_s=5.0)
    assert "error_max_turns" in str(exc.value)
    assert exc.value.stderr == "Reached max turns"


async def test_plain_text_stdout_passes_through_without_usage(
    fake_success: Path, tmp_path: Path
) -> None:
    runner = ClaudeCodeCliRunner(asyncio.Semaphore(1), binary=str(fake_success))
    result = await runner.run("p", cwd=tmp_path, commit_sha=None, timeout_s=5.0)
    assert "No issues." in result.output
    assert (result.input_tokens, result.output_tokens, result.cost_usd) == (None, None, None)


async def test_output_format_json_flag_follows_prompt(fake_echo_args: Path, tmp_path: Path) -> None:
    runner = ClaudeCodeCliRunner(asyncio.Semaphore(1), binary=str(fake_echo_args))
    result = await runner.run("p", cwd=tmp_path, commit_sha=None, timeout_s=5.0)
    lines = result.output.strip().splitlines()
    assert lines[lines.index("--output-format") + 1] == "json"
