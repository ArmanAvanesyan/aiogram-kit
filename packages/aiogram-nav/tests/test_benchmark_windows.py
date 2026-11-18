"""Fresh benchmark windows preserve ages, observations and denominators."""

import importlib.util
import itertools
import json
import sys
from collections import Counter
from pathlib import Path
from types import SimpleNamespace

import pytest

BENCHMARKS = Path(__file__).parents[1] / "benchmarks"


def load(monkeypatch, filename):
    monkeypatch.syspath_prepend(str(BENCHMARKS))
    spec = importlib.util.spec_from_file_location(
        "nav_window_" + filename, BENCHMARKS / (filename + ".py")
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def redis_windows(monkeypatch):
    pytest.importorskip("redis")
    return load(monkeypatch, "redis_workload")


def window_row(index, *, kind="track", age=50, samples=100):
    return dict(
        scenario="redis-dispatch-" + kind,
        workload=f"redis-dispatch-{kind}/{age}",
        engine="python",
        state_age=age,
        storage_format=3,
        status="measured",
        fixture_boundary="fixed-age test window",
        fixture_id=f"prefix-{index}",
        fixture_start_age=age,
        fixture_end_age=age + (samples if kind == "track" else 0),
        samples=samples,
        calls=samples,
        update_sample_count=samples,
        process_cpu_seconds=[float(index + 1)],
        median_process_cpu_seconds=float(index + 1),
        raw_latency_seconds=[float(index + 1)] * samples,
        raw_client_round_trips=[2] * samples,
        raw_sent_bytes=[10] * samples,
        raw_received_bytes=[20] * samples,
        client_commands={"evalsha": 2 * samples},
        lua_internal_commands={"get": samples},
        cold_namespace_bootstrap=dict(
            sent=1, received=2, responses=3, flushes=4, commands={"set": 1}
        ),
    )


def test_pool_retains_all_samples_and_correct_cpu_counter_denominators(redis_windows):
    rows = [window_row(index) for index in range(10)]
    result = redis_windows._pool(rows, 100)
    assert result["raw_latency_seconds"] == [
        value for row in rows for value in row["raw_latency_seconds"]
    ]
    assert result["calls"] == result["operations_per_cpu_sample"] == 100
    assert (
        result["total_calls"]
        == result["counter_operation_count"]
        == result["update_sample_count"]
        == 1000
    )
    assert result["process_cpu_seconds"] == list(range(1, 11))
    assert result["median_cpu_ns"] == 5.5 * 1_000_000_000 / 100
    assert result["update_p95_seconds"] == 10
    assert result["client_commands"]["evalsha"] / result["counter_operation_count"] == 2
    assert result["lua_internal_commands"] == {"get": 1000}
    assert result["cold_namespace_bootstrap"]["commands"] == {"set": 10}
    assert len(result["cold_namespace_bootstrap_windows"]) == 10
    assert result["latency_windows"] == len(result["latency_window_fixtures"]) == 10
    assert result["latency_window_boundaries"][0] == dict(
        window=0,
        start=0,
        stop=100,
        operation_count=100,
        samples=100,
        state_age=50,
        end_state_age=150,
    )
    assert result["latency_window_boundaries"][-1]["stop"] == 1000


@pytest.mark.parametrize("damage", ["count", "age", "duplicate_fixture", "workload"])
def test_pool_rejects_incomplete_or_nonfresh_windows(redis_windows, damage):
    rows = [window_row(0), window_row(1)]
    if damage == "count":
        rows[1]["raw_received_bytes"].pop()
    elif damage == "age":
        rows[1]["fixture_end_age"] = 1050
    elif damage == "duplicate_fixture":
        rows[1]["fixture_id"] = rows[0]["fixture_id"]
    else:
        rows[1]["workload"] = "other"
    with pytest.raises(ValueError):
        redis_windows._pool(rows, 100)


@pytest.mark.asyncio
async def test_failed_window_is_not_retried_or_dropped(redis_windows, monkeypatch):
    calls = []

    async def measured(*args):
        index = len(calls)
        calls.append(args)
        if index == 1:
            return [dict(status="unavailable", phase="fixture", error_type="Injected")]
        return [window_row(index, kind="noop"), window_row(index)]

    monkeypatch.setattr(redis_windows, "_window", measured)
    result = await redis_windows.workload("redis://unused", "python", 50, 100, object(), windows=10)
    assert len(calls) == 2
    assert result[0]["status"] == "unavailable"
    assert result[0]["completed_latency_windows"] == 1
    assert result[0]["failed_latency_window"] == 1
    assert len(result[0]["completed_window_results"][0][0]["raw_latency_seconds"]) == 100
    assert result[0]["failed_window_result"][0]["error_type"] == "Injected"


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", [None, "track-start", "track-update"])
async def test_ten_windows_use_fresh_sessions_fixed_age_and_capacity(
    redis_windows, monkeypatch, failure
):
    # Real fixture/window builder, fake transport and deterministic counters.
    # This performs no actual benchmark timing or Redis operations.
    repositories, clients = [], []
    ticks = itertools.count(100, 100)
    monkeypatch.setattr(redis_windows.time, "process_time_ns", lambda: next(ticks))
    monkeypatch.setattr(redis_windows.time, "perf_counter_ns", lambda: next(ticks))
    identifiers = itertools.count()
    monkeypatch.setattr(
        redis_windows, "uuid4", lambda: SimpleNamespace(hex=f"window-{next(identifiers)}")
    )

    class Metrics:
        def __init__(self):
            self.reset()
            self.server = Counter()

        def reset(self):
            self.responses = self.sent = self.received = self.flushes = 0
            self.commands = Counter()

        def command(self, name):
            self.commands[name] += 1
            self.server[name] += 1
            self.responses += 1
            self.flushes += 1
            self.sent += 10
            self.received += 20

        def snapshot(self):
            return dict(
                responses=self.responses,
                sent=self.sent,
                received=self.received,
                flushes=self.flushes,
                commands=dict(self.commands),
            )

    class Redis:
        def __init__(self):
            self.info_calls = 0

        async def ping(self):
            return True

        async def info(self, _):
            self.info_calls += 1
            if failure == "track-start" and clients.index(self) == 1 and self.info_calls == 3:
                raise RuntimeError("Injected phase bootstrap failure")
            return {
                "cmdstat_" + name: {"calls": value} for name, value in self.metrics.server.items()
            }

        async def scan_iter(self, *, match):
            self.scan_match = match
            yield match[:-1] + "owned"

        async def delete(self, *keys):
            self.deleted = keys

        async def aclose(self):
            self.closed = True

    def client(_):
        redis = Redis()
        redis.metrics = Metrics()
        clients.append(redis)
        return redis, redis.metrics

    class Repository:
        def __init__(self, *, redis, prefix, config, storage_format=3):
            self.redis, self.prefix, self.config = redis, prefix, config
            self.storage_format = storage_format
            self.age = 0
            repositories.append(self)

        async def initialize(self):
            self.redis.metrics.command("set")

        async def close(self):
            self.closed = True

    class Context:
        def __init__(self, repository):
            self.repository = repository

        async def track(self, *args, **kwargs):
            self.repository.age += 1
            self.repository.redis.metrics.command("evalsha")

    class Nav:
        def __init__(self, *, repository, **kwargs):
            self.context = Context(repository)

        def install(self, dispatcher):
            dispatcher.context = self.context

        def for_conversation(self, _):
            return self.context

    class Router:
        def message(self):
            def decorator(handler):
                self.handler = handler
                return handler

            return decorator

    class Dispatcher:
        def __init__(self, **kwargs):
            async def close():
                pass

            self.fsm = SimpleNamespace(close=close)

        def include_router(self, router):
            self.router = router

        async def feed_update(self, bot, update):
            repo = self.context.repository
            repo.redis.metrics.command("get")
            if (
                failure == "track-update"
                and repositories.index(repo) == 1
                and update.text == "track"
                and repo.age == 80
            ):
                raise RuntimeError("Injected update failure")
            await self.router.handler(update, self.context)

    monkeypatch.setattr(redis_windows, "client", client)
    monkeypatch.setattr(redis_windows, "RedisNavigationRepository", Repository)
    monkeypatch.setattr(redis_windows, "Navigation", Nav)
    monkeypatch.setattr(redis_windows, "NavigationRegistry", lambda **kwargs: None)
    monkeypatch.setattr(redis_windows, "Router", Router)
    monkeypatch.setattr(redis_windows, "Dispatcher", Dispatcher)
    monkeypatch.setattr(
        redis_windows, "Bot", lambda token, session: SimpleNamespace(id=123456, session=session)
    )
    monkeypatch.setattr(
        redis_windows, "incoming", lambda index, text: SimpleNamespace(message_id=index, text=text)
    )
    results = await redis_windows.workload(
        "redis://unused", "python", 50, 100, lambda engine, capacity: (engine, capacity), windows=10
    )
    if failure is not None:
        assert len(repositories) == len(clients) == 2
        assert all(
            repo.closed and client.closed
            for repo, client in zip(repositories, clients, strict=True)
        )
        failed = results[0]
        assert failed["status"] == "unavailable"
        assert failed["completed_latency_windows"] == failed["failed_latency_window"] == 1
        assert len(failed["completed_window_results"]) == 1
        detail = failed["failed_window_result"][0]
        assert detail["error_type"] == "RuntimeError"
        assert len(detail["completed_scenarios"][0]["raw_latency_seconds"]) == 100
        assert detail["partial_scenario"]["scenario"] == "redis-dispatch-track"
        assert len(detail["partial_scenario"]["raw_latency_seconds"]) == (
            0 if failure == "track-start" else 30
        )
        return
    assert len(repositories) == len(clients) == 10
    assert len({repo.prefix for repo in repositories}) == 10
    assert all(
        repo.config == ("python", 160) and repo.age == 150 and repo.closed for repo in repositories
    )
    assert all(
        client.closed and client.scan_match == repo.prefix + ":*"
        for client, repo in zip(clients, repositories, strict=True)
    )
    assert all(
        key.startswith(repo.prefix + ":")
        for client, repo in zip(clients, repositories, strict=True)
        for key in client.deleted
    )
    noop, track = results
    assert noop["scenario"] == "redis-dispatch-noop"
    assert track["scenario"] == "redis-dispatch-track"
    assert all(
        boundary["state_age"] == boundary["end_state_age"] == 50
        for boundary in noop["latency_window_boundaries"]
    )
    assert all(
        boundary["state_age"] == 50 and boundary["end_state_age"] == 150
        for boundary in track["latency_window_boundaries"]
    )
    assert track["client_commands"] == {"get": 1000, "evalsha": 1000}
    assert sum(track["client_commands"].values()) / track["counter_operation_count"] == 2
    assert len(track["raw_latency_seconds"]) == len(noop["raw_latency_seconds"]) == 1000


@pytest.mark.asyncio
async def test_cli_failure_writes_evidence_and_returns_nonzero(
    redis_windows, monkeypatch, tmp_path
):
    cli = load(monkeypatch, "run")
    monkeypatch.setitem(sys.modules, "redis_workload", redis_windows)

    async def failed(*args, **kwargs):
        return [dict(status="unavailable", failed_latency_window=0)]

    async def diagnostic(*args, **kwargs):
        return "diagnostic"

    monkeypatch.setattr(redis_windows, "workload", failed)
    monkeypatch.setattr(cli.asyncio, "to_thread", diagnostic)
    output = tmp_path / "failed.json"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "run.py",
            "--output",
            str(output),
            "--skip-memory",
            "--skip-registry",
            "--redis-url",
            "redis://unused",
            "--ages",
            "50",
            "--samples",
            "100",
            "--latency-windows",
            "10",
        ],
    )
    with pytest.raises(SystemExit, match="window failed"):
        await cli.main()
    evidence = json.loads(output.read_text())
    assert evidence["sampling_plan"]["redis_latency_windows"] == 10
    assert evidence["results"][0]["status"] == "unavailable"


@pytest.mark.asyncio
async def test_default_keeps_one_historical_window(redis_windows, monkeypatch):
    captured = []
    rows = [window_row(0, kind="noop"), window_row(0)]

    async def measured(*args):
        captured.append(args)
        return rows

    monkeypatch.setattr(redis_windows, "_window", measured)
    results = await redis_windows.workload("redis://unused", "python", 50, 100, object())
    assert len(captured) == 1
    for result, original in zip(results, rows, strict=True):
        assert result["latency_windows"] == 1
        assert result["total_calls"] == result["calls"] == 100
        for field in (
            "raw_latency_seconds",
            "process_cpu_seconds",
            "client_commands",
            "cold_namespace_bootstrap",
        ):
            assert result[field] == original[field]


@pytest.mark.asyncio
@pytest.mark.parametrize("count", [0, 101, True])
async def test_invalid_window_count_fails_before_fixture(redis_windows, monkeypatch, count):
    async def unexpected(*args):
        raise AssertionError("Invalid count reached fixture setup")

    monkeypatch.setattr(redis_windows, "_window", unexpected)
    with pytest.raises(ValueError, match="1..100"):
        await redis_windows.workload("redis://unused", "python", 50, 100, object(), windows=count)


@pytest.mark.asyncio
async def test_cpu_repeats_keep_thirty_fresh_hundred_operation_fixtures(monkeypatch):
    cli = load(monkeypatch, "run")
    repositories = []
    ticks = itertools.count(100, 100)
    monkeypatch.setattr(cli.time, "process_time_ns", lambda: next(ticks))
    monkeypatch.setattr(cli.time, "perf_counter_ns", lambda: next(ticks))

    class Repository:
        def __init__(self, *, config, clock):
            self.config = config
            self.operations = []
            repositories.append(self)

    class Nav:
        def __init__(self, *, repository, **kwargs):
            self.repository = repository

        def for_conversation(self, _):
            return self

        async def track(self, *args, **kwargs):
            self.repository.operations.append(kwargs["operation_id"])

    monkeypatch.setattr(cli, "MemoryNavigationRepository", Repository)
    monkeypatch.setattr(cli, "NavigationRegistry", lambda **kwargs: None)
    monkeypatch.setattr(cli, "Navigation", Nav)
    result = await cli.workload(50, "python", 100, 30)
    assert len(repositories) == 30
    assert all(repo.config.max_receipts == 160 for repo in repositories)
    assert all(len(repo.operations) == 150 for repo in repositories)
    assert all(
        repo.operations[49] == "age-49" and repo.operations[50] == "sample-0"
        for repo in repositories
    )
    assert result["calls"] == result["operations_per_cpu_sample"] == 100
    assert result["total_calls"] == result["update_sample_count"] == 3000
    assert len(result["process_cpu_seconds"]) == result["latency_windows"] == 30
    assert len(result["raw_latency_seconds"]) == 3000
    assert all(
        boundary["state_age"] == 50 and boundary["end_state_age"] == 150
        for boundary in result["latency_window_boundaries"]
    )
    assert result["latency_window_boundaries"][-1]["stop"] == 3000
