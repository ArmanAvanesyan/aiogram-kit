"""The portable driver reports raw evidence without self-qualifying."""

import asyncio
import json
import subprocess
import sys
from pathlib import Path

from benchmarks.support import command_summary, measured_row, percentile, provenance
from benchmarks.workloads import memory_workload


def test_nearest_rank_p95_and_raw_cpu_samples():
    row = measured_row("example", 50, "python", 100, [0.1] * 10, list(range(100)))
    assert row["process_cpu_seconds"] == [0.1] * 10
    assert row["cpu_count"] == 10
    assert row["update_sample_count"] == 100
    assert row["update_p95_seconds"] == 94
    assert percentile([]) is None


def test_network_counts_do_not_claim_lua_cpu():
    summary = command_summary(
        [
            {"command": "EVALSHA", "argument_bytes": 10, "elapsed_seconds": 0.1},
            {"command": "GET", "argument_bytes": 2, "elapsed_seconds": 0.01},
        ]
    )
    assert summary["client_round_trips"] == 2
    assert summary["lua_calls"] == 1
    assert summary["direct_commands"] == 1
    assert summary["argument_payload_bytes"] == 12
    assert summary["lua_server_cpu_seconds"] is None


def test_representative_memory_workload_uses_raw_samples():
    row = asyncio.run(memory_workload(1, "python", 3, 2))
    assert row["calls"] == 3
    assert len(row["process_cpu_seconds"]) == 2
    assert len(row["raw_latency_seconds"]) == 6
    assert row["client_round_trips"] == 0
    assert row["application_authority_calls"] > 0


def test_provenance_comes_from_installed_distribution():
    report = provenance()
    assert report["package"] == "aiogram-idle"
    assert report["module_file"]
    assert report["installed_version"]


def test_controller_never_modifies_import_search_path():
    directory = Path(__file__).parents[1] / "benchmarks"
    for source in directory.glob("*.py"):
        assert "sys.path." not in source.read_text()


def test_standalone_controller_does_not_import_nav(tmp_path):
    # Inspect imported modules in a fresh interpreter after executing the actual
    # controller's ordinary path. The optional distribution may be installed.
    output = tmp_path / "benchmark.json"
    driver = Path(__file__).parents[1] / "benchmarks" / "run.py"
    script = (
        "import runpy,sys; "
        f'sys.argv=[{str(driver)!r},"--output",{str(output)!r},"--quick","--ages","1",'
        '"--samples","2","--skip-admission","--allow-editable"]; '
        # run_path doesn't add its directory like Python script execution does;
        # use the package route without any import path modification instead.
        'runpy.run_module("benchmarks.run",run_name="__main__"); '
        'assert not any(n=="aiogram_nav" or n.startswith("aiogram_nav.") for n in sys.modules)'
    )
    subprocess.run([sys.executable, "-c", script], check=True)
    report = json.loads(output.read_text())
    assert report["qualification"] is False
    assert report["representative_workload"] == "memory-activate-touch/50"


def test_fresh_latency_windows_keep_all_observations_and_per_operation_denominators():
    from benchmarks.support import fresh_latency_windows

    seen = []

    async def window():
        index = len(seen)
        seen.append(index)
        values = [0.3 if index == 1 else 0.01] * 100
        return measured_row(
            "redis-track",
            50,
            "python",
            100,
            [float(index + 1)],
            values,
            client_round_trips=200,
            client_commands={"EVALSHA": 100, "GET": 100},
            lua_calls=100,
            direct_commands=100,
            argument_payload_bytes=300,
            lua_server_cpu_seconds=None,
            per_update_round_trips=[2] * 100,
            application_cleanup_calls=150,
            application_fsm={
                "client_round_trips": 100,
                "client_commands": {"GET": 100},
                "lua_calls": 0,
                "direct_commands": 100,
                "argument_payload_bytes": 10,
            },
            deterministic_budget={
                "max_library_round_trips": 20,
                "observed_max": 21 if index == 1 else 2,
                "passed": index != 1,
            },
            storage_diagnostics={
                "hot_value_bytes": 10 + index,
                "retained_redis_memory_bytes": 100 + index,
                "redis_keys": index + 1,
            },
        )

    row = asyncio.run(fresh_latency_windows(window, 3))
    assert seen == [0, 1, 2]
    assert row["calls"] == row["operations_per_cpu_sample"] == 100
    assert row["total_calls"] == row["update_sample_count"] == 300
    assert row["latency_windows"] == row["cpu_count"] == 3
    assert row["process_cpu_seconds"] == [1.0, 2.0, 3.0]
    assert row["median_cpu_ns"] == 2 * 1e9 / 100
    assert row["raw_latency_seconds"] == [0.01] * 100 + [0.3] * 100 + [0.01] * 100
    assert row["update_p95_seconds"] == 0.3  # Slow window is retained, not trimmed.
    assert row["client_round_trips"] == 600
    assert row["client_round_trips_per_operation"] == 2
    assert row["client_commands"] == {"EVALSHA": 300, "GET": 300}
    assert row["application_fsm"]["client_round_trips"] == 300
    assert row["application_cleanup_calls"] == 450
    assert row["per_update_round_trips"] == [2] * 300
    assert row["deterministic_budget"]["observed_max"] == 21
    assert row["deterministic_budget"]["passed"] is False
    assert row["storage_diagnostics"]["retained_redis_memory_bytes"] == 102
    assert len(row["storage_diagnostics_windows"]) == 3
    assert row["latency_window_boundaries"] == [
        {
            "start": offset,
            "stop": offset + 100,
            "age": 50,
            "start_age": 50,
            "end_age": 150,
            "operations": 100,
            "fresh_fixture": True,
        }
        for offset in (0, 100, 200)
    ]


def test_failed_latency_window_propagates_instead_of_sampling_a_replacement():
    from benchmarks.support import fresh_latency_windows

    calls = []

    async def window():
        calls.append(1)
        if len(calls) == 2:
            raise RuntimeError("fixture failed")
        return measured_row("memory-track", 50, "python", 2, [0.1], [0.01, 0.01])

    import pytest

    with pytest.raises(RuntimeError, match="fixture failed"):
        asyncio.run(fresh_latency_windows(window, 3))
    assert len(calls) == 2


def test_fresh_windows_reject_count_mismatch_and_nonpositive_window_count():
    import pytest

    from benchmarks.support import fresh_latency_windows

    calls = []

    async def malformed():
        calls.append(1)
        return measured_row("memory-track", 50, "python", 100, [0.1], [0.01])

    for count in (0, -1, True):
        with pytest.raises(ValueError, match="positive integer"):
            asyncio.run(fresh_latency_windows(malformed, count))
    assert not calls
    with pytest.raises(ValueError, match="operation counts"):
        asyncio.run(fresh_latency_windows(malformed, 1))


def test_redis_windows_recreate_fixed_age_fixture_instead_of_growing_one_conversation(monkeypatch):
    from types import SimpleNamespace

    from benchmarks import workloads
    from benchmarks.support import fresh_latency_windows

    fixtures, closed, cleaned = [], [], []

    class Backend:
        def __init__(self, index):
            self._store = SimpleNamespace(prefix=f"fresh-{index}")
            self.client = SimpleNamespace(benchmark_calls=[])
            self.indices = []

            async def aclose():
                pass

            self.client.aclose = aclose

        async def close(self):
            closed.append(self._store.prefix)

    async def backend(url, engine, capacity):
        assert capacity == 2 * (50 + 100) + 32
        value = Backend(len(fixtures))
        fixtures.append(value)
        return value, value.client

    async def initialize(value):
        runtime = SimpleNamespace(for_conversation=lambda key: value)
        return runtime, SimpleNamespace(calls=0)

    async def accept(context, index, activity):
        context.indices.append(index)
        context.client.benchmark_calls.append(
            {"command": "EVALSHA", "argument_bytes": 1, "elapsed_seconds": 0.001}
        )
        return object()

    async def diagnostics(client, value):
        return {"hot_value_bytes": 10, "retained_redis_memory_bytes": 100, "redis_keys": 4}

    async def cleanup(client, prefix):
        cleaned.append(prefix)

    monkeypatch.setattr(workloads, "redis_backend", backend)
    monkeypatch.setattr(workloads, "initialize", initialize)
    monkeypatch.setattr(workloads, "accept", accept)
    monkeypatch.setattr(workloads, "storage_diagnostics", diagnostics)
    monkeypatch.setattr(workloads, "cleanup_prefix", cleanup)
    row = asyncio.run(
        fresh_latency_windows(lambda: workloads.redis_workload("unused", 50, "python", 100), 2)
    )
    assert len(fixtures) == 2
    assert fixtures[0] is not fixtures[1]
    assert [fixture.indices for fixture in fixtures] == [list(range(150)), list(range(150))]
    assert closed == cleaned == ["fresh-0", "fresh-1"]
    assert row["total_calls"] == 200
    assert row["per_update_round_trips"] == [1] * 200
    assert row["client_round_trips"] == 200  # Warmup calls excluded in each fixture.
