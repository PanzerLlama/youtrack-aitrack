"""Runner — resolve repo state, build context, dispatch through the engine."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from youtrack_aitrack.adapters.git.diff import GitDiffAdapter, GitDiffError
from youtrack_aitrack.adapters.llm.anthropic import AnthropicLLMClient
from youtrack_aitrack.adapters.llm.jinja import JinjaPromptRenderer
from youtrack_aitrack.adapters.storage.runs import JsonRunStore
from youtrack_aitrack.adapters.youtrack.client import YouTrackClient
from youtrack_aitrack.config.instance import InstanceConfig
from youtrack_aitrack.config.loader import load_workflow
from youtrack_aitrack.domain.event import IssueEvent
from youtrack_aitrack.domain.inputs import GitDiffProvider
from youtrack_aitrack.domain.run import RunReport
from youtrack_aitrack.domain.workflow import Workflow
from youtrack_aitrack.engine import WorkflowEngine
from youtrack_aitrack.engine.idempotency import IdempotencyStore
from youtrack_aitrack.engine.run_store import RunStore
from youtrack_aitrack.runtime.factory import ActionFactory


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
    ) -> None:
        self._config = config
        self._workflows = workflows
        self._engine = engine
        self._git = git_provider
        self._repo_dir = repo_dir
        self._run_store = run_store

    async def dispatch(self, event: IssueEvent) -> list[RunReport]:
        branch, diff, commit_sha, unavailable = self._resolve_repo_state(event.issue_id)
        reports = await self._engine.dispatch(
            event,
            self._workflows,
            unavailable_inputs=unavailable,
            commit_sha=commit_sha,
            branch=branch,
            diff=diff,
        )
        for report in reports:
            self._run_store.save_run(report)
        return reports

    async def run(self, issue_id: str) -> list[RunReport]:
        event = IssueEvent(
            issue_id=issue_id,
            project=self._config.youtrack.project,
            event_kind="manual",
            timestamp=datetime.now(UTC),
        )
        return await self.dispatch(event)

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
            diff = self._git.diff(self._repo_dir, branch)
            commit_sha = self._git.commit_sha(self._repo_dir, branch)
        except GitDiffError:
            return branch, None, None, {"git_diff"}
        return branch, diff, commit_sha, set()


def build_runner(
    config: InstanceConfig,
    config_dir: Path,
    *,
    repo_dir: Path | None = None,
) -> Runner:
    yt = YouTrackClient(config.youtrack.url, config.youtrack.token, project=config.youtrack.project)
    llm = AnthropicLLMClient(config.anthropic.api_key)
    renderer = JinjaPromptRenderer(config.prompts_path(config_dir))
    git = GitDiffAdapter()
    run_store = JsonRunStore(config.runs_path(config_dir))
    factory = ActionFactory(llm=llm, renderer=renderer, writer=yt, poster=yt)
    workflows = [factory.materialize_workflow(w) for w in _load_workflows(config, config_dir)]
    engine = WorkflowEngine(idempotency_store=_as_idempotency_store(run_store))
    return Runner(
        config=config,
        workflows=workflows,
        engine=engine,
        git_provider=git,
        repo_dir=repo_dir if repo_dir is not None else Path.cwd(),
        run_store=run_store,
    )


def _load_workflows(config: InstanceConfig, config_dir: Path) -> list[Workflow]:
    workflows_dir = config.workflows_path(config_dir)
    if not workflows_dir.is_dir():
        return []
    return [load_workflow(p) for p in sorted(workflows_dir.glob("*.yaml"))]


def _as_idempotency_store(store: JsonRunStore) -> IdempotencyStore:
    return store
