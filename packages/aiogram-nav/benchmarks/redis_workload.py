"""Whole protected dispatcher updates against a dedicated Redis primary."""

from __future__ import annotations

import inspect
import math
import statistics
import time
from collections import Counter
from datetime import datetime, timezone
from uuid import uuid4

from aiogram import Bot, Dispatcher, Router
from aiogram.client.session.base import BaseSession
from aiogram.fsm.storage.memory import SimpleEventIsolation
from aiogram.types import Chat, Message, Update, User
from redis_metrics import client

from aiogram_nav import (
    ApplicationPresenter,
    CleanupResult,
    ConversationKey,
    Navigation,
    NavigationRegistry,
    Node,
    RenderResult,
)
from aiogram_nav.storage.redis import RedisNavigationRepository


class NoTelegram(BaseSession):
    async def close(self):
        return None

    async def make_request(self, *args, **kwargs):
        raise AssertionError("This probe must not send Telegram requests")

    async def stream_content(self, *args, **kwargs):
        yield b""


def p95(values):
    return sorted(values)[math.ceil(0.95 * len(values)) - 1]


def incoming(index, text):
    return Update(
        update_id=index,
        message=Message(
            message_id=index,
            date=datetime(2026, 1, 1, tzinfo=timezone.utc),
            chat=Chat(id=42, type="private"),
            from_user=User(id=42, is_bot=False, first_name="Benchmark"),
            text=text,
        ),
    )


async def _window(url, engine, age, samples, configuration):
    redis, metrics = client(url)
    prefix = f"benchmark-nav:{uuid4().hex}"
    bot = Bot("123456:ABC", session=NoTelegram())
    dispatcher = Dispatcher(events_isolation=SimpleEventIsolation())
    payload = {"selection": "fixed", "values": [1, 2, 3], "locale": "en"}

    async def cleanup(request):
        return CleanupResult()

    kwargs = dict(redis=redis, prefix=prefix, config=configuration(engine, age + samples + 10))
    if "storage_format" in inspect.signature(RedisNavigationRepository).parameters:
        kwargs["storage_format"] = 3
    repo = RedisNavigationRepository(**kwargs)
    result = []
    phase = "bootstrap"
    completed = 0
    try:
        await redis.ping()
        metrics.reset()
        await repo.initialize()
        startup = metrics.snapshot()
        nav = Navigation(
            registry=NavigationRegistry(roots={"main"}, nodes=[Node("main", renderer="app")]),
            repository=repo,
            presenter=ApplicationPresenter(cleanup=cleanup),
            namespace="benchmark",
        )
        nav.install(dispatcher)
        app = Router()

        @app.message()
        async def handler(message, nav_context):
            if message.text == "track":
                await nav_context.track(
                    "main",
                    params=payload,
                    rendered=RenderResult(f"v{message.message_id}"),
                    operation_id=f"op{message.message_id}",
                )

        dispatcher.include_router(app)
        context = nav.for_conversation(ConversationKey("benchmark", bot.id, 42, 42))
        phase = "fixture"
        for index in range(age):
            await context.track(
                "main",
                params=payload,
                rendered=RenderResult(f"age-{index}"),
                operation_id=f"age-{index}",
            )
            completed += 1
        for kind in ("noop", "track"):
            phase = kind
            latency, roundtrips, sent, received = [], [], [], []
            before = await redis.info("commandstats")
            metrics.reset()
            cpu = time.process_time_ns()
            for index in range(samples):
                previous = metrics.snapshot()
                started = time.perf_counter_ns()
                await dispatcher.feed_update(bot, incoming(age + index + 1, kind))
                latency.append(time.perf_counter_ns() - started)
                snapshot = metrics.snapshot()
                roundtrips.append(snapshot["responses"] - previous["responses"])
                sent.append(snapshot["sent"] - previous["sent"])
                received.append(snapshot["received"] - previous["received"])
            cpu = (time.process_time_ns() - cpu) / samples
            summary = metrics.snapshot()
            after = await redis.info("commandstats")
            server = {
                name.removeprefix("cmdstat_"): value["calls"] - before.get(name, {}).get("calls", 0)
                for name, value in after.items()
                if value["calls"] > before.get(name, {}).get("calls", 0)
            }
            internal = {
                name: count - summary["commands"].get(name, 0)
                for name, count in server.items()
                if name != "info" and count - summary["commands"].get(name, 0) > 0
            }
            result.append(
                dict(
                    scenario=f"redis-dispatch-{kind}",
                    workload=f"redis-dispatch-{kind}/{age}",
                    process_cpu_seconds=[cpu * samples / 1_000_000_000],
                    median_process_cpu_seconds=cpu * samples / 1_000_000_000,
                    calls=samples,
                    cpu_count=1,
                    update_p95_seconds=p95(latency) / 1_000_000_000,
                    update_sample_count=len(latency),
                    raw_latency_seconds=[value / 1_000_000_000 for value in latency],
                    raw_client_round_trips=roundtrips,
                    raw_sent_bytes=sent,
                    raw_received_bytes=received,
                    engine=engine,
                    state_age=age,
                    storage_format=repo.storage_format,
                    status="measured",
                    samples=samples,
                    fixture_id=prefix,
                    fixture_start_age=age,
                    fixture_end_age=age + (samples if kind == "track" else 0),
                    fixture_boundary="whole protected handler; fixed payload and zero history growth; owned disposable prefix",
                    median_cpu_ns=cpu,
                    median_ns=statistics.median(latency),
                    p95_ns=p95(latency),
                    median_client_round_trips=statistics.median(roundtrips),
                    p95_client_round_trips=p95(roundtrips),
                    max_client_round_trips=max(roundtrips),
                    median_sent_bytes=statistics.median(sent),
                    p95_sent_bytes=p95(sent),
                    median_received_bytes=statistics.median(received),
                    p95_received_bytes=p95(received),
                    client_commands=summary["commands"],
                    lua_internal_commands=internal,
                    cold_namespace_bootstrap=startup,
                )
            )
        return result
    except Exception as error:
        return [
            dict(
                scenario="redis-dispatch",
                engine=engine,
                state_age=age,
                status="unavailable",
                error_type=type(error).__name__,
                phase=phase,
                completed_fixture_age=completed,
                fixture_id=prefix,
                completed_scenarios=result,
                partial_scenario=(
                    dict(
                        scenario=f"redis-dispatch-{phase}",
                        raw_latency_seconds=[value / 1_000_000_000 for value in latency],
                        raw_client_round_trips=roundtrips,
                        raw_sent_bytes=sent,
                        raw_received_bytes=received,
                    )
                    if phase in ("noop", "track")
                    else None
                ),
            )
        ]
    finally:
        await dispatcher.fsm.close()
        await repo.close()
        # Only this newly generated, owned benchmark namespace is removed.
        owned = [key async for key in redis.scan_iter(match=f"{prefix}:*")]
        if owned:
            await redis.delete(*owned)
        await redis.aclose()
        await bot.session.close()


def _pool(rows, samples):
    """Pool complete fresh windows; counters cover total_calls, CPU batches calls."""
    first = rows[0]
    expected = ("workload", "scenario", "engine", "state_age", "storage_format", "fixture_boundary")
    for row in rows:
        if any(row[field] != first[field] for field in expected):
            raise ValueError("Redis latency windows have mismatched workload identities")
        if (
            row["status"] != "measured"
            or row["calls"] != samples
            or row["samples"] != samples
            or len(row["process_cpu_seconds"]) != 1
            or row["update_sample_count"] != samples
            or row["fixture_start_age"] != row["state_age"]
            or row["fixture_end_age"]
            != row["state_age"] + (samples if row["scenario"] == "redis-dispatch-track" else 0)
            or any(
                len(row[field]) != samples
                for field in (
                    "raw_latency_seconds",
                    "raw_client_round_trips",
                    "raw_sent_bytes",
                    "raw_received_bytes",
                )
            )
        ):
            raise ValueError("Redis latency window is incomplete")
    fixtures = [row["fixture_id"] for row in rows]
    if len(set(fixtures)) != len(fixtures):
        raise ValueError("Redis latency windows must use distinct fresh fixtures")
    count = len(rows)
    result = dict(first)
    result.update(
        latency_windows=count,
        operations_per_cpu_sample=samples,
        calls=samples,
        total_calls=samples * count,
        counter_operation_count=samples * count,
        samples=samples,
        update_sample_count=samples * count,
        latency_window_fixtures=fixtures,
        latency_window_boundaries=[
            dict(
                window=index,
                start=index * samples,
                stop=(index + 1) * samples,
                operation_count=samples,
                samples=samples,
                state_age=row["fixture_start_age"],
                end_state_age=row["fixture_end_age"],
            )
            for index, row in enumerate(rows)
        ],
    )
    if count == 1:
        return result
    result.pop("fixture_id")
    result.pop("fixture_start_age")
    result.pop("fixture_end_age")
    for field in (
        "raw_latency_seconds",
        "raw_client_round_trips",
        "raw_sent_bytes",
        "raw_received_bytes",
    ):
        result[field] = [value for row in rows for value in row[field]]
    cpu = [row["process_cpu_seconds"][0] for row in rows]
    result.update(
        process_cpu_seconds=cpu,
        median_process_cpu_seconds=statistics.median(cpu),
        cpu_count=count,
        median_cpu_ns=statistics.median(cpu) * 1_000_000_000 / samples,
        update_p95_seconds=p95(result["raw_latency_seconds"]),
        median_ns=statistics.median(result["raw_latency_seconds"]) * 1_000_000_000,
        p95_ns=p95(result["raw_latency_seconds"]) * 1_000_000_000,
    )
    for source, summary in (
        ("raw_client_round_trips", "client_round_trips"),
        ("raw_sent_bytes", "sent_bytes"),
        ("raw_received_bytes", "received_bytes"),
    ):
        result["median_" + summary] = statistics.median(result[source])
        result["p95_" + summary] = p95(result[source])
    result["max_client_round_trips"] = max(result["raw_client_round_trips"])
    for field in ("client_commands", "lua_internal_commands"):
        total = Counter()
        for row in rows:
            total.update(row[field])
        result[field] = dict(total)
    startup = [row["cold_namespace_bootstrap"] for row in rows]
    commands = Counter()
    for row in startup:
        commands.update(row["commands"])
    result["cold_namespace_bootstrap"] = {
        field: sum(row[field] for row in startup)
        for field in ("sent", "received", "responses", "flushes")
    }
    result["cold_namespace_bootstrap"]["commands"] = dict(commands)
    result["cold_namespace_bootstrap_windows"] = startup
    return result


async def workload(url, engine, age, samples, configuration, *, windows=1):
    """Run every requested fixed-age fixture once; never extend its sample count."""
    if type(windows) is not int or windows < 1 or windows > 100:
        raise ValueError("Redis latency windows must be within 1..100")
    complete = []
    groups = {}
    expected = {f"redis-dispatch-{kind}/{age}" for kind in ("noop", "track")}
    for index in range(windows):
        measured = await _window(url, engine, age, samples, configuration)
        if any(row.get("status") != "measured" for row in measured):
            return [
                dict(
                    scenario="redis-dispatch",
                    engine=engine,
                    state_age=age,
                    status="unavailable",
                    latency_windows=windows,
                    completed_latency_windows=index,
                    failed_latency_window=index,
                    failed_window_result=measured,
                    completed_window_results=complete,
                )
            ]
        if {row["workload"] for row in measured} != expected or len(measured) != 2:
            raise ValueError("Redis latency window omitted or duplicated a workload")
        complete.append(measured)
        for row in measured:
            groups.setdefault(row["workload"], []).append(row)
    return [_pool(groups[name], samples) for name in sorted(expected)]
