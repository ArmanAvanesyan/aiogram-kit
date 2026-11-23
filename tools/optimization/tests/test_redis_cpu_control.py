"""An owned service is pinned once, observed exactly, and never silently moved."""

import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

SPEC = importlib.util.spec_from_file_location(
    "redis_cpu_control", Path(__file__).parents[1] / "redis_cpu_control.py"
)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def docker(monkeypatch, *, known=True, same_core=False):
    state = {
        "container_id": "a" * 64,
        "image_id": "sha256:" + "b" * 64,
        "pid": 123,
        "cpuset_cpus": "",
        "affinity": [0, 1, 2, 3],
    }
    calls = []

    def run(command, **kwargs):
        calls.append(command)
        if command[1] == "update":
            state["cpuset_cpus"] = command[3]
            state["affinity"] = [int(command[3])]
            return SimpleNamespace(stdout="updated")
        assert command[1] == "inspect"
        # This deliberately contains no environment/secret fields.
        assert "Env" not in command[3]
        return SimpleNamespace(
            stdout=json.dumps({key: value for key, value in state.items() if key != "affinity"})
        )

    monkeypatch.setattr(MODULE.subprocess, "run", run)
    monkeypatch.setattr(
        MODULE.os,
        "sched_getaffinity",
        lambda pid: {0, 1, 2, 3} if pid == 0 else set(state["affinity"]),
        raising=False,
    )
    layout = [
        {
            "cpu": cpu,
            "package": 0 if known else None,
            "core": (0 if same_core else cpu // 2) if known else None,
        }
        for cpu in range(4)
    ]
    monkeypatch.setattr(MODULE, "topology", lambda cpus: layout)
    return state, calls


def test_disjoint_service_prefers_different_exposed_core_and_verifies_actual_affinity(monkeypatch):
    _, calls = docker(monkeypatch)
    control = MODULE.prepare_service("a" * 64, [0])
    assert MODULE.valid_control(control)
    assert control["service"]["cpu_affinity"] == [2]
    assert control["physical_core_disjoint"] is True
    assert control["physical_isolation_claimed"] is False
    MODULE.verify_service(control)
    assert len([call for call in calls if call[1] == "update"]) == 1


@pytest.mark.parametrize("known,same_core,physical", [(False, False, None), (True, True, False)])
def test_logical_only_fallback_is_explicit(monkeypatch, known, same_core, physical):
    docker(monkeypatch, known=known, same_core=same_core)
    control = MODULE.prepare_service("a" * 64, [0])
    assert control["service"]["cpu_affinity"] == [1]
    assert control["physical_core_disjoint"] is physical
    assert MODULE.valid_control(control)


@pytest.mark.parametrize(
    "field,value",
    [
        ("pid", 456),
        ("affinity", [0]),
        ("cpuset_cpus", "0"),
        ("image_id", "sha256:" + "c" * 64),
    ],
)
def test_changed_service_identity_or_mask_is_not_reselected(monkeypatch, field, value):
    state, calls = docker(monkeypatch)
    control = MODULE.prepare_service("a" * 64, [0])
    state[field] = value
    with pytest.raises(ValueError, match="changed"):
        MODULE.verify_service(control)
    assert len([call for call in calls if call[1] == "update"]) == 1


def test_requires_explicit_supported_disjoint_client_before_docker_mutation(monkeypatch):
    _, calls = docker(monkeypatch)
    with pytest.raises(ValueError, match="explicit"):
        MODULE.prepare_service("a" * 64, None)
    with pytest.raises(ValueError, match="disjoint"):
        MODULE.prepare_service("a" * 64, [0, 1, 2, 3])
    assert calls == []


def test_invalid_service_identifier_never_invokes_docker(monkeypatch):
    _, calls = docker(monkeypatch)
    with pytest.raises(ValueError, match="explicit Docker"):
        MODULE.observe_service("--other-container")
    assert calls == []


def test_same_client_service_cpu_and_false_physical_claim_are_invalid(monkeypatch):
    docker(monkeypatch)
    control = MODULE.prepare_service("a" * 64, [0])
    control["service"]["cpu_affinity"] = [0]
    control["service"]["cpuset_cpus"] = "0"
    assert not MODULE.valid_control(control)
    control = MODULE.prepare_service("a" * 64, [0])
    control["physical_isolation_claimed"] = True
    assert not MODULE.valid_control(control)


@pytest.mark.parametrize("value", ["-1", "5-2", "1-999999999", None, True, "a"])
def test_invalid_cpuset_does_not_expand_or_parse_ambiguously(value):
    with pytest.raises(ValueError, match="CPU set"):
        MODULE.cpu_list(value)
