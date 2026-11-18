"""Fresh Sentinel latency fixtures; CPU batches remain an independent phase."""

from __future__ import annotations

import math
from collections.abc import Callable
from typing import Any

OPERATIONS_PER_WINDOW = 1000


class LatencyWindowFailure(RuntimeError):
    def __init__(self, message: str, partial: dict[str, Any]) -> None:
        super().__init__(message)
        self.partial = partial


def collect_latency_windows(
    sample: Callable[[list[float]], dict[str, Any]], windows: int = 1
) -> dict[str, Any]:
    """Retain every observation; no retry, tail trimming or collector/clock tuning."""
    if type(windows) is not int or not 1 <= windows <= 100:
        raise ValueError("latency windows must be an integer in 1..100")
    latencies: list[float] = []
    boundaries: list[dict[str, Any]] = []
    fixtures: list[str] = []
    for index in range(windows):
        values: list[float] = []
        try:
            fixture = sample(values)
            if (
                len(values) != OPERATIONS_PER_WINDOW
                or any(
                    type(value) not in (int, float)
                    or not math.isfinite(value)
                    or value <= 0
                    for value in values
                )
                or not isinstance(fixture, dict)
                or not isinstance(fixture.get("fixture_id"), str)
                or not fixture["fixture_id"]
                or fixture["fixture_id"] in fixtures
                or type(fixture.get("state_age")) is not int
                or fixture["state_age"] != 0
                or type(fixture.get("end_state_age")) is not int
                or fixture["end_state_age"] != OPERATIONS_PER_WINDOW
            ):
                raise ValueError("Incomplete or reused Sentinel latency fixture")
        except Exception as error:
            # Keep completed windows and even an incomplete/invalid failing vector.
            raise LatencyWindowFailure(
                f"Sentinel latency window {index} failed: {error}",
                {
                    "requested_windows": windows,
                    "completed_windows": len(boundaries),
                    "update_latency_seconds": [*latencies, *values],
                    "latency_window_boundaries": boundaries,
                    "latency_window_fixtures": fixtures,
                    "failed_window": {
                        "window": index,
                        "start": len(latencies),
                        "stop": len(latencies) + len(values),
                        "observed_count": len(values),
                        "error": str(error),
                    },
                },
            ) from error
        fixtures.append(fixture["fixture_id"])
        start = len(latencies)
        latencies.extend(values)
        boundaries.append(
            {
                "window": index,
                "start": start,
                "stop": len(latencies),
                "operation_count": OPERATIONS_PER_WINDOW,
                "state_age": 0,
                "end_state_age": OPERATIONS_PER_WINDOW,
                "fresh_fixture": True,
            }
        )
    return {
        "latency_measurement_phase": "separate-from-cpu-batches",
        "latency_windows": windows,
        "operations_per_latency_window": OPERATIONS_PER_WINDOW,
        "total_latency_calls": len(latencies),
        "update_latency_seconds": latencies,
        "update_sample_count": len(latencies),
        "update_p95_seconds": sorted(latencies)[math.ceil(0.95 * len(latencies)) - 1],
        "latency_window_boundaries": boundaries,
        "latency_window_fixtures": fixtures,
    }
