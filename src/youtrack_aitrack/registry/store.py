"""Generic name-to-class registry used for plugin types."""

from __future__ import annotations

from collections.abc import Callable

from pydantic import BaseModel


class Registry[T: BaseModel]:
    def __init__(self, kind: str) -> None:
        self._kind = kind
        self._items: dict[str, type[T]] = {}

    def register(self, name: str) -> Callable[[type[T]], type[T]]:
        def decorator(cls: type[T]) -> type[T]:
            if name in self._items:
                raise ValueError(
                    f"{self._kind} {name!r} already registered "
                    f"(existing: {self._items[name].__name__})"
                )
            self._items[name] = cls
            return cls

        return decorator

    def get(self, name: str) -> type[T]:
        if name not in self._items:
            raise KeyError(
                f"unknown {self._kind} type {name!r}; available: {sorted(self._items.keys())}"
            )
        return self._items[name]

    def names(self) -> list[str]:
        return sorted(self._items.keys())

    def snapshot(self) -> dict[str, type[T]]:
        return dict(self._items)

    def restore(self, snapshot: dict[str, type[T]]) -> None:
        self._items = dict(snapshot)

    def clear(self) -> None:
        self._items.clear()
