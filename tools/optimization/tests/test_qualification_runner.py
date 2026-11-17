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
        return SimpleNamespace(returncode=0)

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
