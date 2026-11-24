"""Opt-in scheduling controls for an owned, disposable GitHub-hosted runner.

This is tooling, never a library startup hook. No real-time scheduler, GC change,
measurement filtering or claim of exclusive hypervisor hardware is involved.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path


def housekeeping_cpus(available: list[int], client: list[int], layout: list[dict]) -> list[int]:
    index = {row["cpu"]: (row["package"], row["core"]) for row in layout}
    if not client or not set(client) <= set(available) or not set(available) <= set(index):
        raise ValueError("Complete available/client topology is required")
    if any(None in index[cpu] for cpu in available):
        raise ValueError("Known physical core topology is required")
    cores = {index[cpu] for cpu in client}
    result = [cpu for cpu in available if index[cpu] not in cores]
    if not result:
        raise ValueError("A disjoint housekeeping core is required")
    return result


def isolate_runner(client: list[int], layout: list[dict], proc: Path = Path("/proc")) -> dict:
    if (
        os.environ.get("GITHUB_ACTIONS") != "true"
        or os.environ.get("RUNNER_ENVIRONMENT") != "github-hosted"
    ):
        raise ValueError("Scheduling changes require explicit owned GitHub-hosted runner mode")
    available = sorted(os.sched_getaffinity(0))
    housekeeping = housekeeping_cpus(available, client, layout)
    changed, exited = [], []
    uid, own_pid = os.getuid(), os.getpid()
    for process in sorted(proc.iterdir()):
        if not process.name.isdecimal() or int(process.name) == own_pid:
            continue
        try:
            if process.stat().st_uid != uid:
                continue
            threads = list((process / "task").iterdir())
            for thread in threads:
                tid = int(thread.name)
                before = sorted(os.sched_getaffinity(tid))
                method = "owner-sched"
                try:
                    os.sched_setaffinity(tid, housekeeping)
                except PermissionError:
                    # Some runner service threads are owned by the runner UID
                    # but require CAP_SYS_NICE. Recheck ownership before using
                    # the runner's explicit passwordless scheduling privilege.
                    if thread.stat().st_uid != uid:
                        raise PermissionError(
                            "Thread ownership changed before scheduling"
                        ) from None
                    subprocess.run(
                        [
                            "sudo",
                            "-n",
                            "taskset",
                            "-pc",
                            ",".join(map(str, housekeeping)),
                            str(tid),
                        ],
                        check=True,
                        capture_output=True,
                        timeout=30,
                    )
                    method = "sudo-taskset"
                after = sorted(os.sched_getaffinity(tid))
                if after != housekeeping:
                    raise RuntimeError("Housekeeping thread affinity was not applied")
                changed.append(
                    {
                        "pid": int(process.name),
                        "tid": tid,
                        "before": before,
                        "after": after,
                        "method": method,
                    }
                )
                if len(changed) > 4096:
                    raise RuntimeError("Runner thread inventory exceeds its bound")
        except (FileNotFoundError, ProcessLookupError):
            exited.append(int(process.name))
    # Change only this controller; measured children inherit its priority. Keep
    # its original affinity so children can explicitly select the client CPU.
    subprocess.run(
        ["sudo", "-n", "renice", "-n", "-20", "-p", str(own_pid)],
        check=True,
        capture_output=True,
        timeout=30,
    )
    priority = os.getpriority(os.PRIO_PROCESS, 0)
    if priority != -20 or sorted(os.sched_getaffinity(0)) != available:
        raise RuntimeError("Benchmark priority/available affinity differs from its declaration")
    return {
        "schema_version": 1,
        "mode": "owned-runner-housekeeping-and-nice",
        "client_cpus": client,
        "available_cpus": available,
        "housekeeping_cpus": housekeeping,
        "nice": priority,
        "moved_threads": changed,
        "exited_processes": exited,
        "physical_hardware_exclusivity_claimed": False,
        "gc_policy": "unchanged",
    }
