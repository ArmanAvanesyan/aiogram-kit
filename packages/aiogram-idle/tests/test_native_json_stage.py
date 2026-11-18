"""Native JSON stages preserve immutable values, limits and task ownership."""

import asyncio
import json
from collections import UserDict
from contextvars import copy_context
from types import MappingProxyType

import pytest

from aiogram_idle._json_scope import JsonEngine, begin, end, selected
from aiogram_idle.engines import native_core
from aiogram_idle.errors import ConfigurationError
from aiogram_idle.models import freeze_object, thaw_json
from aiogram_idle.storage.receipts import canonicalizer


class Dummy:
    def freeze(self, value, proxy, style):
        raise RuntimeError("injected unknown codec failure")


@pytest.mark.asyncio
async def test_scope_is_task_owned_and_revoked_in_copies():
    engine = JsonEngine(Dummy(), ValueError)
    scope = begin(engine)
    try:
        assert selected() is engine

        async def child():
            assert selected() is None

        await asyncio.create_task(child())
        other = begin(None)
        assert selected() is None
        end(*other)
        assert selected() is engine
        inherited = copy_context()
    finally:
        end(*scope)
    assert selected() is inherited.run(selected) is None


@pytest.mark.asyncio
async def test_unknown_native_failure_never_retries_in_python():
    scope = begin(JsonEngine(Dummy(), ValueError))
    try:
        with pytest.raises(RuntimeError, match="unknown codec"):
            freeze_object({"x": 1})
    finally:
        end(*scope)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "value",
    [
        {},
        {"key": [1, True, None, -0.0, 1e-200, 2**200]},
        {"hy": "Հայերեն😀\n\x7f", "nested": {"a": (2, 3)}},
        MappingProxyType({"x": [1]}),
        UserDict({"x": [1]}),
    ],
)
async def test_freeze_matches_python_and_size_boundary(value):
    pytest.importorskip("aiogram_idle_native")
    original = freeze_object(value)
    size = len(json.dumps(thaw_json(original), ensure_ascii=True).encode())
    scope = begin(JsonEngine(canonicalizer(), native_core().InvalidJson))
    try:
        result = freeze_object(value, max_bytes=size)
        assert thaw_json(result) == thaw_json(original)
        assert type(result) is type(original) is MappingProxyType
        with pytest.raises(ConfigurationError):
            freeze_object(value, max_bytes=size - 1)
        if isinstance(value, dict):
            value.clear()
            assert thaw_json(result) == thaw_json(original)
    finally:
        end(*scope)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "value",
    [
        {"x": float("nan")},
        {"x": float("inf")},
        {"x": "\ud800"},
        {"\udfff": 1},
        {1: "invalid"},
        {"x": object()},
    ],
)
async def test_invalid_values_keep_errors(value):
    pytest.importorskip("aiogram_idle_native")
    with pytest.raises(Exception) as reference:
        freeze_object(value)
    scope = begin(JsonEngine(canonicalizer(), native_core().InvalidJson))
    try:
        with pytest.raises(type(reference.value)) as actual:
            freeze_object(value)
        assert str(actual.value) == str(reference.value)
    finally:
        end(*scope)


@pytest.mark.asyncio
async def test_custom_proxy_backing_runs_original_validator_once():
    pytest.importorskip("aiogram_idle_native")

    class Custom(UserDict):
        calls = 0

        def items(self):
            self.calls += 1
            return super().items()

    backing = Custom({"x": [1]})
    proxy = MappingProxyType(backing)
    expected = freeze_object(proxy)
    count = backing.calls
    backing.calls = 0
    scope = begin(JsonEngine(canonicalizer(), native_core().InvalidJson))
    try:
        assert thaw_json(freeze_object(proxy)) == thaw_json(expected)
        assert backing.calls == count
    finally:
        end(*scope)


@pytest.mark.asyncio
async def test_depth_and_cycles_are_bounded():
    pytest.importorskip("aiogram_idle_native")
    cycle = {}
    cycle["self"] = cycle
    scope = begin(JsonEngine(canonicalizer(), native_core().InvalidJson))
    try:
        with pytest.raises(ConfigurationError, match="nesting"):
            freeze_object(cycle)
    finally:
        end(*scope)


@pytest.mark.asyncio
async def test_codec_memo_is_owned_bounded_and_disposable():
    pytest.importorskip("aiogram_idle_native")
    from aiogram_idle.storage.receipts import new_canonicalizer

    core = new_canonicalizer()
    scope = begin(JsonEngine(core, native_core().InvalidJson))
    try:
        source = {"x": [1, 2, 3]}
        foreign = MappingProxyType(source)
        owned = freeze_object(foreign)
        assert freeze_object(owned) is owned
        expected = core.fingerprint(owned)
        source["x"].append(4)
        assert core.fingerprint(owned) == expected
        assert core.fingerprint(foreign) != expected
        for index in range(300):
            value = freeze_object({"index": index, "payload": "x" * 100})
            core.fingerprint(value)
        entries, size = core.cache_stats()
        assert 0 < entries <= 128
        assert 0 < size <= 1_048_576
        core.clear_cache()
        assert core.cache_stats() == (0, 0)
        assert core.fingerprint(owned) == expected
    finally:
        end(*scope)


@pytest.mark.asyncio
async def test_reentrant_lock_and_python_override_do_not_leak_codec():
    from aiogram_idle.storage.owned_lock import OwnedLock

    engine = JsonEngine(Dummy(), ValueError)
    lock = OwnedLock(processor=engine)
    async with lock:
        async with lock:
            assert selected() is engine
        async with OwnedLock():
            assert selected() is None
        assert selected() is engine

        async def child():
            assert selected() is None
            with pytest.raises(RuntimeError, match="owning task"):
                lock.release()

        await asyncio.create_task(child())
    assert selected() is None


def test_cached_sdk_record_is_not_accepted_as_json():
    pytest.importorskip("aiogram_idle_native")
    from aiogram_idle import IdleConversationKey
    from aiogram_idle.storage.receipts import new_canonicalizer

    core = new_canonicalizer()
    key = IdleConversationKey("test", 1, 42, 42)
    core.fingerprint(key)
    assert core.cache_stats()[0] > 0
    assert core.freeze(key, MappingProxyType, "idle") is None


@pytest.mark.asyncio
async def test_queue_only_scope_keeps_lock_ownership_without_codec():
    from aiogram_idle.storage.owned_lock import OwnedLock

    engine = JsonEngine(Dummy(), ValueError)
    lock = OwnedLock(processor=engine)
    async with lock.queue:
        assert lock.locked()
        assert selected() is None
        async with lock.queue:
            assert selected() is None

        async def child():
            with pytest.raises(RuntimeError, match="owning task"):
                lock.release()

        await asyncio.create_task(child())
    assert not lock.locked()
    async with lock:
        async with lock.queue:
            assert selected() is engine
        async with OwnedLock(processor=engine).queue:
            assert selected() is None
        assert selected() is engine
    assert selected() is None
