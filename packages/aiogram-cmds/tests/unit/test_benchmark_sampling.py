"""Declared latency sampling preserves CPU work and every observed tail."""

import importlib.util
import math
from pathlib import Path
from types import SimpleNamespace

import pytest


@pytest.fixture
def driver(monkeypatch):
    path = Path(__file__).parents[2] / "benchmarks" / "run.py"
    if not path.is_file():
        pytest.skip("Source-only benchmark driver is absent from this SDK artifact profile")
    for dependency in ("orjson", "psutil", "pyperf"):
        pytest.importorskip(dependency)
    spec = importlib.util.spec_from_file_location("cmds_sampling_driver", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(
        module.psutil,
        "Process",
        lambda: SimpleNamespace(memory_info=lambda: SimpleNamespace(rss=123)),
    )
    return module


class FakeClock:
    def __init__(self):
        self.now = 0
        self.calls = 0
        self.durations = []
        self.counters = {"translator": 0}

    def call(self):
        self.calls += 1
        duration = 1_000_000 if self.calls % 37 == 0 else self.calls % 11 + 1
        self.durations.append(duration)
        self.now += duration
        self.counters["translator"] += 1

    async def async_call(self):
        self.call()


@pytest.mark.parametrize("asynchronous", [False, True])
@pytest.mark.parametrize("requested,expected_count", [(None, 1000), (3000, 3000)])
async def test_declared_latency_samples_retain_all_values_and_cpu_trials(
    driver, monkeypatch, asynchronous, requested, expected_count
):
    clock = FakeClock()
    monkeypatch.setattr(driver.time, "perf_counter_ns", lambda: clock.now)
    monkeypatch.setattr(driver.time, "process_time_ns", lambda: clock.now)
    arguments = ("confirmation_hit/10", None, 7, clock.counters, 31, 5, requested)
    if asynchronous:
        arguments = (arguments[0], clock.async_call, *arguments[2:])
        result = await driver.sample_async(*arguments)
    else:
        arguments = (arguments[0], clock.call, *arguments[2:])
        result = driver.sample(*arguments)
    assert clock.calls == (5 + 31) * 7 + expected_count
    assert result["loops"] == 7
    assert result["samples"] == 31
    assert result["warmups"] == 5
    assert len(result["cpu_ns"]["values"]) == len(result["wall_ns"]["values"]) == 31
    assert result["calls"]["translator"] == 31 * 7 + expected_count
    observed = result["individual_latency_ns"]
    assert observed["count"] == expected_count
    assert observed["values"] == clock.durations[-expected_count:]
    assert (
        observed["p95"]
        == sorted(observed["values"])[math.ceil(0.95 * expected_count) - 1]
    )
    assert max(observed["values"]) == 1_000_000  # Tail samples remain present.


@pytest.mark.parametrize("asynchronous", [False, True])
async def test_latency_override_does_not_multiply_cpu_only_work(
    driver, monkeypatch, asynchronous
):
    clock = FakeClock()
    monkeypatch.setattr(driver.time, "perf_counter_ns", lambda: clock.now)
    monkeypatch.setattr(driver.time, "process_time_ns", lambda: clock.now)
    if asynchronous:
        result = await driver.sample_async(
            "profile_resolution/100", clock.async_call, 7, {}, 31, 5, 3000
        )
    else:
        result = driver.sample("profile_resolution/100", clock.call, 7, {}, 31, 5, 3000)
    assert clock.calls == (5 + 31) * 7
    assert result["individual_latency_ns"] == {"count": 0, "p95": None, "values": []}


@pytest.mark.parametrize("asynchronous", [False, True])
async def test_fake_network_keeps_one_cpu_operation_per_trial(
    driver, monkeypatch, asynchronous
):
    clock = FakeClock()
    monkeypatch.setattr(driver.time, "perf_counter_ns", lambda: clock.now)
    monkeypatch.setattr(driver.time, "process_time_ns", lambda: clock.now)
    if asynchronous:
        result = await driver.sample_async(
            "fake_telegram_1ms/100", clock.async_call, 7, {}, 31, 5, 3000
        )
    else:
        result = driver.sample("fake_telegram_1ms/100", clock.call, 7, {}, 31, 5, 3000)
    assert result["loops"] == 1
    assert result["samples"] == 31
    assert clock.calls == 5 + 31 + 3000
    assert result["individual_latency_ns"]["count"] == 3000


@pytest.mark.parametrize("value", [0, -1, 1.5, True, "3000"])
@pytest.mark.parametrize("asynchronous", [False, True])
async def test_invalid_programmatic_counts_fail_before_work(
    driver, value, asynchronous
):
    def forbidden():
        pytest.fail("Invalid declared sampling must fail before workload calls")

    with pytest.raises(ValueError, match="positive integer"):
        if asynchronous:
            await driver.sample_async(
                "confirmation_hit/1", forbidden, 7, {}, 31, 5, value
            )
        else:
            driver.sample("confirmation_hit/1", forbidden, 7, {}, 31, 5, value)


@pytest.mark.parametrize("value", ["0", "-1", "1.5", "True", "invalid"])
def test_invalid_cli_counts_are_rejected(driver, value):
    with pytest.raises(SystemExit) as error:
        driver.parse_args(
            ["--output", "unused.json", "--individual-latency-samples", value]
        )
    assert error.value.code == 2


def test_cli_preserves_historical_full_and_quick_defaults(driver):
    full = driver.parse_args(["--output", "unused.json"])
    quick = driver.parse_args(["--output", "unused.json", "--quick"])
    override = driver.parse_args(
        ["--output", "unused.json", "--quick", "--individual-latency-samples", "3000"]
    )
    assert full.individual_latency_samples is quick.individual_latency_samples is None
    assert driver.individual_sample_count(31, full.individual_latency_samples) == 1000
    assert driver.individual_sample_count(5, quick.individual_latency_samples) == 100
    assert (
        driver.individual_sample_count(5, override.individual_latency_samples) == 3000
    )
