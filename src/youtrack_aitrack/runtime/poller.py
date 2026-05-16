"""Poller — cursor-driven loop that fetches IssueEvents and dispatches through Runner."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from youtrack_aitrack.config.instance import InstanceConfig
from youtrack_aitrack.domain.run import RunReport
from youtrack_aitrack.engine.run_store import RunStore
from youtrack_aitrack.runtime.runner import ActivityFeed, Runner, wire


class IssueTagsLookup(Protocol):
    async def get_issue_tags(self, issue_id: str) -> list[str]: ...


@dataclass(frozen=True)
class PollResult:
    cursor_before: str | None
    cursor_after: str | None
    event_count: int
    events_filtered: int
    reports: list[RunReport]


class Poller:
    def __init__(
        self,
        *,
        runner: Runner,
        run_store: RunStore,
        activity_feed: ActivityFeed,
        tags_lookup: IssueTagsLookup,
        include_tags: list[str] | None = None,
    ) -> None:
        self._runner = runner
        self._run_store = run_store
        self._feed = activity_feed
        self._tags_lookup = tags_lookup
        self._include_tags: set[str] = set(include_tags or [])

    async def poll_once(self) -> PollResult:
        cursor_before = self._run_store.load_cursor()
        events, cursor_after = await self._feed.changed_issues_since(cursor_before)
        reports: list[RunReport] = []
        filtered = 0
        for event in events:
            if self._include_tags and not await self._event_matches_tags(event.issue_id):
                filtered += 1
                continue
            reports.extend(await self._runner.dispatch(event))
        self._run_store.save_cursor(cursor_after)
        return PollResult(
            cursor_before=cursor_before,
            cursor_after=cursor_after,
            event_count=len(events),
            events_filtered=filtered,
            reports=reports,
        )

    async def _event_matches_tags(self, issue_id: str) -> bool:
        tags = await self._tags_lookup.get_issue_tags(issue_id)
        return any(t in self._include_tags for t in tags)

    async def poll_loop(
        self,
        *,
        interval_seconds: float,
        stop: asyncio.Event,
        on_iteration: Callable[[PollResult], None] = lambda _r: None,
        max_iterations: int | None = None,
    ) -> int:
        count = 0
        while not stop.is_set():
            if max_iterations is not None and count >= max_iterations:
                break
            result = await self.poll_once()
            on_iteration(result)
            count += 1
            if stop.is_set():
                break
            if max_iterations is not None and count >= max_iterations:
                break
            try:
                await asyncio.wait_for(stop.wait(), timeout=interval_seconds)
            except TimeoutError:
                continue
        return count


def build_poller(
    config: InstanceConfig,
    config_dir: Path,
    *,
    repo_dir: Path | None = None,
    dry_run: bool = False,
    stub_llm: bool = False,
) -> Poller:
    w = wire(
        config,
        config_dir,
        repo_dir=repo_dir,
        dry_run=dry_run,
        stub_llm=stub_llm,
        workflow_names=None,
    )
    runner = Runner(
        config=w.config,
        workflows=w.workflows,
        engine=w.engine,
        git_provider=w.git,
        repo_dir=w.repo_dir,
        run_store=w.run_store,
        state_lookup=w.yt,
    )
    return Poller(
        runner=runner,
        run_store=w.run_store,
        activity_feed=w.yt,
        tags_lookup=w.yt,
        include_tags=list(config.defaults.include_tags),
    )
