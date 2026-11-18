"""Measurement helpers: payload bytes are estimates; server CPU is not RTT time."""

from __future__ import annotations

import hashlib
import importlib.metadata
import math
import platform
import statistics
import sys
import time
from collections import Counter
from pathlib import Path


def percentile(values, fraction=0.95):
    if not values:
        return None
    return sorted(values)[math.ceil(fraction * len(values)) - 1]


def measured_row(scenario, age, engine, samples, cpu, latencies, **extra):
    return dict(
        scenario=scenario,
        workload=f"{scenario}/{age}",
        engine=engine,
        state_age=age,
        calls=samples,
        process_cpu_seconds=cpu,
        median_process_cpu_seconds=statistics.median(cpu) if cpu else None,
        cpu_count=len(cpu),
        raw_latency_seconds=latencies,
        update_p95_seconds=percentile(latencies),
        update_sample_count=len(latencies),
        median_cpu_ns=statistics.median(cpu) * 1e9 / samples if cpu else None,
        **extra,
    )


def payload_bytes(value):
    if isinstance(value, bytes):
        return len(value)
    return len(str(value).encode("utf-8", errors="strict"))


def counted_redis_type():
    from redis.asyncio import Redis

    class CountedRedis(Redis):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self.benchmark_calls = []

        async def execute_command(self, *args, **kwargs):
            started = time.perf_counter()
            try:
                result = await super().execute_command(*args, **kwargs)
            finally:
                self.benchmark_calls.append(
                    {
                        "command": str(args[0]).upper(),
                        "argument_bytes": sum(payload_bytes(value) for value in args),
                        "elapsed_seconds": time.perf_counter() - started,
                    }
                )
            return result

    return CountedRedis


def command_summary(calls):
    commands = Counter(value["command"] for value in calls)
    return {
        "client_round_trips": len(calls),
        "client_commands": dict(commands),
        "lua_calls": sum(commands[name] for name in ("EVAL", "EVALSHA")),
        "direct_commands": sum(
            count for name, count in commands.items() if name not in {"EVAL", "EVALSHA"}
        ),
        "argument_payload_bytes": sum(value["argument_bytes"] for value in calls),
        "lua_server_cpu_seconds": None,
        "lua_time_note": "Client elapsed time includes network/client overhead; no server CPU attribution is claimed.",
    }


def provenance(package="aiogram-idle"):
    import aiogram_idle

    try:
        import resource

        rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * (
            1 if sys.platform == "darwin" else 1024
        )
    except ImportError:
        rss = None
    dist = importlib.metadata.distribution(package)
    direct = dist.read_text("direct_url.json")
    return {
        "package": package,
        "package_version": dist.version,
        "installed_version": dist.version,
        "module_file": aiogram_idle.__file__,
        "direct_url": direct,
        "python": sys.version,
        "os": platform.platform(),
        "cpu": platform.processor(),
        "rss_peak_bytes": rss,
    }


def driver_manifest():
    return {
        path.name: hashlib.sha256(path.read_bytes()).hexdigest()
        for path in Path(__file__).parent.glob("*.py")
    }


def window_boundaries(age, samples, windows, *, advancing=True):
    """End-exclusive observation offsets for independent fixed-age fixtures."""
    return [
        {
            "start": index * samples,
            "stop": (index + 1) * samples,
            "age": age,
            "start_age": age,
            "end_age": age + samples if advancing else age,
            "operations": samples,
            "fresh_fixture": True,
        }
        for index in range(windows)
    ]


def _sum_command_evidence(rows):
    result = dict(rows[0])
    for field in ("client_round_trips", "lua_calls", "direct_commands", "argument_payload_bytes"):
        if field in result:
            result[field] = sum(row[field] for row in rows)
    if "client_commands" in result:
        commands = Counter()
        for row in rows:
            commands.update(row["client_commands"])
        result["client_commands"] = dict(commands)
    return result


async def fresh_latency_windows(run_window, windows):
    """Pool every observation from fresh fixtures; never retry or trim failures.

    Each existing helper constructs and closes one independent backend/runtime.
    `calls` remains the operations in each CPU sample, as in the historical
    memory preset. `total_calls` is the denominator for pooled transport counts.
    """
    if type(windows) is not int or windows < 1:
        raise ValueError("latency windows must be a positive integer")
    rows = []
    for _ in range(windows):
        row = await run_window()
        if rows and any(
            row[key] != rows[0][key]
            for key in ("scenario", "workload", "state_age", "engine", "calls")
        ):
            raise ValueError("Fresh latency windows must use the same fixed fixture shape")
        if (
            type(row["calls"]) is not int
            or row["calls"] < 1
            or len(row["process_cpu_seconds"]) != 1
            or len(row["raw_latency_seconds"]) != row["calls"]
            or row["update_sample_count"] != row["calls"]
        ):
            raise ValueError("Fresh latency window observations do not match operation counts")
        rows.append(row)
    result = _sum_command_evidence(rows)
    cpu = [sample for row in rows for sample in row["process_cpu_seconds"]]
    latencies = [sample for row in rows for sample in row["raw_latency_seconds"]]
    result.update(
        process_cpu_seconds=cpu,
        median_process_cpu_seconds=statistics.median(cpu),
        median_cpu_ns=statistics.median(cpu) * 1e9 / result["calls"],
        cpu_count=len(cpu),
        raw_latency_seconds=latencies,
        update_p95_seconds=percentile(latencies),
        update_sample_count=len(latencies),
        operations_per_cpu_sample=result["calls"],
        total_calls=len(latencies),
        latency_windows=windows,
        latency_window_boundaries=window_boundaries(
            result["state_age"],
            result["calls"],
            windows,
            advancing=result["scenario"] != "redis-dispatcher-noop",
        ),
    )
    for field in ("application_authority_calls", "application_cleanup_calls"):
        if field in result:
            result[field] = sum(row[field] for row in rows)
    if "per_update_round_trips" in result:
        result["per_update_round_trips"] = [
            value for row in rows for value in row["per_update_round_trips"]
        ]
        result["client_round_trips_per_operation"] = (
            result["client_round_trips"] / result["total_calls"]
        )
    if "application_fsm" in result:
        result["application_fsm"] = _sum_command_evidence([row["application_fsm"] for row in rows])
    if "deterministic_budget" in result:
        budget = dict(result["deterministic_budget"])
        budget["observed_max"] = max(row["deterministic_budget"]["observed_max"] for row in rows)
        budget["passed"] = all(row["deterministic_budget"]["passed"] for row in rows)
        result["deterministic_budget"] = budget
    if "storage_diagnostics" in result and windows > 1:
        observations = [row["storage_diagnostics"] for row in rows]
        result["storage_diagnostics_windows"] = observations
        result["storage_diagnostics"] = {
            **result["storage_diagnostics"],
            **{
                field: max(row[field] for row in observations)
                for field in ("hot_value_bytes", "retained_redis_memory_bytes", "redis_keys")
            },
            "aggregation": "Maximum across fresh windows; all per-window observations retained",
        }
    return result
