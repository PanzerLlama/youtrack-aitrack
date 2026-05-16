"""JsonRunStore — RunStore adapter persisting RunReports as JSON files on disk."""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from pathlib import Path

from youtrack_aitrack.domain.run import RunReport

_CURSOR_FILENAME = ".cursor.json"
_IDEMPOTENCY_FILENAME = ".idempotency.json"
# run_id flows into a path component. Reject any character that could cause
# directory traversal or escape the runs root. uuid4 hex (the canonical shape
# produced by RunReport) matches; alphanumeric + `_-` test fixtures match too.
_RUN_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


class JsonRunStoreError(RuntimeError):
    """Raised on corrupt JSON or unexpected on-disk shape in JsonRunStore."""


class JsonRunStore:
    def __init__(self, runs_dir: Path) -> None:
        self._runs_dir = runs_dir

    def save_run(self, report: RunReport) -> None:
        date = datetime.now(UTC).strftime("%Y-%m-%d")
        path = self._runs_dir / date / f"{report.run_id}.json"
        _atomic_write(path, report.model_dump_json())

    def load_run(self, run_id: str) -> RunReport | None:
        if not _RUN_ID_RE.match(run_id):
            return None
        if not self._runs_dir.is_dir():
            return None
        for date_dir in sorted(self._runs_dir.iterdir(), reverse=True):
            if not date_dir.is_dir() or date_dir.name.startswith("."):
                continue
            candidate = date_dir / f"{run_id}.json"
            if candidate.is_file():
                try:
                    return RunReport.model_validate_json(candidate.read_text())
                except ValueError as exc:
                    raise JsonRunStoreError(f"corrupt run file: {candidate}") from exc
        return None

    def save_cursor(self, token: str | None) -> None:
        path = self._runs_dir / _CURSOR_FILENAME
        _atomic_write(path, json.dumps({"cursor": token}))

    def load_cursor(self) -> str | None:
        path = self._runs_dir / _CURSOR_FILENAME
        if not path.is_file():
            return None
        try:
            data = json.loads(path.read_text())
        except ValueError as exc:
            raise JsonRunStoreError(f"corrupt cursor file: {path}") from exc
        if not isinstance(data, dict) or "cursor" not in data:
            raise JsonRunStoreError(f"unexpected cursor file shape: {path}")
        value = data["cursor"]
        if value is None or isinstance(value, str):
            return value
        raise JsonRunStoreError(f"cursor must be str or null, got {type(value).__name__}")

    def has_processed(self, key: str) -> bool:
        return key in self._load_idempotency()

    def mark_processed(self, key: str, run_id: str) -> None:
        seen = self._load_idempotency()
        seen[key] = run_id
        path = self._runs_dir / _IDEMPOTENCY_FILENAME
        _atomic_write(path, json.dumps({"seen": seen}))

    def _load_idempotency(self) -> dict[str, str]:
        path = self._runs_dir / _IDEMPOTENCY_FILENAME
        if not path.is_file():
            return {}
        try:
            data = json.loads(path.read_text())
        except ValueError as exc:
            raise JsonRunStoreError(f"corrupt idempotency file: {path}") from exc
        if not isinstance(data, dict) or "seen" not in data:
            raise JsonRunStoreError(f"unexpected idempotency file shape: {path}")
        seen = data["seen"]
        if not isinstance(seen, dict) or not all(
            isinstance(k, str) and isinstance(v, str) for k, v in seen.items()
        ):
            raise JsonRunStoreError(f"idempotency 'seen' must map str->str: {path}")
        return dict(seen)


def _atomic_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(content)
    tmp.replace(path)
