"""Type-level checks for the AgentRunner Protocol."""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from youtrack_aitrack.domain.agent_runner import (
    AgentResult,
    AgentRunner,
    AgentRunnerError,
)


class _Compliant:
    async def run(
        self,
        prompt: str,
        *,
        cwd: Path,
        commit_sha: str | None,
        timeout_s: float,
    ) -> AgentResult:
        return AgentResult(output=prompt, exit_code=0, duration_s=0.0)


class _MissingMethod:
    """Lacks the run() method entirely."""

    async def complete(self, prompt: str) -> str:
        return prompt


def test_compliant_object_satisfies_protocol() -> None:
    assert isinstance(_Compliant(), AgentRunner)


def test_object_missing_run_method_does_not_satisfy_protocol() -> None:
    # runtime_checkable Protocols only check method *presence*, not signatures.
    # This guards against accidental removal of the method, not signature drift.
    assert not isinstance(_MissingMethod(), AgentRunner)


def test_agent_result_is_frozen() -> None:
    result = AgentResult(output="hello", exit_code=0, duration_s=1.5)
    with pytest.raises(ValidationError):
        result.output = "mutated"  # type: ignore[misc]


def test_agent_runner_error_carries_stderr() -> None:
    err = AgentRunnerError("boom", stderr="diag")
    assert str(err) == "boom"
    assert err.stderr == "diag"


def test_agent_runner_error_stderr_optional() -> None:
    err = AgentRunnerError("boom")
    assert err.stderr is None
