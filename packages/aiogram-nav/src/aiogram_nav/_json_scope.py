"""Task-owned pure-data codec scope; never grants coordinator ownership."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from contextvars import ContextVar, Token
from dataclasses import dataclass
from typing import Literal, ParamSpec, Protocol, TypeVar


class JsonCore(Protocol):
    def fingerprint(self, value: object) -> str: ...
    def clear_cache(self) -> None: ...
    def cache_stats(self) -> tuple[int, int]: ...

    def freeze(self, value: object, proxy: object, style: str) -> tuple[object, int] | None: ...


@dataclass(frozen=True)
class JsonEngine:
    core: JsonCore
    invalid: type[Exception]


@dataclass
class JsonRecord:
    owner: asyncio.Task[object] | None
    engine: JsonEngine | None
    active: bool = True


_SCOPE: ContextVar[JsonRecord | None] = ContextVar("pure_json_codec", default=None)


def begin(engine: JsonEngine | None) -> tuple[Token[JsonRecord | None], JsonRecord]:
    record = JsonRecord(asyncio.current_task(), engine)
    return _SCOPE.set(record), record


def end(token: Token[JsonRecord | None], record: JsonRecord) -> None:
    record.active = False
    record.engine = None
    record.owner = None
    try:
        _SCOPE.reset(token)
    except ValueError:
        # Revocation remains effective in copied contexts, even without reset.
        pass


def active() -> bool:
    record = _SCOPE.get()
    return record is not None and record.active


def selected() -> JsonEngine | None:
    record = _SCOPE.get()
    if record is None or not record.active or record.engine is None:
        return None
    try:
        return record.engine if record.owner is asyncio.current_task() else None
    except RuntimeError:
        return None


class JsonLock(asyncio.Lock):
    """Non-reentrant backend lock; codec selection begins only after acquisition."""

    def __init__(self, processor: JsonEngine) -> None:
        super().__init__()
        self.processor = processor
        self.scope: tuple[Token[JsonRecord | None], JsonRecord] | None = None
        self._owner: asyncio.Task[object] | None = None

    async def acquire(self) -> Literal[True]:
        await super().acquire()
        try:
            self.scope = begin(self.processor)
            self._owner = self.scope[1].owner
        except BaseException:
            super().release()
            raise
        return True

    def release(self) -> None:
        if self.scope is None or self._owner is not asyncio.current_task():
            raise RuntimeError("Backend codec scope requires its owning task")
        scope, self.scope = self.scope, None
        self._owner = None
        end(*scope)
        super().release()


P = ParamSpec("P")
T = TypeVar("T")


def construct(
    processor: JsonEngine | None, factory: Callable[P, T], *args: P.args, **kwargs: P.kwargs
) -> T:
    """Select the codec for a synchronous SDK model constructor, never callbacks."""
    if processor is None:
        return factory(*args, **kwargs)
    scope = begin(processor)
    try:
        return factory(*args, **kwargs)
    finally:
        end(*scope)
