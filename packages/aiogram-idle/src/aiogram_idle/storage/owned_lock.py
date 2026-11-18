"""Backend-only task-owned lock for composing pure domain mutations atomically."""

from __future__ import annotations

import asyncio
from contextvars import Token
from typing import Literal

from .._json_scope import JsonEngine, JsonRecord, active, begin, end


class OwnedLock(asyncio.Lock):
    """Reenter only from the actual owning task, never an inherited context."""

    def __init__(self, *, processor: JsonEngine | None = None) -> None:
        super().__init__()
        self._owner: asyncio.Task[object] | None = None
        self._depth = 0
        self._processor = processor
        self._json_scope: tuple[Token[JsonRecord | None], JsonRecord] | None = None
        self.queue = _QueueScope(self)

    async def acquire(self, *, codec: bool = True) -> Literal[True]:
        task = asyncio.current_task()
        if task is not None and self._owner is task:
            self._depth += 1
            return True
        await super().acquire()
        self._owner, self._depth = task, 1
        try:
            if (codec and self._processor is not None) or active():
                self._json_scope = begin(self._processor if codec else None)
        except BaseException:
            self._owner, self._depth = None, 0
            super().release()
            raise
        return True

    def release(self) -> None:
        if self._owner is not asyncio.current_task() or self._depth < 1:
            raise RuntimeError("Backend lock release requires its owning task")
        self._depth -= 1
        if self._depth == 0:
            self._owner = None
            scope, self._json_scope = self._json_scope, None
            if scope is not None:
                end(*scope)
            super().release()


class _QueueScope:
    """Same task-owned lock, without an unused data codec for queue-only work."""

    def __init__(self, lock: OwnedLock) -> None:
        self.lock = lock

    async def __aenter__(self) -> None:
        await self.lock.acquire(codec=False)

    async def __aexit__(self, *exc: object) -> None:
        self.lock.release()
