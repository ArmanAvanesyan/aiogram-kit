"""Fake observations preserve Sentinel's independent CPU and latency phases."""

import ast
import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[3]
DIRECTORY = ROOT / "packages/aiogram-sentinel/benchmarks"
SPEC = importlib.util.spec_from_file_location(
    "sentinel_latency_windows", DIRECTORY / "latency_windows.py"
)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def fake_factory(*, fail_at=None, short_at=None, duplicate=False):
    fixtures = []

    def sample(values):
        index = len(fixtures)
        fixtures.append(index)
        # Include both first-operation cold cost and a large tail; neither is trimmed.
        vector = [1e-3] + [1e-5] * 998 + [2e-3]
        values.extend(vector[:999] if short_at == index else vector)
        if fail_at == index:
            raise RuntimeError("application fixture failed")
        return {
            "fixture_id": "duplicate" if duplicate else f"fixture-{index}",
            "state_age": 0,
            "end_state_age": 1000,
        }

    return sample, fixtures


def test_ten_fresh_thousand_operation_windows_retain_every_cold_and_tail():
    sample, created = fake_factory()
    result = MODULE.collect_latency_windows(sample, 10)
    assert created == list(range(10))
    assert result["latency_windows"] == 10
    assert result["operations_per_latency_window"] == 1000
    assert result["total_latency_calls"] == result["update_sample_count"] == 10000
    assert len(result["latency_window_fixtures"]) == 10
    assert len(set(result["latency_window_fixtures"])) == 10
    assert result["update_latency_seconds"][::1000] == [1e-3] * 10
    assert result["update_latency_seconds"][999::1000] == [2e-3] * 10
    for index, boundary in enumerate(result["latency_window_boundaries"]):
        assert boundary["start"] == index * 1000
        assert boundary["stop"] == (index + 1) * 1000
        assert boundary["operation_count"] == 1000
        assert boundary["state_age"] == 0 and boundary["end_state_age"] == 1000
    assert result["update_p95_seconds"] == 1e-5
    assert "process_cpu_seconds" not in result and "calls" not in result


def test_default_still_collects_exactly_one_original_fixture():
    sample, created = fake_factory()
    result = MODULE.collect_latency_windows(sample)
    assert created == [0]
    assert result["update_sample_count"] == 1000


@pytest.mark.parametrize("short", [False, True])
def test_failed_window_retains_partial_data_and_never_retries_or_skips(short):
    sample, created = fake_factory(fail_at=None if short else 2, short_at=2 if short else None)
    with pytest.raises(MODULE.LatencyWindowFailure) as caught:
        MODULE.collect_latency_windows(sample, 10)
    assert created == [0, 1, 2]
    evidence = caught.value.partial
    assert evidence["completed_windows"] == 2
    assert len(evidence["update_latency_seconds"]) == (2999 if short else 3000)
    assert evidence["failed_window"]["observed_count"] == (999 if short else 1000)
    assert len(evidence["latency_window_boundaries"]) == 2


def test_reused_fixture_fails_instead_of_relabeling_it():
    sample, created = fake_factory(duplicate=True)
    with pytest.raises(MODULE.LatencyWindowFailure):
        MODULE.collect_latency_windows(sample, 10)
    assert created == [0, 1]


@pytest.mark.parametrize("windows", [0, -1, True, 1.5, 101])
def test_invalid_window_count_fails_before_any_fixture(windows):
    sample, created = fake_factory()
    with pytest.raises(ValueError):
        MODULE.collect_latency_windows(sample, windows)
    assert created == []


def test_window_collector_never_adds_clock_sleep_or_gc_calls():
    tree = ast.parse((DIRECTORY / "latency_windows.py").read_text())
    calls = {
        node.func.attr
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
    }
    assert not calls & {"sleep", "collect", "disable", "enable", "set_threshold", "perf_counter"}


def test_driver_keeps_original_cpu_dimensions_and_creates_each_fresh_loop():
    tree = ast.parse((DIRECTORY / "run.py").read_text())
    assignments = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Assign)
        and any(
            isinstance(target, ast.Tuple)
            and [item.id for item in target.elts] == ["count", "repeats", "warmups"]
            for target in node.targets
        )
    ]
    assert len(assignments) == 1
    assert ast.literal_eval(assignments[0].value.orelse) == (50000, 15, 5)
    collectors = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "collect_latency_windows"
    ]
    assert len(collectors) == 1
    callback = collectors[0].args[0]
    assert isinstance(callback, ast.Lambda)
    assert isinstance(callback.body, ast.Call) and callback.body.func.attr == "run"
