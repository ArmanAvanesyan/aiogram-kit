"""Bounded in-process repository bookkeeping, never application business state."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass, field, fields, is_dataclass
from enum import Enum
from functools import lru_cache
from typing import Literal, Protocol, cast

from aiogram_coordination import ExternalSession

from .._json_scope import selected
from ..engine import CanonicalCore, EngineName, native_core, require_engine
from ..models import (
    CommitResult,
    ConversationKey,
    EffectCheckpoint,
    HistoryEntry,
    MessageRef,
    NavigationIntent,
    NavigationMutation,
    NavigationToken,
    PreparedAction,
    RenderResult,
    VersionedSnapshot,
    ViewState,
)


def _canonical(value: object) -> object:
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, ViewState) and value.render_status == "complete":
        value = RenderResult(
            value.view_id,
            value.messages,
            value.reply_keyboard_key,
            value.locale,
            value.reply_keyboard_locale,
        )
    if is_dataclass(value) and not isinstance(value, type):
        return {item.name: _canonical(getattr(value, item.name)) for item in fields(value)}
    if isinstance(value, Mapping):
        return {
            str(key): _canonical(child)
            for key, child in cast(Mapping[object, object], value).items()
        }
    if isinstance(value, (tuple, list)):
        return [_canonical(child) for child in cast(tuple[object, ...], value)]
    return value


def payload_size(value: object) -> int:
    return len(
        json.dumps(
            _canonical(value), ensure_ascii=False, separators=(",", ":"), allow_nan=False
        ).encode()
    )


@lru_cache(maxsize=1)
def canonicalizer() -> CanonicalCore:
    return native_core().Canonicalizer(
        Enum,
        Mapping,
        fields,
        None,
        ViewState,
        RenderResult,
        (
            ConversationKey,
            EffectCheckpoint,
            HistoryEntry,
            MessageRef,
            NavigationIntent,
            NavigationMutation,
            RenderResult,
            ViewState,
        ),
    )


class _FingerprintCall(Protocol):
    def __call__(self, value: object) -> str: ...


class _FreezeCall(Protocol):
    def __call__(self, value: object, proxy: object, style: str) -> tuple[object, int] | None: ...


class _DeferredCanonicalizer:
    """Backend-owned codec, allocated only when pure JSON work is requested.

    Redis read projections use the same memory reducer but often do not perform
    any fingerprint/freezing work. Creating twenty metadata references and a
    native cache for each such read is unnecessary. No native result or mutable
    record is shared between backends, and ABI checks remain eager in the owner.
    """

    def __init__(self) -> None:
        self._loaded: CanonicalCore | None = None
        self.fingerprint: _FingerprintCall = self._fingerprint
        self.freeze: _FreezeCall = self._freeze

    def _core(self) -> CanonicalCore:
        if self._loaded is None:
            self._loaded = canonicalizer().fork()
            # Pay the deferred dispatch once, not on each hot-path operation.
            self.fingerprint = self._loaded.fingerprint
            self.freeze = self._loaded.freeze
        return self._loaded

    def fork(self) -> CanonicalCore:
        return _DeferredCanonicalizer()

    def _fingerprint(self, value: object) -> str:
        return self._core().fingerprint(value)

    def _freeze(self, value: object, proxy: object, style: str) -> tuple[object, int] | None:
        return self._core().freeze(value, proxy, style)

    def clear_cache(self) -> None:
        if self._loaded is not None:
            self._loaded.clear_cache()

    def cache_stats(self) -> tuple[int, int]:
        return self._loaded.cache_stats() if self._loaded is not None else (0, 0)


def new_canonicalizer() -> CanonicalCore:
    return _DeferredCanonicalizer()


def fingerprint(value: object, *, engine: EngineName = "python") -> str:
    require_engine(engine)
    if engine == "rust":
        processor = selected()
        return (processor.core if processor else canonicalizer()).fingerprint(value)
    raw = json.dumps(_canonical(value), sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(raw.encode()).hexdigest()


@dataclass
class Operation:
    fingerprint: str
    prepared: PreparedAction | None
    status: Literal["prepared", "completed", "unknown", "failed"] = "prepared"
    result: CommitResult | None = None
    retention_until: int = 0
    completion_fingerprint: str | None = None
    token_receipts: dict[str, TokenRecord] = field(default_factory=lambda: dict[str, TokenRecord]())


@dataclass
class TokenRecord:
    token: NavigationToken
    operation_id: str
    fingerprint: str
    consumed_by: str | None = None


@dataclass
class Conversation:
    version: str
    expiry_heap: list[tuple[int, str]] = field(
        default_factory=lambda: list[tuple[int, str]](), kw_only=True
    )
    unloaded_operations: int = field(default=0, kw_only=True)
    host_session: tuple[str, int] | None = field(default=None, kw_only=True)
    views: dict[tuple[str, str], str] = field(
        default_factory=lambda: dict[tuple[str, str], str](), kw_only=True
    )
    external_session: ExternalSession | None = field(default=None, kw_only=True)
    current: VersionedSnapshot | None = None
    pending_id: str | None = None
    operations: dict[str, Operation] = field(default_factory=lambda: dict[str, Operation]())
    tokens: dict[str, TokenRecord] = field(default_factory=lambda: dict[str, TokenRecord]())
