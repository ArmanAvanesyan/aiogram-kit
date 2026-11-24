"""Scheduling control is explicit, fail-closed and confined to a disposable runner."""

import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pytest

SPEC = importlib.util.spec_from_file_location(
    "runner_cpu_control", Path(__file__).parents[1] / "runner_cpu_control.py"
)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)
LAYOUT = [{"cpu": cpu, "package": 0, "core": cpu // 2} for cpu in range(4)]


def test_siblings_are_reserved_together():
    assert MODULE.housekeeping_cpus([0, 1, 2, 3], [0], LAYOUT) == [2, 3]
    with pytest.raises(ValueError, match="disjoint"):
        MODULE.housekeeping_cpus([0, 1], [0], LAYOUT)
    with pytest.raises(ValueError, match="Known"):
        MODULE.housekeeping_cpus([0], [0], [{"cpu": 0, "package": None, "core": None}])


def test_local_runner_cannot_change_scheduling(monkeypatch):
    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
    with pytest.raises(ValueError, match="GitHub-hosted"):
        MODULE.isolate_runner([0], LAYOUT)


def fake_runner(monkeypatch, tmp_path):
    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    monkeypatch.setenv("RUNNER_ENVIRONMENT", "github-hosted")
    monkeypatch.setattr(MODULE.os, "getpid", lambda: 100)
    monkeypatch.setattr(MODULE.os, "getpriority", lambda *args: -20, raising=False)
    monkeypatch.setattr(MODULE.os, "PRIO_PROCESS", 0, raising=False)
    state = {0: [0, 1, 2, 3], 222: [0, 1, 2, 3], 223: [0, 1, 2, 3]}
    monkeypatch.setattr(MODULE.os, "sched_getaffinity", lambda tid: state[tid], raising=False)
    monkeypatch.setattr(
        MODULE.os, "sched_setaffinity", lambda tid, cpus: state.update({tid: cpus}), raising=False
    )
    for tid in (222, 223):
        (tmp_path / "222" / "task" / str(tid)).mkdir(parents=True)
    (tmp_path / "100").mkdir()
    commands = []
    monkeypatch.setattr(
        MODULE.subprocess, "run", lambda command, **kwargs: commands.append(command)
    )
    return state, commands


def test_other_threads_move_but_controller_affinity_does_not(monkeypatch, tmp_path):
    state, commands = fake_runner(monkeypatch, tmp_path)
    proof = MODULE.isolate_runner([0], LAYOUT, tmp_path)
    assert state[222] == state[223] == [2, 3]
    assert state[0] == [0, 1, 2, 3]
    assert commands == [["sudo", "-n", "renice", "-n", "-20", "-p", "100"]]
    assert proof["nice"] == -20 and len(proof["moved_threads"]) == 2
    assert proof["physical_hardware_exclusivity_claimed"] is False


def test_permission_failure_uses_checked_explicit_runner_privilege(monkeypatch, tmp_path):
    state, commands = fake_runner(monkeypatch, tmp_path)

    def denied(*args):
        raise PermissionError("runner service thread")

    def privileged(command, **kwargs):
        commands.append(command)
        if command[2] == "taskset":
            state[int(command[-1])] = [2, 3]

    monkeypatch.setattr(MODULE.os, "sched_setaffinity", denied)
    monkeypatch.setattr(MODULE.subprocess, "run", privileged)
    proof = MODULE.isolate_runner([0], LAYOUT, tmp_path)
    assert all(row["method"] == "sudo-taskset" for row in proof["moved_threads"])
    assert state[222] == state[223] == [2, 3]


def test_privileged_failure_never_starts_measurement(monkeypatch, tmp_path):
    fake_runner(monkeypatch, tmp_path)

    def denied(*args):
        raise PermissionError("denied")

    def failed(command, **kwargs):
        raise MODULE.subprocess.CalledProcessError(1, command)

    monkeypatch.setattr(MODULE.os, "sched_setaffinity", denied)
    monkeypatch.setattr(MODULE.subprocess, "run", failed)
    with pytest.raises(MODULE.subprocess.CalledProcessError):
        MODULE.isolate_runner([0], LAYOUT, tmp_path)


def test_foreign_owner_is_not_changed(monkeypatch, tmp_path):
    _, _ = fake_runner(monkeypatch, tmp_path)
    original = Path.stat
    monkeypatch.setattr(
        Path,
        "stat",
        lambda p, *a, **kw: (
            SimpleNamespace(st_uid=-1) if p.name == "222" else original(p, *a, **kw)
        ),
    )
    proof = MODULE.isolate_runner([0], LAYOUT, tmp_path)
    assert proof["moved_threads"] == []


def test_priority_must_be_confirmed(monkeypatch, tmp_path):
    fake_runner(monkeypatch, tmp_path)
    monkeypatch.setattr(MODULE.os, "getpriority", lambda *args: 0)
    with pytest.raises(RuntimeError, match="priority"):
        MODULE.isolate_runner([0], LAYOUT, tmp_path)
