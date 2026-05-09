"""Tests for the plugin registry."""

from collections.abc import Iterator

import pytest
from pydantic import BaseModel

from youtrack_aitrack.domain.action import ActionSpec
from youtrack_aitrack.domain.trigger import TriggerSpec
from youtrack_aitrack.registry import (
    action_registry,
    register_action,
    register_trigger,
    trigger_registry,
)
from youtrack_aitrack.registry.store import Registry


class _Base(BaseModel):
    type: str


class _A(_Base):
    pass


class _B(_Base):
    pass


@pytest.fixture(autouse=True)
def _isolate_global_registries() -> Iterator[None]:
    trigger_snap = trigger_registry.snapshot()
    action_snap = action_registry.snapshot()
    trigger_registry.clear()
    action_registry.clear()
    yield
    trigger_registry.restore(trigger_snap)
    action_registry.restore(action_snap)


# --- Registry class ---


def test_registry_register_and_lookup() -> None:
    r: Registry[_Base] = Registry("thing")
    r.register("a")(_A)
    assert r.get("a") is _A


def test_registry_decorator_returns_class() -> None:
    r: Registry[_Base] = Registry("thing")
    cls = r.register("a")(_A)
    assert cls is _A


def test_registry_register_duplicate_rejected() -> None:
    r: Registry[_Base] = Registry("thing")
    r.register("a")(_A)
    with pytest.raises(ValueError) as exc:
        r.register("a")(_B)
    msg = str(exc.value)
    assert "thing" in msg
    assert "'a'" in msg
    assert "already registered" in msg


def test_registry_lookup_unknown_lists_available() -> None:
    r: Registry[_Base] = Registry("thing")
    r.register("alpha")(_A)
    r.register("beta")(_B)
    with pytest.raises(KeyError) as exc:
        r.get("gamma")
    msg = str(exc.value)
    assert "alpha" in msg
    assert "beta" in msg
    assert "gamma" in msg


def test_registry_names_returns_sorted() -> None:
    r: Registry[_Base] = Registry("thing")
    r.register("zebra")(_A)
    r.register("apple")(_B)
    assert r.names() == ["apple", "zebra"]


def test_registry_clear_resets() -> None:
    r: Registry[_Base] = Registry("thing")
    r.register("a")(_A)
    r.clear()
    assert r.names() == []


def test_registry_snapshot_restore_round_trip() -> None:
    r: Registry[_Base] = Registry("thing")
    r.register("a")(_A)
    snap = r.snapshot()
    r.clear()
    assert r.names() == []
    r.restore(snap)
    assert r.get("a") is _A


# --- Package-level instances ---


def test_register_trigger_decorator() -> None:
    @register_trigger("demo_trigger")
    class DemoTrigger(TriggerSpec):
        pass

    assert trigger_registry.get("demo_trigger") is DemoTrigger


def test_register_action_decorator() -> None:
    @register_action("demo_action")
    class DemoAction(ActionSpec):
        pass

    assert action_registry.get("demo_action") is DemoAction


def test_registries_are_independent() -> None:
    @register_trigger("only_in_trigger")
    class LonelyTrigger(TriggerSpec):
        pass

    with pytest.raises(KeyError):
        action_registry.get("only_in_trigger")
