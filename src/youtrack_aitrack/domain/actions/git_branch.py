"""GitBranchAction — create (or re-enter) the issue's feature branch and switch to it."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Literal, Protocol

from pydantic import PrivateAttr

from youtrack_aitrack.domain.action import ActionSpec
from youtrack_aitrack.domain.branch_name import DEFAULT_BRANCH_TEMPLATE, build_branch_name
from youtrack_aitrack.domain.context import Context
from youtrack_aitrack.domain.run import ActionResult
from youtrack_aitrack.registry import register_action


class BranchCreator(Protocol):
    def current_branch(self, repo_dir: Path) -> str | None: ...

    def has_branch(self, repo_dir: Path, name: str) -> bool: ...

    def is_clean(self, repo_dir: Path) -> bool: ...

    def create_branch(self, repo_dir: Path, name: str, *, base: str) -> None: ...

    def switch(self, repo_dir: Path, name: str) -> None: ...


class _NoOpBranchCreator:
    def current_branch(self, repo_dir: Path) -> str | None:
        return None

    def has_branch(self, repo_dir: Path, name: str) -> bool:
        return False

    def is_clean(self, repo_dir: Path) -> bool:
        return True

    def create_branch(self, repo_dir: Path, name: str, *, base: str) -> None:
        return None

    def switch(self, repo_dir: Path, name: str) -> None:
        return None


@register_action("git_branch")
class GitBranchAction(ActionSpec):
    """Idempotent: an existing branch is switched to, a missing one is created from ``base``.

    ``base`` unset means "the instance's configured base branch", injected by the
    runtime as ``default_base`` (falls back to ``main``).

    Switching requires a clean tracked tree so a checkout never clobbers local
    edits; being already on the target branch needs no switch and is always fine.
    """

    type: Literal["git_branch"] = "git_branch"
    base: str | None = None
    name: str = DEFAULT_BRANCH_TEMPLATE
    checkout: bool = True

    _git: BranchCreator = PrivateAttr()
    _default_base: str = PrivateAttr()

    def __init__(
        self,
        *,
        git: BranchCreator | None = None,
        default_base: str = "main",
        **data: Any,
    ) -> None:
        super().__init__(**data)
        self._git = git if git is not None else _NoOpBranchCreator()
        self._default_base = default_base

    async def execute(self, ctx: Context) -> ActionResult:
        repo = ctx.repo_path if ctx.repo_path is not None else Path(".")
        summary = ctx.issue_details.summary if ctx.issue_details is not None else None
        try:
            branch = build_branch_name(self.name, task_id=ctx.issue.issue_id, summary=summary)
        except ValueError as exc:
            return ActionResult(action_id=self.id, success=False, error=str(exc))
        base = self.base if self.base is not None else self._default_base
        exists = self._git.has_branch(repo, branch)
        if self._needs_switch(repo, branch) and not self._git.is_clean(repo):
            return ActionResult(
                action_id=self.id,
                success=False,
                error=(
                    "working tree has uncommitted changes; "
                    f"commit or stash before switching to {branch!r}"
                ),
            )
        if not exists:
            self._git.create_branch(repo, branch, base=base)
        if self.checkout:
            self._git.switch(repo, branch)
        return ActionResult(
            action_id=self.id,
            success=True,
            output={
                "branch": branch,
                "created": not exists,
                "base": base,
                "checked_out": self.checkout,
                "note": _note(branch, created=not exists, base=base, checkout=self.checkout),
            },
        )

    def _needs_switch(self, repo: Path, branch: str) -> bool:
        return self.checkout and self._git.current_branch(repo) != branch


def _note(branch: str, *, created: bool, base: str, checkout: bool) -> str:
    verb = f"created {branch} from {base}" if created else f"reused existing {branch}"
    return f"{verb}; switched to it" if checkout else verb
