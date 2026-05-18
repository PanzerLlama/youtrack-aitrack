"""ClaudeCodeCliRunner — invoke the Claude Code CLI as an AgentRunner backend.

Spawns `claude -p <prompt>` (or `claude --bare -p <prompt>`) as a subprocess
in the caller's working directory, captures stdout, and surfaces failures as
AgentRunnerError. Concurrency is gated by an injected asyncio.Semaphore so
that a daemon polling multiple workflows in parallel does not over-subscribe
either the user's subscription rate limits or the host's CPU.

Two auth modes, both ToS-allowed on the user's own machine (verified
2026-05-17):

- Non-bare (default): relies on the local OAuth credential written by
  `claude login`. Honors `~/.claude` and any project-level CLAUDE.md, hooks,
  plugins. After 2026-06-15 these calls draw from the Pro/Max subscription's
  Agent SDK credit pool.

- Bare: passes --bare. Skips OAuth and keychain reads, so ANTHROPIC_API_KEY
  MUST be set in the subprocess environment. Faster startup; deterministic
  (no local CLAUDE.md / hooks).
"""

from __future__ import annotations

import asyncio
import os
import time
from pathlib import Path

from youtrack_aitrack.domain.agent_runner import AgentResult, AgentRunnerError


class ClaudeCodeCliRunner:
    def __init__(
        self,
        semaphore: asyncio.Semaphore,
        *,
        binary: str = "claude",
        bare: bool = False,
        allowed_tools: str | None = None,
        env: dict[str, str] | None = None,
    ) -> None:
        if bare and not (env or os.environ).get("ANTHROPIC_API_KEY"):
            raise ValueError("ClaudeCodeCliRunner(bare=True) requires ANTHROPIC_API_KEY in env")
        self._semaphore = semaphore
        self._binary = binary
        self._bare = bare
        self._allowed_tools = allowed_tools
        self._env = env

    async def run(
        self,
        prompt: str,
        *,
        cwd: Path,
        commit_sha: str | None,
        timeout_s: float,
        model: str | None = None,
    ) -> AgentResult:
        args: list[str] = [self._binary]
        if self._bare:
            args.append("--bare")
        args.extend(["-p", prompt])
        if self._allowed_tools is not None:
            args.extend(["--allowedTools", self._allowed_tools])
        if model is not None:
            args.extend(["--model", model])

        async with self._semaphore:
            return await self._spawn(args, cwd=cwd, timeout_s=timeout_s, model=model)

    async def _spawn(
        self, args: list[str], *, cwd: Path, timeout_s: float, model: str | None
    ) -> AgentResult:
        started = time.monotonic()
        try:
            proc = await asyncio.create_subprocess_exec(
                *args,
                cwd=str(cwd),
                stdin=asyncio.subprocess.DEVNULL,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=self._env,
            )
        except FileNotFoundError as exc:
            raise AgentRunnerError(
                f"Claude Code CLI not found on PATH (binary={self._binary!r}). "
                "Install with `npm install -g @anthropic-ai/claude-code` "
                "or set binary= to the absolute path."
            ) from exc

        try:
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout_s)
        except TimeoutError as exc:
            proc.kill()
            await proc.wait()
            raise AgentRunnerError(f"Claude Code CLI exceeded timeout of {timeout_s:.0f}s") from exc

        duration_s = time.monotonic() - started
        stderr_text = stderr.decode("utf-8", errors="replace") if stderr else None

        if proc.returncode != 0:
            raise AgentRunnerError(
                f"Claude Code CLI exited with code {proc.returncode}",
                stderr=stderr_text,
            )

        return AgentResult(
            output=stdout.decode("utf-8", errors="replace"),
            exit_code=proc.returncode,
            duration_s=duration_s,
            model_used=model,
        )
