"""Idempotency Protocol — dedup workflow runs against a logical event key."""

from __future__ import annotations

from typing import Protocol


class IdempotencyStore(Protocol):
    def has_processed(self, key: str) -> bool: ...

    def mark_processed(self, key: str, run_id: str) -> None: ...


def build_idempotency_key(
    *,
    workflow_name: str,
    issue_id: str,
    to_state: str | None,
    commit_sha: str | None,
) -> str:
    return f"{workflow_name}|{issue_id}|{to_state or ''}|{commit_sha or ''}"


class _InMemoryIdempotencyStore:
    """Test-grade in-memory store; production wiring lands in a separate issue."""

    def __init__(self) -> None:
        self._seen: dict[str, str] = {}

    def has_processed(self, key: str) -> bool:
        return key in self._seen

    def mark_processed(self, key: str, run_id: str) -> None:
        self._seen[key] = run_id
