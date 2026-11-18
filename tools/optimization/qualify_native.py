"""Run all four predeclared native gates serially against installed wheels.

This command never publishes. A passed performance result still needs artifact,
platform and release review. Failed runs are retained rather than resampled away.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import runpy
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
COMPARISON = runpy.run_path(
    str(HERE / "compare_results.py"), run_name="qualification_control_validation"
)
VALID_CONTROLS = COMPARISON["valid_controls"]
REDIS_CONTROL = runpy.run_path(
    str(HERE / "redis_cpu_control.py"), run_name="qualification_redis_control"
)


PACKAGES = frozenset({"aiogram-sentinel", "aiogram-cmds", "aiogram-nav", "aiogram-idle"})
ORDER = ["python-a", "rust-a", "rust-b", "python-b"]
GATE = {
    "maximum_rust_python_cpu_ratio": 0.8,
    "maximum_rust_python_p95_ratio": 1.05,
    "maximum_repeat_spread": 0.1,
}
SAMPLES = {"cpu_repeats_minimum": 10, "individual_latency_minimum": 100}


def validate_protocol(protocol: object) -> dict:
    """Reject misleading metadata and unsafe/repeated output labels before writes."""
    if (
        not isinstance(protocol, dict)
        or type(protocol.get("schema_version")) is not int
        or protocol["schema_version"] != 1
    ):
        raise ValueError("Unsupported qualification protocol schema")
    if protocol.get("order") != ORDER:
        raise ValueError("Protocol requires unique, balanced Python-Rust-Rust-Python labels")
    if protocol.get("gate") != GATE or protocol.get("samples") != SAMPLES:
        raise ValueError("Protocol thresholds and samples must match the enforced gate")
    workloads = protocol.get("cpu_workloads")
    latency = protocol.get("required_latency")
    if not isinstance(workloads, dict) or not workloads or not set(workloads) <= PACKAGES:
        raise ValueError("Protocol must declare known packages and CPU workloads")
    if not isinstance(latency, dict) or set(latency) != set(workloads):
        raise ValueError("Every declared package requires latency workloads")
    for names in [*workloads.values(), *latency.values()]:
        if (
            not isinstance(names, list)
            or not names
            or any(not isinstance(name, str) or not name.strip() for name in names)
            or len(names) != len(set(names))
        ):
            raise ValueError("Protocol workloads must be nonempty unique strings")
    return protocol


def own_output(output: Path) -> None:
    """Atomically reserve even an existing empty directory against concurrent runs."""
    output.mkdir(parents=True, exist_ok=True)
    if any(output.iterdir()):
        raise ValueError("Qualification output must be empty; retain earlier attempts")
    try:
        descriptor = os.open(
            output / ".qualification-owner", os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600
        )
    except FileExistsError as error:
        raise ValueError("Qualification output already belongs to another attempt") from error
    with os.fdopen(descriptor, "w") as owner:
        owner.write(str(os.getpid()) + "\n")


def checked_comparison(
    report: Path,
    returncode: int,
    affinity: list[int] | None = None,
    plan: dict | None = None,
    service_control: dict | None = None,
) -> dict:
    """An erroneous comparator cannot promote a partial or contradictory report."""
    if returncode not in (0, 1):
        raise RuntimeError("Comparator process failed; qualification withheld")
    result = json.loads(report.read_text())
    if not isinstance(result, dict):
        raise RuntimeError("Malformed comparator result; qualification withheld")
    qualified, failures = result.get("qualified"), result.get("failures")
    if (
        type(qualified) is not bool
        or not isinstance(failures, list)
        or any(not isinstance(failure, str) for failure in failures)
    ):
        raise RuntimeError("Malformed comparator result; qualification withheld")
    if qualified != (not failures) or returncode != (0 if qualified else 1):
        raise RuntimeError("Comparator status contradicts its result; qualification withheld")
    controls = result.get("measurement_controls")
    if qualified and (
        not VALID_CONTROLS(controls)
        or (plan is not None and controls.get("sampling_plan") != plan)
        or controls.get("service_cpu_control") != service_control
        or (
            affinity is not None
            and (
                controls.get("affinity_policy") != "pinned"
                or controls.get("cpu_affinity") != affinity
            )
        )
    ):
        raise RuntimeError("Comparator host controls contradict the run; qualification withheld")
    return result


def driver_arguments(
    package: str,
    cpu_samples: int = 10,
    latency_windows: int = 1,
    individual_latency_samples: int = 1000,
) -> list[str]:
    if package == "aiogram-cmds":
        return ["--individual-latency-samples", str(individual_latency_samples)]
    if package not in ("aiogram-nav", "aiogram-idle"):
        return []
    arguments = [
        "--ages",
        "50",
        "--samples",
        "100",
        "--cpu-samples",
        str(cpu_samples),
        "--latency-windows",
        str(latency_windows),
    ]
    return arguments + (
        ["--skip-registry"] if package == "aiogram-nav" else ["--combined", "--skip-admission"]
    )


def sampling_plan(package: str, cpu: int, windows: int, individual: int) -> dict:
    return {
        "cpu_repeats": cpu
        if package in ("aiogram-nav", "aiogram-idle")
        else (31 if package == "aiogram-cmds" else 15),
        "additional_latency_windows": windows
        if package in ("aiogram-nav", "aiogram-idle")
        else None,
        "operations_per_window": 100 if package in ("aiogram-nav", "aiogram-idle") else None,
        "individual_latency_samples": individual if package == "aiogram-cmds" else None,
        "state_age": 50 if package in ("aiogram-nav", "aiogram-idle") else None,
    }


def resolve_affinity(value: str | None) -> list[int] | None:
    """Select once, before all paired runs; never adapt selection to timings."""
    if value is None:
        return None
    if not hasattr(os, "sched_getaffinity") or not hasattr(os, "sched_setaffinity"):
        raise ValueError("CPU affinity control is unsupported on this platform")
    available = sorted(os.sched_getaffinity(0))
    if not available:
        raise ValueError("No available CPU for qualification")
    if value == "auto":
        topology = []
        for cpu in available:
            root = Path(f"/sys/devices/system/cpu/cpu{cpu}/topology")
            try:
                package = int((root / "physical_package_id").read_text())
                core = int((root / "core_id").read_text())
            except (OSError, ValueError):
                topology = []
                break
            topology.append((package, core, cpu))
        return [min(topology)[2] if topology else available[0]]
    parts = value.split(",")
    if any(not part.isascii() or not part.isdecimal() for part in parts):
        raise ValueError("CPU affinity must be auto or comma-separated CPU IDs")
    cpus = [int(part) for part in parts]
    if len(set(cpus)) != len(cpus) or not set(cpus) <= set(available):
        raise ValueError("CPU affinity must contain unique available CPU IDs")
    return sorted(cpus)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--python", type=Path, required=True)
    parser.add_argument("--redis-url", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--protocol", type=Path, required=True)
    parser.add_argument("--cpu-samples", type=int, default=10)
    parser.add_argument("--latency-windows", type=int, default=1)
    parser.add_argument("--individual-latency-samples", type=int, default=1000)
    parser.add_argument(
        "--redis-container-id", help="Explicit owned disposable service to pin disjointly"
    )
    parser.add_argument(
        "--cpu-affinity",
        help="Fixed CPU IDs or auto (select one available logical CPU once using topology)",
    )
    parser.add_argument(
        "--package",
        action="append",
        choices=("aiogram-sentinel", "aiogram-cmds", "aiogram-nav", "aiogram-idle"),
    )
    args = parser.parse_args()
    if not (
        10 <= args.cpu_samples <= 100
        and 1 <= args.latency_windows <= 100
        and 1000 <= args.individual_latency_samples <= 100000
    ):
        raise ValueError("Sampling dimensions must preserve historical minima and bounded limits")
    affinity = resolve_affinity(args.cpu_affinity)
    protocol_bytes = args.protocol.read_bytes()
    protocol = validate_protocol(json.loads(protocol_bytes))
    requested = set(args.package or protocol["cpu_workloads"])
    if not requested or not requested <= set(protocol["cpu_workloads"]):
        raise ValueError("Selected packages must have predeclared workloads")
    output = args.output.resolve()
    own_output(output)
    (output / "protocol.json").write_bytes(protocol_bytes)
    service_control = None
    if args.redis_container_id:
        service_control = REDIS_CONTROL["prepare_service"](args.redis_container_id, affinity)
        (output / "redis-service-control.json").write_text(
            json.dumps(service_control, indent=2) + "\n"
        )
    plans = {
        package: sampling_plan(
            package, args.cpu_samples, args.latency_windows, args.individual_latency_samples
        )
        for package in requested
    }
    host_controls = {
        "schema_version": 2,
        "sampling_plans": plans,
        "redis_service_control": service_control,
        "affinity_request": args.cpu_affinity,
        "resolved_cpu_affinity": affinity,
        "selection_policy": (
            "lowest available physical-package/core/CPU tuple; first allowed CPU if topology unavailable"
            if args.cpu_affinity == "auto"
            else "explicit IDs"
            if affinity
            else "inherited"
        ),
        "available_cpu_affinity": (
            sorted(os.sched_getaffinity(0)) if hasattr(os, "sched_getaffinity") else None
        ),
        "host_cpu_count": os.cpu_count(),
        "physical_isolation_claimed": False,
        "gc_policy": "unchanged",
    }
    (output / "host-controls.json").write_text(json.dumps(host_controls, indent=2) + "\n")
    results = {}
    for package, workloads in protocol["cpu_workloads"].items():
        if args.package and package not in args.package:
            continue
        directory = output / package
        directory.mkdir(exist_ok=True)
        for label in protocol["order"]:
            command = [
                sys.executable,
                str(HERE / "run_benchmarks.py"),
                "--python",
                str(args.python.absolute()),
                "--package",
                package,
                "--profile",
                "native" if label.startswith("rust-") else "optimized",
                "--output-dir",
                str(directory / label),
                "--redis-url",
                args.redis_url,
            ]
            if affinity is not None:
                command += ["--cpu-affinity", ",".join(map(str, affinity))]
            command += ["--sampling-plan", json.dumps(plans[package], sort_keys=True)]
            if service_control is not None:
                command += ["--redis-service-control", str(output / "redis-service-control.json")]
            if package == "aiogram-idle":
                command += ["--peer-package", "aiogram-nav"]
            command += [
                f"--driver-arg={argument}"
                for argument in driver_arguments(
                    package, args.cpu_samples, args.latency_windows, args.individual_latency_samples
                )
            ]
            print(f"Starting {package} {label}", flush=True)
            with (directory / f"{label}.log").open("w") as log:
                process = subprocess.run(command, cwd=ROOT, stdout=log, stderr=subprocess.STDOUT)
            if process.returncode:
                raise RuntimeError(f"Benchmark failed: {package} {label}; see retained log")
        command = [sys.executable, str(HERE / "compare_results.py")]
        for label in protocol["order"]:
            engine = label.split("-")[0]
            command += [f"--{engine}", str(directory / label / f"{package}.json")]
        for workload in workloads:
            command += ["--cpu-workload", workload]
        for workload in protocol["required_latency"].get(package, []):
            command += ["--latency-workload", workload]
        report = directory / "native-gate.json"
        command += ["--output", str(report)]
        comparison = subprocess.run(command, cwd=ROOT, check=False)
        results[package] = checked_comparison(
            report, comparison.returncode, affinity, plans[package], service_control
        )
    summary = {
        "protocol_sha256": hashlib.sha256(protocol_bytes).hexdigest(),
        "publication_performed": False,
        "requested_cpu_affinity": affinity,
        "host_control_declaration": "host-controls.json",
        "packages_selected": list(results),
        "performance_gates": {
            package: {"qualified": result["qualified"], "failures": result["failures"]}
            for package, result in results.items()
        },
    }
    (output / "qualification-summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps(summary, indent=2))
    return int(any(not result["qualified"] for result in results.values()))


if __name__ == "__main__":
    raise SystemExit(main())
