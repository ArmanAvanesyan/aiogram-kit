"""Run all four predeclared native gates serially against installed wheels.

This command never publishes. A passed performance result still needs artifact,
platform and release review. Failed runs are retained rather than resampled away.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]


def driver_arguments(package: str) -> list[str]:
    if package not in ("aiogram-nav", "aiogram-idle"):
        return []
    arguments = ["--ages", "50", "--samples", "100", "--cpu-samples", "10"]
    return arguments + (
        ["--skip-registry"] if package == "aiogram-nav" else ["--combined", "--skip-admission"]
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--python", type=Path, required=True)
    parser.add_argument("--redis-url", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--protocol", type=Path, required=True)
    parser.add_argument(
        "--package",
        action="append",
        choices=("aiogram-sentinel", "aiogram-cmds", "aiogram-nav", "aiogram-idle"),
    )
    args = parser.parse_args()
    protocol_bytes = args.protocol.read_bytes()
    protocol = json.loads(protocol_bytes)
    requested = set(args.package or protocol["cpu_workloads"])
    if not requested or not requested <= set(protocol["cpu_workloads"]):
        raise ValueError("Selected packages must have predeclared workloads")
    output = args.output.resolve()
    if output.exists() and any(output.iterdir()):
        raise ValueError("Qualification output must be empty; retain earlier attempts")
    output.mkdir(parents=True, exist_ok=True)
    (output / "protocol.json").write_bytes(protocol_bytes)
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
            if package == "aiogram-idle":
                command += ["--peer-package", "aiogram-nav"]
            command += [f"--driver-arg={argument}" for argument in driver_arguments(package)]
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
        subprocess.run(command, cwd=ROOT, check=False)
        results[package] = json.loads(report.read_text())
    summary = {
        "protocol_sha256": hashlib.sha256(protocol_bytes).hexdigest(),
        "publication_performed": False,
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
