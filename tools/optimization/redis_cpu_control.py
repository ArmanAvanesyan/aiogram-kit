"""Explicit controls for an owned disposable Docker Redis, never discovered apps."""

from __future__ import annotations

import json
import os
import re
import subprocess
from pathlib import Path

INSPECT = (
    '{"container_id":{{json .Id}},"image_id":{{json .Image}},'
    '"pid":{{json .State.Pid}},"cpuset_cpus":{{json .HostConfig.CpusetCpus}}}'
)


def cpu_list(value: object) -> list[int] | None:
    if value == "":
        return None
    if (
        not isinstance(value, str)
        or re.fullmatch(r"[0-9]+(?:-[0-9]+)?(?:,[0-9]+(?:-[0-9]+)?)*", value) is None
    ):
        raise ValueError("Malformed Docker CPU set")
    result: set[int] = set()
    for item in value.split(","):
        bounds = [int(part) for part in item.split("-")]
        first, last = bounds[0], bounds[-1]
        if last < first or last - first > 4096:
            raise ValueError("Malformed or oversized Docker CPU set")
        result.update(range(first, last + 1))
    return sorted(result)


def topology(cpus: list[int]) -> list[dict]:
    values = []
    for cpu in cpus:
        root = Path(f"/sys/devices/system/cpu/cpu{cpu}/topology")
        try:
            package = int((root / "physical_package_id").read_text())
            core = int((root / "core_id").read_text())
            if package < 0 or core < 0:
                raise ValueError("Unavailable physical topology")
        except (OSError, ValueError):
            package = core = None
        values.append({"cpu": cpu, "package": package, "core": core})
    return values


def observe_service(container_id: str) -> dict:
    if re.fullmatch(r"[a-f0-9]{12,64}", container_id) is None:
        raise ValueError("An explicit Docker service container ID is required")
    result = subprocess.run(
        ["docker", "inspect", "--format", INSPECT, container_id],
        check=True,
        capture_output=True,
        text=True,
    )
    value = json.loads(result.stdout)
    if (
        not isinstance(value, dict)
        or not isinstance(value.get("container_id"), str)
        or re.fullmatch(r"[a-f0-9]{64}", value["container_id"]) is None
        or not value["container_id"].startswith(container_id)
        or not isinstance(value.get("image_id"), str)
        or re.fullmatch(r"sha256:[a-f0-9]{64}", value["image_id"]) is None
        or type(value.get("pid")) is not int
        or value["pid"] <= 0
    ):
        raise ValueError("Invalid or stopped Docker service identity")
    cpu_list(value.get("cpuset_cpus"))
    value["cpu_affinity"] = sorted(os.sched_getaffinity(value["pid"]))
    return value


def valid_control(value: object) -> bool:
    if not isinstance(value, dict) or set(value) != {
        "schema_version",
        "mode",
        "client_cpu_affinity",
        "service",
        "available_topology",
        "physical_core_disjoint",
        "physical_isolation_claimed",
    }:
        return False
    client, service = value["client_cpu_affinity"], value["service"]
    if (
        type(value["schema_version"]) is not int
        or value["schema_version"] != 1
        or value["mode"] != "docker-disjoint-logical"
        or value["physical_isolation_claimed"] is not False
        or not (
            value["physical_core_disjoint"] is None or type(value["physical_core_disjoint"]) is bool
        )
        or not isinstance(client, list)
        or not client
        or any(type(cpu) is not int or cpu < 0 for cpu in client)
        or sorted(set(client)) != client
        or not isinstance(service, dict)
        or set(service)
        != {
            "container_id",
            "image_id",
            "pid",
            "cpuset_cpus",
            "cpu_affinity",
        }
    ):
        return False
    try:
        configured = cpu_list(service["cpuset_cpus"])
        affinity = service["cpu_affinity"]
        if (
            not isinstance(affinity, list)
            or len(affinity) != 1
            or type(affinity[0]) is not int
            or affinity[0] < 0
            or configured != affinity
            or set(client) & set(affinity)
            or type(service["pid"]) is not int
            or service["pid"] <= 0
            or not isinstance(service["container_id"], str)
            or re.fullmatch(r"[a-f0-9]{64}", service["container_id"]) is None
            or not isinstance(service["image_id"], str)
            or re.fullmatch(r"sha256:[a-f0-9]{64}", service["image_id"]) is None
        ):
            return False
        items = value["available_topology"]
        if not isinstance(items, list) or not items:
            return False
        index = {}
        for item in items:
            if (
                not isinstance(item, dict)
                or set(item) != {"cpu", "package", "core"}
                or type(item["cpu"]) is not int
                or item["cpu"] < 0
                or item["cpu"] in index
                or any(
                    part is not None and (type(part) is not int or part < 0)
                    for part in (item["package"], item["core"])
                )
                or ((item["package"] is None) != (item["core"] is None))
            ):
                return False
            index[item["cpu"]] = (item["package"], item["core"])
        selected = client + affinity
        if not set(selected) <= set(index):
            return False
        known = all(index[cpu][0] is not None for cpu in selected)
        distinct = index[affinity[0]] not in {index[cpu] for cpu in client} if known else None
        return value["physical_core_disjoint"] == distinct
    except (TypeError, ValueError):
        return False


def prepare_service(container_id: str, client: list[int] | None) -> dict:
    if client is None or not hasattr(os, "sched_getaffinity"):
        raise ValueError("Disjoint Redis control requires explicit supported client CPU affinity")
    available = sorted(os.sched_getaffinity(0))
    candidates = sorted(set(available) - set(client))
    if not candidates or not set(client) <= set(available):
        raise ValueError("No disjoint available logical CPU for Redis")
    layout = topology(available)
    index = {item["cpu"]: (item["package"], item["core"]) for item in layout}
    client_known = all(index[cpu][0] is not None for cpu in client)
    distinct = [
        cpu
        for cpu in candidates
        if client_known
        and index[cpu][0] is not None
        and index[cpu] not in {index[item] for item in client}
    ]
    chosen = distinct[0] if distinct else candidates[0]
    # Check explicit ownership/identity before making a configuration change.
    before = observe_service(container_id)
    subprocess.run(
        ["docker", "update", "--cpuset-cpus", str(chosen), before["container_id"]],
        check=True,
        capture_output=True,
        text=True,
    )
    service = observe_service(before["container_id"])
    if (
        service["container_id"] != before["container_id"]
        or service["image_id"] != before["image_id"]
        or service["pid"] != before["pid"]
    ):
        raise ValueError("Redis service identity changed while configuring CPU control")
    known = all(index[cpu][0] is not None for cpu in [*client, chosen])
    value = {
        "schema_version": 1,
        "mode": "docker-disjoint-logical",
        "client_cpu_affinity": client,
        "service": service,
        "available_topology": layout,
        "physical_core_disjoint": index[chosen] not in {index[cpu] for cpu in client}
        if known
        else None,
        "physical_isolation_claimed": False,
    }
    if service["cpu_affinity"] != [chosen] or not valid_control(value):
        raise ValueError("Docker Redis CPU affinity differs from the declared disjoint control")
    return value


def verify_service(value: dict) -> dict:
    if not valid_control(value):
        raise ValueError("Invalid Redis service CPU control")
    observed = observe_service(value["service"]["container_id"])
    if observed != value["service"]:
        raise ValueError(
            "Redis service identity or CPU affinity changed: "
            + json.dumps(observed, sort_keys=True)
        )
    return observed
