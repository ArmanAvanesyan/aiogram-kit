"""Task-owned pure-data codec scope; never grants coordinator ownership."""

from __future__ import annotations

import asyncio
from contextvars import ContextVar, Token
from dataclasses import dataclass
from typing import Protocol


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
    # Copied contexts may outlive the operation. Revocation must also release
    # the codec cache and owner task rather than merely make them inaccessible.
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
