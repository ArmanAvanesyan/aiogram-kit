"""Cross-engine domain vectors; native absence remains an optional dependency."""

from __future__ import annotations

import hashlib
import json
import random
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from aiogram_idle.engines import (
    activity_guard,
    claim_guard,
    fingerprint_canonical,
    make_queue,
    native_core,
    phase_transition,
    receipt_admission,
    require_engine,
    session_guard,
)
from aiogram_idle.errors import ActivityConflict, ConfigurationError, OwnershipLost
from aiogram_idle.machine import Trigger
from aiogram_idle.models import (
    IdleConversationKey,
    IdleSnapshot,
    Phase,
    RuntimeSnapshot,
    SessionSnapshot,
)
from aiogram_idle.storage.state import Claim, Job

NATIVE = pytest.mark.skipif(
    __import__("importlib.util", fromlist=["find_spec"]).find_spec("aiogram_idle_native") is None,
    reason="optional native companion is not installed",
)


def test_missing_native_fails_at_selection_without_fallback(monkeypatch):
    native_core.cache_clear()

    def unavailable(name):
        raise ModuleNotFoundError(name)

    monkeypatch.setattr("aiogram_idle.engines.importlib.import_module", unavailable)
    with pytest.raises(ConfigurationError, match="requires aiogram-idle-native==0.3.1"):
        require_engine("rust")
    require_engine("python")
    native_core.cache_clear()


@pytest.mark.parametrize("version,abi", [("0.2.0", 1), ("0.3.1", 2)])
def test_incompatible_native_rejected_before_backend_mutation(monkeypatch, version, abi):
    native_core.cache_clear()
    monkeypatch.setattr(
        "aiogram_idle.engines.importlib.import_module",
        lambda _: SimpleNamespace(API_VERSION=abi, ENGINE_VERSION=version),
    )
    with pytest.raises(ConfigurationError, match="ABI/version"):
        require_engine("rust")
    native_core.cache_clear()


def test_unknown_engine_rejected():
    with pytest.raises(ConfigurationError, match="engine must"):
        require_engine("automatic")


@NATIVE
def test_every_lifecycle_transition_matches_python_reference():
    for phase in Phase:
        for trigger in Trigger:
            try:
                expected = phase_transition(phase.value, trigger.value)
            except ActivityConflict:
                with pytest.raises(ActivityConflict):
                    phase_transition(phase.value, trigger.value, engine="rust")
            else:
                assert phase_transition(phase.value, trigger.value, engine="rust") == expected


@NATIVE
@pytest.mark.parametrize("revision", [1, 2, 10**100])
def test_session_activity_claim_guards_match_at_boundaries(revision):
    for now in [0.0, 9.999999, 10.0, 11.0]:
        for actual in [None, ("s", "a", revision, 10.0), ("foreign", "a", revision, 10.0)]:
            assert activity_guard(
                actual, ("s", "a", revision), now, engine="rust"
            ) == activity_guard(actual, ("s", "a", revision), now)
        for actual in [None, ("s", revision, 10.0), ("other", revision, 10.0)]:
            for expected in [None, ("s", revision), ("s", revision + 1)]:
                assert session_guard(actual, expected, now, engine="rust") == session_guard(
                    actual, expected, now
                )
        for actual in [None, ("token", revision, 10.0), ("other", revision, 10.0)]:
            assert claim_guard(actual, ("token", revision), now, engine="rust") == claim_guard(
                actual, ("token", revision), now
            )


@NATIVE
@pytest.mark.parametrize(
    "value", [None, True, 1, 1.0, -0.0, 10**200, "é\\u0000", {"nested": [1, 1.0, -0.0, "հայերեն"]}]
)
def test_exact_legacy_fingerprint_bytes(value):
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)
    assert fingerprint_canonical(raw, engine="rust") == hashlib.sha256(raw.encode()).hexdigest()


@NATIVE
def test_receipt_decisions_preserve_duplicate_before_capacity_and_big_integers():
    for existing in [None, "same", "different"]:
        for count in [0, 1, 100, 10**100]:
            for limit in [1, 256, 10**101]:
                assert receipt_admission(
                    existing, "same", count, limit, engine="rust"
                ) == receipt_admission(existing, "same", count, limit)


def record(key, deadline):
    return RuntimeSnapshot(
        key,
        SessionSnapshot("session", 100_000),
        idle=IdleSnapshot(phase=Phase.ACTIVE, deadline=deadline),
    )


def capture(action):
    try:
        return action()
    except OwnershipLost:
        return "ownership"


@NATIVE
def test_seeded_5000_step_queue_history_matches_python():
    rng = random.Random(7315)
    queues = [make_queue("python"), make_queue("rust")]
    keys = [
        IdleConversationKey("n" + str(index % 2), index % 2 + 1, index + 1, index + 1)
        for index in range(12)
    ]
    now = 0.0
    for index in range(5000):
        now += rng.randrange(3)
        key = rng.choice(keys)
        action = rng.randrange(5)
        if action == 0:
            deadline = None if rng.randrange(5) == 0 else now + rng.randrange(10)
            for queue in queues:
                queue.schedule(record(key, deadline))
        elif action == 1:
            namespace = rng.choice([None, "n0", "n1"])
            results = []
            for queue in queues:
                with patch(
                    "secrets.token_urlsafe", side_effect=[f"token-{index}-{n}" for n in range(100)]
                ):
                    results.append(
                        queue.claim(limit=8, lease_seconds=10, now=now, namespace=namespace)
                    )
            assert results[0] == results[1]
        elif action in {2, 3}:
            job = queues[0].jobs.get(key)
            if job is None or job.token is None:
                continue
            claim = Claim(
                key,
                job.token if rng.randrange(4) else "foreign",
                job.generation,
                job.lease_until,
                job.deadline,
            )
            deadline = now + rng.randrange(10)
            results = [
                capture(
                    lambda q=queue, c=claim, t=now, a=action, k=key, d=deadline: (
                        q.renew(c, now=t, lease_seconds=10)
                        if a == 2
                        else q.release(c, record(k, d), now=t)
                    )
                )
                for queue in queues
            ]
            assert results[0] == results[1]
        else:
            for queue in queues:
                queue.jobs.pop(key, None)
        assert queues[0].sequence == queues[1].sequence
        assert dict(queues[0].jobs) == dict(queues[1].jobs)
        for queue in queues:
            assert len(queue.heap) <= 2 * len(queue.jobs) + 128 or not queue.jobs


@NATIVE
def test_queue_restores_big_generation_and_does_not_allocate_tokens_for_huge_limit():
    key = IdleConversationKey("test", 10**100, 42, 42)
    queue = make_queue("rust")
    generation = 10**100
    queue.jobs[key] = Job(generation, 1, 1)
    queue.sequence = generation
    queue._push(key, queue.jobs[key])
    assert queue.jobs[key].generation == generation
    with patch("secrets.token_urlsafe", return_value="one") as random_token:
        claims = queue.claim(limit=10**100, lease_seconds=10, now=2)
    assert len(claims) == 1 and random_token.call_count == 1
    assert claims[0].generation == generation


@NATIVE
def test_reconciliation_is_bounded_and_restores_only_missing_jobs():
    keys = [IdleConversationKey("test", 1, i, i) for i in range(1, 4)]
    queue = make_queue("rust")
    assert queue.reconcile([record(key, 5) for key in keys], limit=2) == 2
    assert set(queue.jobs) == set(keys[:2])
    assert queue.reconcile([record(key, 6) for key in keys], limit=3) == 1
    assert queue.jobs[keys[0]].deadline == 5


@NATIVE
def test_invalid_native_input_does_not_mutate_existing_queue():
    queue = native_core().DeadlineCore()
    queue.schedule("key", "namespace", "1", 10)
    before = queue.get("key")
    with pytest.raises(ValueError):
        queue.renew("key", "token", "1", 0, float("nan"))
    assert queue.get("key") == before


@NATIVE
def test_opaque_unicode_identities_preserve_surrogate_codepoints():
    namespace, sid, aid, token = "scope-\ud800", "session-\udfff", "activity-\ud800", "token-\udfff"
    assert activity_guard((sid, aid, 1, 10), (sid, aid, 1), 1, engine="rust") is None
    assert session_guard((sid, 1, 10), (sid, 1), 1, engine="rust") is None
    assert claim_guard((token, 1, 10), (token, 1), 1, engine="rust") is None
    with pytest.raises(ConfigurationError):
        IdleConversationKey(namespace, 1, 42, 42)
    key = IdleConversationKey("scope-🙂", 1, 42, 42)
    namespace = key.namespace
    queue = make_queue("rust")
    queue.schedule(record(key, 1))
    with patch("secrets.token_urlsafe", return_value=token):
        claimed = queue.claim(limit=1, lease_seconds=10, now=2, namespace=namespace)[0]
    assert claimed.key == key and claimed.token == token
    assert queue.check(claimed, 3).token == token


@NATIVE
def test_missing_queue_capability_rejected_before_backend_mutation(monkeypatch):
    original = native_core()
    native_core.cache_clear()
    fake = SimpleNamespace(
        **{
            name: getattr(original, name)
            for name in (
                "API_VERSION",
                "ENGINE_VERSION",
                "OwnershipLost",
                "phase_transition",
                "fingerprint_canonical",
                "receipt_admission",
                "activity_guard",
                "session_guard",
                "claim_guard",
            )
        }
    )
    fake.DeadlineCore = object
    monkeypatch.setattr("aiogram_idle.engines.importlib.import_module", lambda _: fake)
    with pytest.raises(ConfigurationError, match="ABI/version"):
        require_engine("rust")
    native_core.cache_clear()


@NATIVE
def test_native_error_after_mutation_is_not_retried_in_python():
    from aiogram_idle._native_queue import RustDeadlineQueue

    queue = RustDeadlineQueue()
    original = queue.core

    class BrokenAfterWrite:
        def __getattr__(self, name):
            return getattr(original, name)

        def schedule(self, *args):
            original.schedule(*args)
            raise RuntimeError("injected failure after mutation")

    queue.core = BrokenAfterWrite()
    key = IdleConversationKey("test", 1, 42, 42)
    with pytest.raises(RuntimeError, match="after mutation"):
        queue.schedule(record(key, 5))
    assert len(original) == 1


@NATIVE
def test_integer_wire_does_not_depend_on_global_decimal_digit_limit():
    # More than CPython's default 4300 decimal digits, valid in the original models.
    number = 1 << 20_000
    assert activity_guard(("s", "a", number, 10), ("s", "a", number), 1, engine="rust") is None
    assert receipt_admission(None, "digest", number, number + 1, engine="rust") == "admit"
    key = IdleConversationKey("native", number, number, number)
    queue = make_queue("rust")
    queue.jobs[key] = Job(number, 1, 1)
    queue.sequence = number
    queue._push(key, queue.jobs[key])
    with patch("secrets.token_urlsafe", return_value="token"):
        claim = queue.claim(limit=1, lease_seconds=10, now=2, bot_id=number)[0]
    assert claim.generation == number and claim.key == key


@NATIVE
def test_native_queue_views_do_not_delay_core_release_until_gc():
    import gc
    import weakref

    enabled = gc.isenabled()
    gc.disable()
    try:
        queue = make_queue("rust")
        reference = weakref.ref(queue)
        queue.schedule(record(IdleConversationKey("test", 1, 42, 42), 1))
        del queue
        assert reference() is None
    finally:
        if enabled:
            gc.enable()


@NATIVE
def test_schedule_and_release_need_no_second_native_snapshot():
    from aiogram_idle._native_queue import RustDeadlineQueue

    queue = RustDeadlineQueue()
    original = queue.core

    class NoSnapshots:
        def __getattr__(self, name):
            return getattr(original, name)

        def __len__(self):
            return len(original)

        def get(self, key):
            raise AssertionError("redundant native snapshot")

    queue.core = NoSnapshots()
    key = IdleConversationKey("test", 1, 42, 42)
    queue.schedule(record(key, 5))
    assert list(queue.keys.values()) == [key]
    claim = queue.claim(limit=1, lease_seconds=10, now=5)[0]
    # A preserved owned job remains present even when no new deadline is supplied.
    queue.schedule(record(key, None), preserve=claim)
    assert list(queue.keys.values()) == [key]
    queue.release(claim, record(key, None), now=6, retry_at=8)
    assert list(queue.keys.values()) == [key]
    claim = queue.claim(limit=1, lease_seconds=10, now=8)[0]
    queue.release(claim, record(key, None), now=9)
    assert not queue.keys
    queue.schedule(record(key, 10))
    queue.schedule(record(key, None))
    assert not queue.keys


@NATIVE
@pytest.mark.parametrize(
    "token", ["ordinary-token", 'quote"slash\\', "line\n", "Հայերեն🙂", "token-\udfff", ""]
)
@pytest.mark.parametrize("sequence", [0, 10**100])
def test_release_values_keeps_full_guard_and_lossless_transport(token, sequence):
    queue = native_core().DeadlineCore()
    queue.sequence = format(sequence, "x")
    queue.schedule("key", '"scope"', "1", 1)
    encoded = json.dumps(token, ensure_ascii=True)
    claim = queue.claim(1, 10, 2, [encoded])[0]
    generation = int(claim[2], 16)
    before = queue.get("key")
    with pytest.raises(native_core().OwnershipLost):
        queue.release_values("key", token, generation + 1, 3, 20)
    assert queue.get("key") == before
    with pytest.raises(native_core().OwnershipLost):
        queue.release_values("key", token + "foreign", generation, 3, 20)
    assert queue.get("key") == before
    queue.release_values("key", token, generation, 3, 20)
    assert queue.get("key")[1:4] == (20, 20, None)
    with pytest.raises(native_core().OwnershipLost):
        queue.release_values("key", token, generation, 3, 20)


@NATIVE
@pytest.mark.parametrize("generation", [0, -1])
def test_release_values_invalid_generation_is_atomic(generation):
    queue = native_core().DeadlineCore()
    queue.schedule("key", '"scope"', "1", 1)
    queue.claim(1, 10, 2, ['"token"'])
    before = queue.get("key")
    with pytest.raises(ValueError):
        queue.release_values("key", "token", generation, 3, 20)
    assert queue.get("key") == before


@NATIVE
def test_release_values_honors_integer_subclass_format_and_expiry():
    calls = []

    class Revision(int):
        def __format__(self, spec):
            calls.append(spec)
            return super().__format__(spec)

    queue = native_core().DeadlineCore()
    queue.schedule("key", '"scope"', "1", 1)
    queue.claim(1, 10, 2, ['"token"'])
    before = queue.get("key")
    with pytest.raises(native_core().OwnershipLost):
        queue.release_values("key", "token", Revision(1), 12, 20)
    assert calls == ["x"]
    assert queue.get("key") == before
    queue.release_values("key", "token", Revision(1), 3, 20)
    assert calls == ["x", "x"]


@NATIVE
def test_release_values_format_uses_type_special_method_lookup():
    class Revision(int):
        def __format__(self, spec):
            return super().__format__(spec)

        def __getattribute__(self, name):
            if name == "__format__":
                return lambda spec: "wrong"
            return super().__getattribute__(name)

    queue = native_core().DeadlineCore()
    queue.schedule("key", '"scope"', "1", 1)
    queue.claim(1, 10, 2, ['"token"'])
    queue.release_values("key", "token", Revision(1), 3, 20)
    assert queue.get("key")[1:4] == (20, 20, None)


@NATIVE
@pytest.mark.parametrize("deadline", [float("nan"), float("inf"), -float("inf")])
def test_release_values_invalid_deadline_does_not_consume_claim(deadline):
    queue = native_core().DeadlineCore()
    queue.schedule("key", '"scope"', "1", 1)
    queue.claim(1, 10, 2, ['"token"'])
    before = queue.get("key")
    with pytest.raises(ValueError):
        queue.release_values("key", "token", 1, 3, deadline)
    assert queue.get("key") == before
    queue.release_values("key", "token", 1, 3, None)
    assert queue.get("key") is None


@NATIVE
def test_release_values_missing_replaced_and_expired_claims_are_fenced():
    queue = native_core().DeadlineCore()
    with pytest.raises(native_core().OwnershipLost):
        queue.release_values("missing", "token", 1, 3, None)
    queue.schedule("key", '"scope"', "1", 1)
    queue.claim(1, 10, 2, ['"token"'])
    before = queue.get("key")
    with pytest.raises(native_core().OwnershipLost):
        queue.release_values("key", "token", 1, 12, None)
    assert queue.get("key") == before
    queue.schedule("key", '"scope"', "1", 1)
    replacement = queue.claim(1, 10, 3, ['"replacement"'])[0]
    before = queue.get("key")
    with pytest.raises(native_core().OwnershipLost):
        queue.release_values("key", "token", 1, 4, None)
    assert queue.get("key") == before
    queue.release_values("key", "replacement", int(replacement[2], 16), 4, None)
    assert queue.get("key") is None


@NATIVE
@pytest.mark.parametrize("generation", [True, 1])
def test_queue_release_scalar_subclasses_keep_original_format_path(generation):
    class Revision(int):
        def __format__(self, spec):
            return "1"

    class Token(str):
        def __str__(self):
            return "foreign"

    for revision in (generation, Revision(999)):
        key = IdleConversationKey("scope", 1, 42, 42)
        queue = make_queue("rust")
        queue.schedule(record(key, 1))
        with patch("secrets.token_urlsafe", return_value="token"):
            claimed = queue.claim(limit=1, lease_seconds=10, now=2)[0]
        fabricated = Claim(key, Token("token"), revision, claimed.lease_until, claimed.deadline)
        queue.release(fabricated, record(key, 1), now=3, retry_at=20)
        assert queue.jobs[key].deadline == 20


@NATIVE
def test_raw_release_capability_required_before_engine_selection(monkeypatch):
    original = native_core()
    native_core.cache_clear()

    class MissingRelease:
        def __init__(self):
            self.core = original.DeadlineCore()

        def __getattr__(self, name):
            if name == "release_values":
                raise AttributeError(name)
            return getattr(self.core, name)

    fake = SimpleNamespace(**vars(original))
    fake.DeadlineCore = MissingRelease
    monkeypatch.setattr("aiogram_idle.engines.importlib.import_module", lambda _: fake)
    try:
        with pytest.raises(ConfigurationError, match="ABI/version"):
            require_engine("rust")
    finally:
        native_core.cache_clear()


@NATIVE
def test_raw_release_unknown_error_is_not_retried_after_mutation():
    key = IdleConversationKey("scope", 1, 42, 42)
    queue = make_queue("rust")
    queue.schedule(record(key, 1))
    claimed = queue.claim(limit=1, lease_seconds=10, now=2)[0]
    original = queue.core
    calls = []

    class FailedAfterWrite:
        def __getattr__(self, name):
            return getattr(original, name)

        def release_values(self, *args):
            calls.append("release")
            original.release_values(*args)
            raise RuntimeError("unknown after release")

        def release(self, *args):
            raise AssertionError("legacy release must not retry a native error")

    queue.core = FailedAfterWrite()
    with pytest.raises(RuntimeError, match="unknown after release"):
        queue.release(claimed, record(key, 1), now=3, retry_at=20)
    assert calls == ["release"]
    assert queue.jobs[key].deadline == 20
