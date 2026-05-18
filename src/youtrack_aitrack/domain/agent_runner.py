"""AgentRunner — abstract interface for AI agent backends.

An AgentRunner runs a rendered prompt against an AI agent that may have
access to the project's working tree. Implementations may shell out to a
local CLI (claude, codex, gemini) or call a remote SDK; the engine treats
them identically through this Protocol.

The signature carries cwd + commit_sha so that working-tree-aware backends
(CLI runners) can inspect the project directly rather than receive a
pre-embedded diff. SDK-style backends (Anthropic API) accept these args
and discard them. ``model`` lets the caller pass the per-action model
choice through to backends that select model per-call (SDK) while CLI
runners may map it to a ``--model`` flag.

AgentResult carries subprocess-style metadata (exit code, duration, model
used) so the engine has uniform observability across backends.
"""

from __future__ import annotations

from pathlib import Path
from typing import Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict


class AgentResult(BaseModel):
    """Outcome of a single AgentRunner invocation."""

    model_config = ConfigDict(frozen=True)

    output: str
    exit_code: int
    duration_s: float
    model_used: str | None = None


class AgentRunnerError(Exception):
    """Raised when an AgentRunner cannot produce a result.

    Wraps subprocess failures, timeouts, missing binaries, and unparseable
    output so the engine sees a single exception type regardless of backend.
    The agent's stderr (if any) lives in `stderr`; consumers may log it but
    must not depend on its contents structurally.
    """

    def __init__(self, message: str, *, stderr: str | None = None) -> None:
        super().__init__(message)
        self.stderr = stderr


@runtime_checkable
class AgentRunner(Protocol):
    async def run(
        self,
        prompt: str,
        *,
        cwd: Path,
        commit_sha: str | None,
        timeout_s: float,
        model: str | None = None,
    ) -> AgentResult: ...
