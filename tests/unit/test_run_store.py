"""Tests for the RunStore Protocol and its in-memory default."""

from __future__ import annotations

from youtrack_aitrack.domain.run import RunReport, RunState
from youtrack_aitrack.engine.run_store import RunStore, _InMemoryRunStore


def _accepts_store(s: RunStore) -> RunStore:
    return s


def _make_report(workflow: str = "wf") -> RunReport:
    return RunReport(workflow_name=workflow, state=RunState.DONE)


def test_run_report_has_default_run_id() -> None:
    r = _make_report()
    assert isinstance(r.run_id, str)
    assert len(r.run_id) > 0


def test_run_report_run_id_is_unique() -> None:
    a = _make_report()
    b = _make_report()
    assert a.run_id != b.run_id


def test_run_report_explicit_run_id() -> None:
    r = RunReport(run_id="abc-123", workflow_name="wf", state=RunState.DONE)
    assert r.run_id == "abc-123"


def test_in_memory_store_satisfies_protocol() -> None:
    store = _InMemoryRunStore()
    accepted = _accepts_store(store)
    assert accepted is store


def test_save_and_load_run_round_trip() -> None:
    store = _InMemoryRunStore()
    report = _make_report()
    store.save_run(report)
    loaded = store.load_run(report.run_id)
    assert loaded == report


def test_load_unknown_run_returns_none() -> None:
    store = _InMemoryRunStore()
    assert store.load_run("missing") is None


def test_cursor_round_trip() -> None:
    store = _InMemoryRunStore()
    assert store.load_cursor() is None
    store.save_cursor("cursor-abc")
    assert store.load_cursor() == "cursor-abc"
    store.save_cursor(None)
    assert store.load_cursor() is None
