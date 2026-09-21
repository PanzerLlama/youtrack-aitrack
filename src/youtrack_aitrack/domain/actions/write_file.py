"""WriteFileAction — persist an upstream action's text output as a file in the repo."""

from __future__ import annotations

from pathlib import Path, PurePosixPath
from typing import Any, Literal, Protocol

from pydantic import PrivateAttr

from youtrack_aitrack.domain.action import ActionSpec
from youtrack_aitrack.domain.context import Context
from youtrack_aitrack.domain.run import ActionResult
from youtrack_aitrack.registry import register_action


class RepoFileWriter(Protocol):
    def write_text(self, repo_dir: Path, relative_path: PurePosixPath, text: str) -> None: ...

    def commit_paths(self, repo_dir: Path, paths: list[PurePosixPath], message: str) -> str: ...


class _NoOpRepoFileWriter:
    def write_text(self, repo_dir: Path, relative_path: PurePosixPath, text: str) -> None:
        return None

    def commit_paths(self, repo_dir: Path, paths: list[PurePosixPath], message: str) -> str:
        return ""


@register_action("write_file")
class WriteFileAction(ActionSpec):
    """Write ``ctx.action_outputs[source].output['text']`` to ``path`` (relative to the repo).

    ``{task_id}`` is substituted in both ``path`` and ``commit_message``. When a
    commit message is given the file is committed on the current branch.
    """

    type: Literal["write_file"] = "write_file"
    source: str
    path: str
    commit_message: str | None = None

    _writer: RepoFileWriter = PrivateAttr()

    def __init__(self, *, writer: RepoFileWriter | None = None, **data: Any) -> None:
        super().__init__(**data)
        self._writer = writer if writer is not None else _NoOpRepoFileWriter()

    async def execute(self, ctx: Context) -> ActionResult:
        text = _source_text(ctx, self.source)
        if text is None:
            return ActionResult(
                action_id=self.id,
                success=False,
                error=f"source action {self.source!r} produced no text output",
            )
        task_id = ctx.issue.issue_id
        try:
            rel = _safe_relative_path(self.path.replace("{task_id}", task_id))
        except ValueError as exc:
            return ActionResult(action_id=self.id, success=False, error=str(exc))
        repo = ctx.repo_path if ctx.repo_path is not None else Path(".")
        self._writer.write_text(repo, rel, text)
        sha: str | None = None
        if self.commit_message is not None:
            message = self.commit_message.replace("{task_id}", task_id)
            sha = self._writer.commit_paths(repo, [rel], message)
        note = f"wrote {rel}" + (f"; committed {sha[:10]}" if sha else "")
        return ActionResult(
            action_id=self.id,
            success=True,
            output={"path": str(rel), "committed_sha": sha, "note": note},
        )


def _source_text(ctx: Context, source: str) -> str | None:
    result = ctx.action_outputs.get(source)
    if result is None or result.output is None:
        return None
    text = result.output.get("text")
    return text if isinstance(text, str) else None


def _safe_relative_path(raw: str) -> PurePosixPath:
    path = PurePosixPath(raw)
    if path.is_absolute() or ".." in path.parts or not path.parts:
        raise ValueError(f"write_file path must be relative and stay inside the repo: {raw!r}")
    return path
