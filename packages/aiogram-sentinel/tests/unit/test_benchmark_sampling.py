"""Fresh benchmark observations preserve the original middleware state window."""

import importlib.util
from pathlib import Path

import pytest

SPEC = importlib.util.spec_from_file_location(
    "sentinel_latency_windows",
    Path(__file__).parents[2] / "benchmarks/latency_windows.py",
)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def test_fresh_thousand_operation_fixture_per_requested_window():
    created = []

    def sample(values):
        created.append(object())
        values.extend([0.001] * 999 + [1.0])
        return {
            "fixture_id": str(id(created[-1])),
            "state_age": 0,
            "end_state_age": 1000,
        }

    result = MODULE.collect_latency_windows(sample, 10)
    assert len(created) == len({id(item) for item in created}) == 10
    assert result["update_sample_count"] == 10000
    assert result["update_latency_seconds"][999::1000] == [1.0] * 10
    assert "calls" not in result and "process_cpu_seconds" not in result


def test_failure_keeps_partial_observations_and_never_retries():
    calls = []

    def sample(values):
        calls.append(len(calls))
        values.append(0.5)
        raise RuntimeError("fixture failed")

    with pytest.raises(MODULE.LatencyWindowFailure) as failure:
        MODULE.collect_latency_windows(sample, 10)
    assert calls == [0]
    assert failure.value.partial["update_latency_seconds"] == [0.5]
