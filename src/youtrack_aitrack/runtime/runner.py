"""Runner — resolve repo state, build context, dispatch through the engine."""

from __future__ import annotations

import asyncio
import os
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol

from youtrack_aitrack.adapters.cli.claude_code import ClaudeCodeCliRunner
from youtrack_aitrack.adapters.git.diff import GitDiffAdapter, GitDiffError
from youtrack_aitrack.adapters.llm.anthropic import AnthropicAgentRunner, AnthropicLLMClient
from youtrack_aitrack.adapters.llm.jinja import JinjaPromptRenderer
from youtrack_aitrack.adapters.storage.runs import JsonRunStore
from youtrack_aitrack.adapters.youtrack.client import YouTrackClient
from youtrack_aitrack.config.instance import InstanceConfig
from youtrack_aitrack.config.loader import load_workflow
from youtrack_aitrack.domain.agent_runner import AgentRunner
from youtrack_aitrack.domain.event import IssueEvent
from youtrack_aitrack.domain.inputs import GitDiffProvider
from youtrack_aitrack.domain.run import RunReport
from youtrack_aitrack.domain.workflow import Workflow
from youtrack_aitrack.engine import WorkflowEngine
from youtrack_aitrack.engine.idempotency import IdempotencyStore
from youtrack_aitrack.engine.run_store import RunStore
from youtrack_aitrack.runtime.factory import (
    ActionFactory,
    NoOpCommentPoster,
    NoOpFieldWriter,
    StandardOutputSink,
    StubAgentRunner,
)


class IssueStateLookup(Protocol):
    async def get_issue_state(self, issue_id: str) -> str | None: ...


class ActivityFeed(Protocol):
    async def changed_issues_since(
        self, cursor: str | None
    ) -> tuple[list[IssueEvent], str | None]: ...


@dataclass(frozen=True)
class Wiring:
    """All adapters + workflows composed for one instance — shared by Runner and Poller."""

    config: InstanceConfig
    yt: YouTrackClient
    run_store: JsonRunStore
    git: GitDiffAdapter
    engine: WorkflowEngine
    workflows: list[Workflow]
    repo_dir: Path


class Runner:
    def __init__(
        self,
        *,
        config: InstanceConfig,
        workflows: list[Workflow],
        engine: WorkflowEngine,
        git_provider: GitDiffProvider,
        repo_dir: Path,
        run_store: RunStore,
        state_lookup: IssueStateLookup,
    ) -> None:
        self._config = config
        self._workflows = workflows
        self._engine = engine
        self._git = git_provider
        self._repo_dir = repo_dir
        self._run_store = run_store
        self._state = state_lookup

    async def dispatch(self, event: IssueEvent, *, force: bool = False) -> list[RunReport]:
        branch, diff, commit_sha, unavailable = self._resolve_repo_state(event.issue_id)
        reports = await self._engine.dispatch(
            event,
            self._workflows,
            unavailable_inputs=unavailable,
            commit_sha=commit_sha,
            branch=branch,
            diff=diff,
            base_url=self._config.defaults.base_url,
            repo_path=self._repo_dir,
            force=force,
        )
        for report in reports:
            self._run_store.save_run(report)
        return reports

    async def run(self, issue_id: str, *, force: bool = False) -> list[RunReport]:
        current_state = await self._state.get_issue_state(issue_id)
        event = IssueEvent(
            issue_id=issue_id,
            project=self._config.youtrack.project,
            event_kind="status_change",
            from_state=None,
            to_state=current_state,
            timestamp=datetime.now(UTC),
        )
        return await self.dispatch(event, force=force)

    def _resolve_repo_state(
        self, issue_id: str
    ) -> tuple[str | None, str | None, str | None, set[str]]:
        pattern = self._config.defaults.branch_pattern
        try:
            branch = self._git.resolve_branch(issue_id, repo_dir=self._repo_dir, pattern=pattern)
        except GitDiffError:
            return None, None, None, {"git_diff"}
        if branch is None:
            return None, None, None, {"git_diff"}
        try:
            diff = self._git.diff(
                self._repo_dir, branch, base=self._config.defaults.git_base_branch
            )
            commit_sha = self._git.commit_sha(self._repo_dir, branch)
        except GitDiffError:
            return branch, None, None, {"git_diff"}
        return branch, diff, commit_sha, set()


def wire(
    config: InstanceConfig,
    config_dir: Path,
    *,
    repo_dir: Path | None = None,
    dry_run: bool = False,
    stub_llm: bool = False,
    workflow_names: set[str] | None = None,
) -> Wiring:
    yt = YouTrackClient(
        config.youtrack.url,
        config.youtrack.token,
        project=config.youtrack.project,
        poll_lookback_seconds=config.defaults.poll_lookback_seconds,
    )
    agents = _build_agents(config, stub_llm=stub_llm)
    renderer = JinjaPromptRenderer(config.prompts_path(config_dir))
    git = GitDiffAdapter()
    run_store = JsonRunStore(config.runs_path(config_dir))
    writer = NoOpFieldWriter() if dry_run else yt
    poster = NoOpCommentPoster() if dry_run else yt
    factory = ActionFactory(
        agents=agents,
        default_agent=config.defaults.default_agent,
        renderer=renderer,
        writer=writer,
        poster=poster,
        agent_timeout_seconds=float(config.defaults.agent_timeout_seconds),
    )
    workflows = [
        factory.materialize_workflow(w) for w in _load_workflows(config, config_dir, workflow_names)
    ]
    output_sink = StandardOutputSink(writer=writer, poster=poster)
    engine = WorkflowEngine(
        idempotency_store=_as_idempotency_store(run_store),
        output_sink=output_sink,
    )
    return Wiring(
        config=config,
        yt=yt,
        run_store=run_store,
        git=git,
        engine=engine,
        workflows=workflows,
        repo_dir=repo_dir if repo_dir is not None else Path.cwd(),
    )


def build_runner(
    config: InstanceConfig,
    config_dir: Path,
    *,
    repo_dir: Path | None = None,
    dry_run: bool = False,
    stub_llm: bool = False,
    workflow_names: set[str] | None = None,
) -> Runner:
    w = wire(
        config,
        config_dir,
        repo_dir=repo_dir,
        dry_run=dry_run,
        stub_llm=stub_llm,
        workflow_names=workflow_names,
    )
    return Runner(
        config=w.config,
        workflows=w.workflows,
        engine=w.engine,
        git_provider=w.git,
        repo_dir=w.repo_dir,
        run_store=w.run_store,
        state_lookup=w.yt,
    )


def _load_workflows(
    config: InstanceConfig,
    config_dir: Path,
    names: set[str] | None,
) -> list[Workflow]:
    workflows_dir = config.workflows_path(config_dir)
    if not workflows_dir.is_dir():
        return []
    workflows = [load_workflow(p) for p in sorted(workflows_dir.glob("*.yaml"))]
    if names is None:
        return workflows
    return [w for w in workflows if w.name in names]


def _as_idempotency_store(store: JsonRunStore) -> IdempotencyStore:
    return store


def _build_agents(config: InstanceConfig, *, stub_llm: bool) -> dict[str, AgentRunner]:
    """Construct the AgentRunner registry for this instance.

    With ``stub_llm=True`` every registered backend is the same StubAgentRunner
    so workflows can be exercised without spending tokens or shelling out, no
    matter which ``agent`` they declare. Otherwise both real backends are
    registered eagerly; the CLI runner's subprocess is only spawned on actual
    invocation, so registering it costs nothing if no workflow uses it.

    When ``cli_agent_mode='bare'`` the CLI runner is constructed with
    ``bare=True`` and ANTHROPIC_API_KEY pushed into its subprocess env, so
    spawned ``claude --bare -p`` calls skip local CLAUDE.md / hooks / plugins
    and authenticate via the API key instead of the user's OAuth keychain.
    This is the daemon-friendly mode: deterministic small input, predictable
    per-call token cost, no leakage of developer-local context. Bare mode
    requires a non-empty api_key — wire() fails loudly here rather than
    waiting for the first spawn to crash.
    """
    if stub_llm:
        stub = StubAgentRunner()
        return {"anthropic_api": stub, "claude_code_cli": stub}
    anthropic_runner = AnthropicAgentRunner(
        AnthropicLLMClient(config.anthropic.api_key),
        default_model=config.anthropic.default_model,
    )
    cli_runner = _build_cli_runner(config)
    return {"anthropic_api": anthropic_runner, "claude_code_cli": cli_runner}


def _build_cli_runner(config: InstanceConfig) -> ClaudeCodeCliRunner:
    semaphore = asyncio.Semaphore(config.defaults.cli_agent_concurrency)
    if config.defaults.cli_agent_mode == "bare":
        if not config.anthropic.api_key:
            raise ValueError(
                "cli_agent_mode='bare' requires anthropic.api_key to be set "
                "(bare mode authenticates the spawned `claude` subprocess via "
                "ANTHROPIC_API_KEY, not OAuth). Either set the api_key or "
                "switch cli_agent_mode to 'oauth'."
            )
        env = {**os.environ, "ANTHROPIC_API_KEY": config.anthropic.api_key}
        return ClaudeCodeCliRunner(semaphore, bare=True, env=env)
    return ClaudeCodeCliRunner(semaphore)
