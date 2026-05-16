"""Tests for JsonRunStore adapter."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from youtrack_aitrack.adapters.storage.runs import JsonRunStore, JsonRunStoreError
from youtrack_aitrack.domain.run import ActionResult, RunReport, RunState
from youtrack_aitrack.engine.idempotency import IdempotencyStore
from youtrack_aitrack.engine.run_store import RunStore


def _accepts_store(s: RunStore) -> RunStore:
    return s


def _accepts_idempotency(s: IdempotencyStore) -> IdempotencyStore:
    return s


def _make_report(*, run_id: str | None = None, workflow: str = "wf") -> RunReport:
    kwargs: dict[str, object] = {"workflow_name": workflow, "state": RunState.DONE}
    if run_id is not None:
        kwargs["run_id"] = run_id
    return RunReport(**kwargs)  # type: ignore[arg-type]


def _today() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%d")


def test_adapter_satisfies_run_store_protocol(tmp_path: Path) -> None:
    store = JsonRunStore(tmp_path)
    accepted = _accepts_store(store)
    assert accepted is store


def test_save_run_writes_to_dated_subdir(tmp_path: Path) -> None:
    store = JsonRunStore(tmp_path)
    report = _make_report(run_id="abc123")
    store.save_run(report)
    expected = tmp_path / _today() / "abc123.json"
    assert expected.is_file()


def test_save_run_atomic_leaves_no_tmp_file(tmp_path: Path) -> None:
    store = JsonRunStore(tmp_path)
    store.save_run(_make_report(run_id="rid"))
    leftovers = list(tmp_path.rglob("*.tmp"))
    assert leftovers == []


def test_save_run_overwrites_same_run_id(tmp_path: Path) -> None:
    store = JsonRunStore(tmp_path)
    r1 = RunReport(run_id="same", workflow_name="wf", state=RunState.DONE)
    r2 = RunReport(run_id="same", workflow_name="wf", state=RunState.FAILED)
    store.save_run(r1)
    store.save_run(r2)
    loaded = store.load_run("same")
    assert loaded is not None
    assert loaded.state == RunState.FAILED


def test_save_and_load_run_round_trip_preserves_fields(tmp_path: Path) -> None:
    store = JsonRunStore(tmp_path)
    report = RunReport(
        run_id="round-trip",
        workflow_name="audit",
        state=RunState.DONE,
        action_results=[
            ActionResult(action_id="a1", success=True, output={"k": "v"}, duration_ms=42)
        ],
    )
    store.save_run(report)
    loaded = store.load_run("round-trip")
    assert loaded == report


def test_load_unknown_run_returns_none(tmp_path: Path) -> None:
    store = JsonRunStore(tmp_path)
    assert store.load_run("never-saved") is None


def test_load_unknown_run_returns_none_when_runs_dir_missing(tmp_path: Path) -> None:
    store = JsonRunStore(tmp_path / "missing")
    assert store.load_run("any") is None


def test_load_run_rejects_path_traversal_run_id(tmp_path: Path) -> None:
    """run_id flows into a path component; reject metachars defensively."""
    store = JsonRunStore(tmp_path)
    for bad in ("../etc/passwd", "/abs/path", "a/b", "a\\b", "..", "a.b"):
        assert store.load_run(bad) is None, f"expected reject for {bad!r}"


def test_load_run_scans_multiple_date_dirs(tmp_path: Path) -> None:
    (tmp_path / "2026-05-09").mkdir(parents=True)
    (tmp_path / "2026-05-10").mkdir(parents=True)
    report = RunReport(run_id="rid", workflow_name="wf", state=RunState.DONE)
    (tmp_path / "2026-05-09" / "rid.json").write_text(report.model_dump_json())
    store = JsonRunStore(tmp_path)
    assert store.load_run("rid") == report


def test_corrupt_run_file_raises(tmp_path: Path) -> None:
    date_dir = tmp_path / _today()
    date_dir.mkdir(parents=True)
    (date_dir / "corrupt.json").write_text("{not valid json")
    store = JsonRunStore(tmp_path)
    with pytest.raises(JsonRunStoreError, match="corrupt run file"):
        store.load_run("corrupt")


def test_cursor_round_trip(tmp_path: Path) -> None:
    store = JsonRunStore(tmp_path)
    assert store.load_cursor() is None
    store.save_cursor("token-abc")
    assert store.load_cursor() == "token-abc"
    store.save_cursor("token-def")
    assert store.load_cursor() == "token-def"
    store.save_cursor(None)
    assert store.load_cursor() is None


def test_cursor_save_creates_runs_dir(tmp_path: Path) -> None:
    nested = tmp_path / "deep" / "runs"
    store = JsonRunStore(nested)
    store.save_cursor("x")
    assert (nested / ".cursor.json").is_file()


def test_cursor_atomic_leaves_no_tmp_file(tmp_path: Path) -> None:
    store = JsonRunStore(tmp_path)
    store.save_cursor("x")
    leftovers = list(tmp_path.rglob("*.tmp"))
    assert leftovers == []


def test_corrupt_cursor_raises(tmp_path: Path) -> None:
    tmp_path.mkdir(exist_ok=True)
    (tmp_path / ".cursor.json").write_text("{not valid json")
    store = JsonRunStore(tmp_path)
    with pytest.raises(JsonRunStoreError, match="corrupt cursor file"):
        store.load_cursor()


def test_cursor_unexpected_shape_raises(tmp_path: Path) -> None:
    (tmp_path / ".cursor.json").write_text('{"other_key": 1}')
    store = JsonRunStore(tmp_path)
    with pytest.raises(JsonRunStoreError, match="unexpected cursor file shape"):
        store.load_cursor()


def test_cursor_non_string_value_raises(tmp_path: Path) -> None:
    (tmp_path / ".cursor.json").write_text('{"cursor": 123}')
    store = JsonRunStore(tmp_path)
    with pytest.raises(JsonRunStoreError, match="cursor must be str or null"):
        store.load_cursor()


def test_load_run_ignores_dotfiles(tmp_path: Path) -> None:
    """The cursor file lives next to the date dirs and must not be walked into."""
    store = JsonRunStore(tmp_path)
    store.save_cursor("c")
    assert store.load_run("anything") is None


def test_adapter_satisfies_idempotency_protocol(tmp_path: Path) -> None:
    store = JsonRunStore(tmp_path)
    accepted = _accepts_idempotency(store)
    assert accepted is store


def test_has_processed_returns_false_when_file_missing(tmp_path: Path) -> None:
    store = JsonRunStore(tmp_path)
    assert store.has_processed("any-key") is False


def test_mark_then_has_processed_round_trip(tmp_path: Path) -> None:
    store = JsonRunStore(tmp_path)
    store.mark_processed("key-1", "run-abc")
    assert store.has_processed("key-1") is True
    assert store.has_processed("key-2") is False


def test_mark_processed_persists_across_instances(tmp_path: Path) -> None:
    JsonRunStore(tmp_path).mark_processed("k", "r")
    assert JsonRunStore(tmp_path).has_processed("k") is True


def test_mark_processed_appends_without_overwriting(tmp_path: Path) -> None:
    store = JsonRunStore(tmp_path)
    store.mark_processed("k1", "r1")
    store.mark_processed("k2", "r2")
    assert store.has_processed("k1") is True
    assert store.has_processed("k2") is True


def test_mark_processed_atomic_leaves_no_tmp_file(tmp_path: Path) -> None:
    store = JsonRunStore(tmp_path)
    store.mark_processed("k", "r")
    leftovers = list(tmp_path.rglob("*.tmp"))
    assert leftovers == []


def test_corrupt_idempotency_file_raises(tmp_path: Path) -> None:
    (tmp_path / ".idempotency.json").write_text("{not valid")
    store = JsonRunStore(tmp_path)
    with pytest.raises(JsonRunStoreError, match="corrupt idempotency file"):
        store.has_processed("k")


def test_idempotency_unexpected_shape_raises(tmp_path: Path) -> None:
    (tmp_path / ".idempotency.json").write_text('{"other_key": 1}')
    store = JsonRunStore(tmp_path)
    with pytest.raises(JsonRunStoreError, match="unexpected idempotency file shape"):
        store.has_processed("k")


def test_idempotency_non_string_value_raises(tmp_path: Path) -> None:
    (tmp_path / ".idempotency.json").write_text('{"seen": {"k": 1}}')
    store = JsonRunStore(tmp_path)
    with pytest.raises(JsonRunStoreError, match="seen' must map str->str"):
        store.has_processed("k")


def test_load_run_ignores_idempotency_dotfile(tmp_path: Path) -> None:
    store = JsonRunStore(tmp_path)
    store.mark_processed("k", "r")
    assert store.load_run("anything") is None
