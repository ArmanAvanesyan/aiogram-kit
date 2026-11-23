"""Native JSON stages preserve immutable values, limits and task ownership."""

import asyncio
import json
from collections import UserDict
from contextvars import copy_context
from types import MappingProxyType

import pytest

from aiogram_nav._json_scope import JsonEngine, begin, end, selected
from aiogram_nav.engine import native_core
from aiogram_nav.errors import InvalidParameters
from aiogram_nav.json import freeze_object, thaw_json
from aiogram_nav.storage.state import canonicalizer


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
    pytest.importorskip("aiogram_nav_native")
    original = freeze_object(value)
    size = len(json.dumps(thaw_json(original), ensure_ascii=False).encode())
    scope = begin(JsonEngine(canonicalizer(), native_core().InvalidJson))
    try:
        result = freeze_object(value, max_bytes=size)
        assert thaw_json(result) == thaw_json(original)
        assert type(result) is type(original) is MappingProxyType
        with pytest.raises(InvalidParameters):
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
    pytest.importorskip("aiogram_nav_native")
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
    pytest.importorskip("aiogram_nav_native")

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
    pytest.importorskip("aiogram_nav_native")
    cycle = {}
    cycle["self"] = cycle
    scope = begin(JsonEngine(canonicalizer(), native_core().InvalidJson))
    try:
        with pytest.raises(InvalidParameters, match="nesting"):
            freeze_object(cycle)
    finally:
        end(*scope)


@pytest.mark.asyncio
async def test_codec_memo_is_owned_bounded_and_disposable():
    pytest.importorskip("aiogram_nav_native")
    from aiogram_nav.storage.state import new_canonicalizer

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
async def test_scoped_lock_cancellation_and_foreign_release():
    from aiogram_nav._json_scope import JsonLock

    lock = JsonLock(JsonEngine(Dummy(), ValueError))
    async with lock:

        async def foreign():
            assert selected() is None
            with pytest.raises(RuntimeError, match="owning task"):
                lock.release()

        await asyncio.create_task(foreign())
        waiting = asyncio.create_task(lock.acquire())
        await asyncio.sleep(0)
        waiting.cancel()
        with pytest.raises(asyncio.CancelledError):
            await waiting
        assert lock.locked()
    assert selected() is None
    assert not lock.locked()


def test_cached_sdk_record_is_not_accepted_as_json():
    pytest.importorskip("aiogram_nav_native")
    from aiogram_nav import ConversationKey
    from aiogram_nav.storage.state import new_canonicalizer

    core = new_canonicalizer()
    key = ConversationKey("test", 1, 42, 42)
    core.fingerprint(key)
    assert core.cache_stats()[0] > 0
    assert core.freeze(key, MappingProxyType, "nav") is None


@pytest.mark.asyncio
async def test_read_only_memory_projection_does_not_allocate_a_native_codec(monkeypatch):
    pytest.importorskip("aiogram_nav_native")
    from aiogram_nav import ConversationKey, MemoryNavigationRepository, NavigationConfig
    from aiogram_nav.storage import state

    def unexpected():
        raise AssertionError("Read-only projection allocated a native codec")

    monkeypatch.setattr(state, "canonicalizer", unexpected)
    repository = MemoryNavigationRepository(config=NavigationConfig(engine="rust"))
    assert await repository.load(ConversationKey("test", 1, 42, 42)) is None
    assert repository.json_processor.core.cache_stats() == (0, 0)
    await repository.close()


def test_deferred_codecs_fork_once_and_never_share_derived_data(monkeypatch):
    from aiogram_nav.storage import state

    class Core:
        def __init__(self):
            self.values = []

        def fingerprint(self, value):
            self.values.append(value)
            return str(value)

        def freeze(self, value, proxy, style):
            return None

        def cache_stats(self):
            return len(self.values), len(self.values)

        def clear_cache(self):
            self.values.clear()

    created = []

    class Template:
        def fork(self):
            core = Core()
            created.append(core)
            return core

    monkeypatch.setattr(state, "canonicalizer", Template)
    first = state.new_canonicalizer()
    second = first.fork()
    assert first.cache_stats() == second.cache_stats() == (0, 0)
    first.clear_cache()
    assert created == []
    assert first.fingerprint("a") == "a"
    assert first.fingerprint("b") == "b"
    assert len(created) == 1
    assert second.cache_stats() == (0, 0)
    assert second.fingerprint("c") == "c"
    assert len(created) == 2
    first.clear_cache()
    assert second.cache_stats() == (1, 1)


@pytest.mark.parametrize("initialized", [False, True])
def test_deferred_codec_disposal_never_requires_cycle_collection(initialized):
    import gc
    import weakref

    from aiogram_nav.storage.state import new_canonicalizer

    if initialized:
        pytest.importorskip("aiogram_nav_native")
    enabled = gc.isenabled()
    gc.disable()
    try:
        core = new_canonicalizer()
        assert "fingerprint" not in vars(core)
        assert "freeze" not in vars(core)
        if initialized:
            core.fingerprint({"value": 1})
            # Initialized hot calls still go directly to native bound methods.
            assert vars(core)["fingerprint"].__self__ is core._loaded
            assert vars(core)["freeze"].__self__ is core._loaded
        reference = weakref.ref(core)
        del core
        assert reference() is None
    finally:
        if enabled:
            gc.enable()


@pytest.mark.asyncio
async def test_read_only_projection_codec_drops_immediately_without_gc():
    import gc
    import weakref

    from aiogram_nav import ConversationKey, MemoryNavigationRepository, NavigationConfig

    pytest.importorskip("aiogram_nav_native")
    enabled = gc.isenabled()
    gc.disable()
    try:
        repository = MemoryNavigationRepository(config=NavigationConfig(engine="rust"))
        reference = weakref.ref(repository.json_processor.core)
        assert await repository.load(ConversationKey("read-only", 1, 42, 42)) is None
        await repository.close()
        del repository
        assert reference() is None
    finally:
        if enabled:
            gc.enable()


@pytest.mark.asyncio
async def test_revoked_copied_context_drops_codec_and_completed_owner_without_gc():
    import gc
    import weakref

    enabled = gc.isenabled()
    gc.disable()
    try:

        async def create_revoked_context():
            engine = JsonEngine(Dummy(), ValueError)
            scope = begin(engine)
            copied = copy_context()
            engine_reference = weakref.ref(engine)
            owner_reference = weakref.ref(asyncio.current_task())
            end(*scope)
            return copied, engine_reference, owner_reference, scope[1]

        task = asyncio.create_task(create_revoked_context())
        copied, engine_reference, owner_reference, record = await task
        del task
        # Let asyncio discard the completed task's ready/await callbacks; do not
        # collect cycles while the copied Context remains deliberately alive.
        await asyncio.sleep(0)
        await asyncio.sleep(0)
        assert copied.run(selected) is None
        assert record.engine is record.owner is None
        assert engine_reference() is None
        assert owner_reference() is None
    finally:
        if enabled:
            gc.enable()


@pytest.mark.asyncio
async def test_scope_revocation_clears_only_inner_references_and_restores_outer():
    outer_engine = JsonEngine(Dummy(), ValueError)
    outer = begin(outer_engine)
    try:
        inner_engine = JsonEngine(Dummy(), ValueError)
        inner = begin(inner_engine)
        copied = copy_context()
        end(*inner)
        assert inner[1].engine is inner[1].owner is None
        assert selected() is outer_engine
        assert copied.run(selected) is None
        assert outer[1].engine is outer_engine
        assert outer[1].owner is asyncio.current_task()
    finally:
        end(*outer)
    assert outer[1].engine is outer[1].owner is None


@pytest.mark.asyncio
async def test_copied_context_revocation_keeps_actual_backend_lock_owner():
    from aiogram_nav._json_scope import JsonLock

    lock = JsonLock(JsonEngine(Dummy(), ValueError))
    await lock.acquire()
    copied = copy_context()
    copied.run(end, *lock.scope)
    assert selected() is copied.run(selected) is None
    assert lock.scope[1].owner is lock.scope[1].engine is None

    async def foreign():
        with pytest.raises(RuntimeError, match="owning task"):
            lock.release()

    await asyncio.create_task(foreign())
    assert lock.locked()
    lock.release()
    assert not lock.locked()
    assert lock._owner is None
