"""Qualification must keep paired runs serial and retain failed attempts."""

import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

PATH = Path(__file__).parents[1] / "qualify_native.py"
SPEC = importlib.util.spec_from_file_location("qualify_native", PATH)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def arguments(monkeypatch, tmp_path):
    protocol = tmp_path / "protocol.json"
    protocol.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "gate": MODULE.GATE,
                "samples": MODULE.SAMPLES,
                "cpu_workloads": {"aiogram-idle": ["memory-activate-touch/50"]},
                "required_latency": {"aiogram-idle": ["redis-track/50"]},
                "order": ["python-a", "rust-a", "rust-b", "python-b"],
            }
        )
    )
    monkeypatch.setattr(
        MODULE.sys,
        "argv",
        [
            str(PATH),
            "--python",
            "/isolated/bin/python",
            "--redis-url",
            "redis://localhost:6379",
            "--output",
            str(tmp_path / "results"),
            "--protocol",
            str(protocol),
        ],
    )


def test_serial_paired_runs_preserve_nonqualifying_result(monkeypatch, tmp_path):
    arguments(monkeypatch, tmp_path)
    calls = []

    def run(command, **kwargs):
        calls.append(command)
        if "--output" in command:
            Path(command[command.index("--output") + 1]).write_text(
                json.dumps({"qualified": False, "failures": ["CPU improvement below 20%"]})
            )
        return SimpleNamespace(returncode=1 if "--output" in command else 0)

    monkeypatch.setattr(MODULE.subprocess, "run", run)
    assert MODULE.main() == 1
    assert len(calls) == 5
    assert [command[command.index("--profile") + 1] for command in calls[:4]] == [
        "optimized",
        "native",
        "native",
        "optimized",
    ]
    for command in calls[:4]:
        assert "--quick" not in command
        assert "--driver-arg=--combined" in command
        assert command[command.index("--peer-package") + 1] == "aiogram-nav"
    summary = json.loads((tmp_path / "results/qualification-summary.json").read_text())
    assert summary["performance_gates"]["aiogram-idle"]["qualified"] is False
    assert summary["publication_performed"] is False


def test_benchmark_failure_cannot_produce_qualified_summary(monkeypatch, tmp_path):
    arguments(monkeypatch, tmp_path)
    monkeypatch.setattr(MODULE.subprocess, "run", lambda *a, **k: SimpleNamespace(returncode=1))
    with pytest.raises(RuntimeError, match="Benchmark failed"):
        MODULE.main()
    assert not (tmp_path / "results/qualification-summary.json").exists()
    assert (tmp_path / "results/aiogram-idle/python-a.log").is_file()


def test_selected_package_requires_predeclared_workloads(monkeypatch, tmp_path):
    arguments(monkeypatch, tmp_path)
    MODULE.sys.argv += ["--package", "aiogram-cmds"]
    with pytest.raises(ValueError, match="predeclared"):
        MODULE.main()


def test_existing_results_are_never_overwritten(monkeypatch, tmp_path):
    arguments(monkeypatch, tmp_path)
    output = tmp_path / "results"
    output.mkdir()
    evidence = output / "old-result.json"
    evidence.write_text('{"qualified": false}')
    with pytest.raises(ValueError, match="retain earlier"):
        MODULE.main()
    assert evidence.read_text() == '{"qualified": false}'


@pytest.mark.parametrize(
    "field,value",
    [
        ("order", ["python-a", "rust-a", "rust-a", "python-b"]),
        ("order", ["../escaped", "rust-a", "rust-b", "python-b"]),
        ("gate", {**MODULE.GATE, "maximum_rust_python_cpu_ratio": 1.0}),
        ("samples", {**MODULE.SAMPLES, "cpu_repeats_minimum": 1}),
        ("cpu_workloads", {"../escaped": ["core"]}),
        ("cpu_workloads", {"aiogram-idle": []}),
        ("required_latency", {}),
        ("schema_version", True),
    ],
)
def test_invalid_protocol_is_rejected_before_output(monkeypatch, tmp_path, field, value):
    arguments(monkeypatch, tmp_path)
    path = tmp_path / "protocol.json"
    protocol = json.loads(path.read_text())
    protocol[field] = value
    path.write_text(json.dumps(protocol))
    with pytest.raises(ValueError):
        MODULE.main()
    assert not (tmp_path / "results").exists()


@pytest.mark.parametrize(
    "qualified,failures,status",
    [
        (True, [], 1),
        (True, [], 2),
        (False, ["missed CPU"], 0),
        (True, ["missed CPU"], 0),
        (False, [], 1),
        ("false", [], 0),
    ],
)
def test_comparator_errors_never_qualify(tmp_path, qualified, failures, status):
    path = tmp_path / "native-gate.json"
    path.write_text(json.dumps({"qualified": qualified, "failures": failures}))
    with pytest.raises(RuntimeError):
        MODULE.checked_comparison(path, status)


def test_output_reservation_is_exclusive(tmp_path):
    output = tmp_path / "attempt"
    output.mkdir()
    MODULE.own_output(output)
    with pytest.raises(ValueError):
        MODULE.own_output(output)
    assert (output / ".qualification-owner").is_file()


def test_comparator_process_error_cannot_leave_a_successful_summary(monkeypatch, tmp_path):
    arguments(monkeypatch, tmp_path)

    def run(command, **kwargs):
        if "--output" in command:
            Path(command[command.index("--output") + 1]).write_text(
                json.dumps({"qualified": True, "failures": []})
            )
            return SimpleNamespace(returncode=2)
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(MODULE.subprocess, "run", run)
    with pytest.raises(RuntimeError, match="qualification withheld"):
        MODULE.main()
    assert not (tmp_path / "results/qualification-summary.json").exists()


def test_output_reservation_handles_concurrent_empty_checks(monkeypatch, tmp_path):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier

    output = tmp_path / "attempt"
    output.mkdir()
    barrier = Barrier(2)
    original = Path.iterdir

    def concurrent_empty(path):
        if path == output:
            barrier.wait(timeout=5)
            return iter(())
        return original(path)

    def reserve():
        try:
            MODULE.own_output(output)
            return True
        except ValueError:
            return False

    monkeypatch.setattr(Path, "iterdir", concurrent_empty)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: reserve(), range(2)))
    assert sorted(results) == [False, True]


def test_affinity_is_selected_once_and_forwarded_identically(monkeypatch, tmp_path):
    arguments(monkeypatch, tmp_path)
    MODULE.sys.argv += ["--cpu-affinity", "auto"]
    selections = []

    def selected(value):
        selections.append(value)
        return [3]

    monkeypatch.setattr(MODULE, "resolve_affinity", selected)
    calls = []

    def run(command, **kwargs):
        calls.append(command)
        if "--output" in command:
            Path(command[command.index("--output") + 1]).write_text(
                json.dumps(
                    {
                        "qualified": False,
                        "failures": ["latency regression"],
                    }
                )
            )
        return SimpleNamespace(returncode=1 if "--output" in command else 0)

    monkeypatch.setattr(MODULE.subprocess, "run", run)
    assert MODULE.main() == 1
    assert selections == ["auto"]
    assert [call[call.index("--cpu-affinity") + 1] for call in calls[:4]] == ["3"] * 4
    summary = json.loads((tmp_path / "results/qualification-summary.json").read_text())
    assert summary["requested_cpu_affinity"] == [3]


def test_auto_affinity_uses_topology_without_timing_feedback(monkeypatch):
    monkeypatch.setattr(MODULE.os, "sched_getaffinity", lambda pid: {2, 3, 5}, raising=False)
    monkeypatch.setattr(MODULE.os, "sched_setaffinity", lambda *args: None, raising=False)

    def read(path, *args, **kwargs):
        cpu = int(str(path).split("/cpu/cpu")[1].split("/")[0])
        return "0" if path.name == "physical_package_id" else str({2: 1, 3: 0, 5: 0}[cpu])

    monkeypatch.setattr(MODULE.Path, "read_text", read)
    assert MODULE.resolve_affinity("auto") == [3]
    assert MODULE.resolve_affinity("5,2") == [2, 5]
    with pytest.raises(ValueError, match="available"):
        MODULE.resolve_affinity("8")


def test_qualified_comparator_cannot_claim_different_affinity(tmp_path):
    report = tmp_path / "gate.json"
    report.write_text(
        json.dumps(
            {
                "qualified": True,
                "failures": [],
                "measurement_controls": {
                    "schema_version": 1,
                    "gc_policy": "unchanged",
                    "affinity_policy": "pinned",
                    "cpu_affinity": [4],
                },
            }
        )
    )
    with pytest.raises(RuntimeError, match="host controls"):
        MODULE.checked_comparison(report, 0, [3])


def test_requested_affinity_fails_if_platform_or_cpu_unavailable(monkeypatch):
    monkeypatch.delattr(MODULE.os, "sched_getaffinity", raising=False)
    with pytest.raises(ValueError, match="unsupported"):
        MODULE.resolve_affinity("auto")
    monkeypatch.setattr(MODULE.os, "sched_getaffinity", lambda pid: set(), raising=False)
    monkeypatch.setattr(MODULE.os, "sched_setaffinity", lambda *args: None, raising=False)
    with pytest.raises(ValueError, match="No available CPU"):
        MODULE.resolve_affinity("auto")


def test_auto_affinity_without_topology_uses_first_allowed_cpu(monkeypatch):
    monkeypatch.setattr(MODULE.os, "sched_getaffinity", lambda pid: {8, 3, 5}, raising=False)
    monkeypatch.setattr(MODULE.os, "sched_setaffinity", lambda *args: None, raising=False)

    def unavailable(*args, **kwargs):
        raise OSError("topology unavailable")

    monkeypatch.setattr(MODULE.Path, "read_text", unavailable)
    assert MODULE.resolve_affinity("auto") == [3]


def test_stronger_sampling_flags_forward_without_changing_fixed_age_window(monkeypatch, tmp_path):
    arguments(monkeypatch, tmp_path)
    MODULE.sys.argv += [
        "--cpu-samples",
        "30",
        "--latency-windows",
        "10",
        "--individual-latency-samples",
        "3000",
    ]
    calls = []

    def run(command, **kwargs):
        calls.append(command)
        if "--output" in command:
            Path(command[command.index("--output") + 1]).write_text(
                json.dumps(
                    {
                        "qualified": False,
                        "failures": ["latency regression"],
                    }
                )
            )
        return SimpleNamespace(returncode=1 if "--output" in command else 0)

    monkeypatch.setattr(MODULE.subprocess, "run", run)
    assert MODULE.main() == 1
    for command in calls[:4]:
        extra = [
            item.removeprefix("--driver-arg=")
            for item in command
            if item.startswith("--driver-arg=")
        ]
        assert extra[extra.index("--ages") + 1] == "50"
        assert extra[extra.index("--samples") + 1] == "100"
        assert extra[extra.index("--cpu-samples") + 1] == "30"
        assert extra[extra.index("--latency-windows") + 1] == "10"
        plan = json.loads(command[command.index("--sampling-plan") + 1])
        assert plan["cpu_repeats"] == 30 and plan["additional_latency_windows"] == 10
    declaration = json.loads((tmp_path / "results/host-controls.json").read_text())
    assert declaration["sampling_plans"]["aiogram-idle"]["operations_per_window"] == 100
    assert MODULE.driver_arguments("aiogram-cmds", 30, 10, 3000) == [
        "--individual-latency-samples",
        "3000",
    ]


@pytest.mark.parametrize(
    "arguments_extra",
    [
        ["--cpu-samples", "9"],
        ["--latency-windows", "0"],
        ["--individual-latency-samples", "999"],
    ],
)
def test_stronger_options_cannot_reduce_historical_sampling(monkeypatch, tmp_path, arguments_extra):
    arguments(monkeypatch, tmp_path)
    MODULE.sys.argv += arguments_extra
    with pytest.raises(ValueError, match="historical minima"):
        MODULE.main()
    assert not (tmp_path / "results").exists()


def test_comparator_cannot_promote_a_different_sampling_declaration(tmp_path):
    plan = MODULE.sampling_plan("aiogram-nav", 30, 10, 3000)
    controls = {
        "schema_version": 2,
        "affinity_policy": "pinned",
        "cpu_affinity": [2],
        "host_cpu_count": 8,
        "effective_cpu_count": 1,
        "gc_policy": "unchanged",
        "gc_enabled": True,
        "gc_thresholds": [700, 10, 10],
        "controller_sha256": "d" * 64,
        "service_cpu_control": None,
        "sampling_plan": MODULE.sampling_plan("aiogram-nav", 10, 1, 1000),
    }
    report = tmp_path / "gate.json"
    report.write_text(
        json.dumps({"qualified": True, "failures": [], "measurement_controls": controls})
    )
    with pytest.raises(RuntimeError, match="host controls"):
        MODULE.checked_comparison(report, 0, [2], plan)
