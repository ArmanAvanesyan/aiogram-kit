"""Run repository benchmarks using explicitly installed distributions.

The benchmark drivers live in their owning repositories. Run each profile in a
separate fresh environment; this controller never installs or rebuilds packages.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import subprocess
import tempfile
import time
import uuid
from pathlib import Path

PACKAGES = ("aiogram-sentinel", "aiogram-cmds", "aiogram-nav", "aiogram-idle")
PROBE_COMMON = """
import hashlib, importlib, importlib.metadata, json, sys, zipfile
from pathlib import Path
from urllib.parse import urlsplit
from urllib.request import url2pathname
MODULES = {
    'aiogram-sentinel-native': '_aiogram_sentinel_native',
    'aiogram-cmds-native': '_aiogram_cmds_native',
    'aiogram-nav-native': 'aiogram_nav_native',
    'aiogram-idle-native': 'aiogram_idle_native',
}
def installed(name):
    package = importlib.import_module(MODULES.get(name, name.replace('-', '_')))
    distribution = importlib.metadata.distribution(name)
    direct = json.loads(distribution.read_text('direct_url.json') or '{}')
    if direct.get('dir_info', {}).get('editable'):
        raise RuntimeError('Benchmark environment must install artifacts, not editable sources')
    if 'site-packages' not in str(package.__file__):
        raise RuntimeError('Checkout shadows the benchmark distribution')
    archive = direct.get('archive_info', {})
    digest = archive.get('hashes', {}).get('sha256')
    if not digest and archive.get('hash', '').startswith('sha256='):
        digest = archive['hash'].split('=', 1)[1]
    source = urlsplit(direct.get('url', ''))
    if source.scheme == 'file' and source.netloc in ('', 'localhost'):
        artifact = Path(url2pathname(source.path))
        if artifact.suffix == '.whl' and artifact.is_file():
            actual = hashlib.sha256(artifact.read_bytes()).hexdigest()
            if digest and actual != digest:
                raise RuntimeError('Local wheel differs from recorded archive digest')
            with zipfile.ZipFile(artifact) as wheel:
                for member in wheel.infolist():
                    if member.is_dir() or member.filename.endswith('.dist-info/RECORD'):
                        continue
                    if '.data/' in member.filename or '..' in Path(member.filename).parts:
                        raise RuntimeError('Unsupported wheel layout for installed provenance')
                    target = distribution.locate_file(member.filename)
                    if not target.is_file() or target.read_bytes() != wheel.read(member):
                        raise RuntimeError('Installed files differ from the local wheel artifact')
            digest = actual
    return {'distribution': name, 'version': distribution.version,
            'module': str(package.__file__), 'python': sys.version,
            'module_sha256': hashlib.sha256(Path(package.__file__).read_bytes()).hexdigest(),
            'artifact_sha256': digest,
            'executable': sys.executable, 'direct_url': direct}
"""
PROBE = PROBE_COMMON + "\nprint(json.dumps(installed(sys.argv[1])))\n"
HOST_OBSERVATION = r"""
import gc, os
def host_observation():
    result = {
        "cpu_affinity": sorted(os.sched_getaffinity(0)) if hasattr(os, "sched_getaffinity") else None,
        "host_cpu_count": os.cpu_count(),
        "gc_enabled": gc.isenabled(),
        "gc_thresholds": list(gc.get_threshold()),
        "gc_counts": list(gc.get_count()),
        "gc_collections": gc.get_stats(),
    }
    try:
        result["load_average"] = list(os.getloadavg())
    except (AttributeError, OSError):
        result["load_average"] = None
    try:
        import resource
        usage = resource.getrusage(resource.RUSAGE_SELF)
        result["process_usage"] = {name: getattr(usage, name) for name in (
            "ru_utime", "ru_stime", "ru_nvcsw", "ru_nivcsw", "ru_minflt", "ru_majflt"
        )}
    except (ImportError, OSError):
        result["process_usage"] = None
    paths = {
        "cgroup_cpu_stat": "/sys/fs/cgroup/cpu.stat",
        "cgroup_cpu_max": "/sys/fs/cgroup/cpu.max",
        "cgroup_cpuset": "/sys/fs/cgroup/cpuset.cpus.effective",
        "cpu_pressure": "/proc/pressure/cpu",
    }
    result["linux_cpu"] = {}
    for name, location in paths.items():
        try:
            result["linux_cpu"][name] = Path(location).read_text()[:16384]
        except (OSError, UnicodeError):
            result["linux_cpu"][name] = None
    affinity = result["cpu_affinity"] or []
    frequencies = {}
    for cpu in affinity[:256]:
        location = Path(f"/sys/devices/system/cpu/cpu{cpu}/cpufreq/scaling_cur_freq")
        try:
            frequencies[str(cpu)] = int(location.read_text())
        except (OSError, ValueError):
            frequencies[str(cpu)] = None
    result["cpu_frequency_khz"] = frequencies
    return result
"""


BOOTSTRAP = (
    PROBE_COMMON
    + HOST_OBSERVATION
    + r"""
import runpy
expected = json.loads(sys.argv[1])
controls = json.loads(sys.argv[2])
requested = controls["cpu_affinity"]
if requested is not None:
    os.sched_setaffinity(0, requested)
    if sorted(os.sched_getaffinity(0)) != requested:
        raise RuntimeError('Benchmark CPU affinity differs from its declared control')
for probe in expected:
    if installed(probe['distribution']) != probe:
        raise RuntimeError('Actual benchmark imports differ from the isolated installed probe')
driver = Path(sys.argv[3])
sys.argv = [str(driver), *sys.argv[4:]]
# The verified installed packages are already imported before local helper paths.
# Their __path__ remains the installed package path, including lazy submodules.
sys.path.insert(0, str(driver.parent))
before = host_observation()
try:
    runpy.run_path(str(driver), run_name='__main__')
finally:
    after = host_observation()
    Path(controls["observations"]).write_text(json.dumps({
        "schema_version": 1,
        "scope": "Before/after driver only; no instrumentation inside measured operations",
        "before": before, "after": after,
    }, indent=2) + "\n")
"""
)


def cpu_affinity(value: str | None) -> list[int] | None:
    """Explicit available CPU IDs only; never silently choose another CPU."""
    if value is None:
        return None
    if not hasattr(os, "sched_getaffinity") or not hasattr(os, "sched_setaffinity"):
        raise ValueError("CPU affinity control is unsupported on this platform")
    parts = value.split(",")
    if not parts or any(not item.isascii() or not item.isdecimal() for item in parts):
        raise ValueError("CPU affinity must be comma-separated nonnegative CPU IDs")
    cpus = [int(item) for item in parts]
    if len(set(cpus)) != len(cpus) or not set(cpus) <= os.sched_getaffinity(0):
        raise ValueError("CPU affinity must contain unique available CPU IDs")
    return sorted(cpus)


def measurement_controls(observations: dict, affinity: list[int] | None) -> dict:
    before, after = observations["before"], observations["after"]
    actual = before["cpu_affinity"]
    if actual != after["cpu_affinity"] or (affinity is not None and actual != affinity):
        raise ValueError("Benchmark CPU affinity changed during the driver")
    if (
        before["gc_enabled"] is not True
        or after["gc_enabled"] is not True
        or before["gc_thresholds"] != after["gc_thresholds"]
    ):
        raise ValueError("Benchmark GC controls changed or automatic GC was disabled")
    count = before["host_cpu_count"]
    if count != after["host_cpu_count"]:
        raise ValueError("Host CPU count changed during the driver")
    return {
        "schema_version": 1,
        "affinity_policy": "pinned" if affinity is not None else "inherited",
        "cpu_affinity": actual,
        "host_cpu_count": count,
        "effective_cpu_count": len(actual) if actual is not None else None,
        "gc_policy": "unchanged",
        "gc_enabled": before["gc_enabled"],
        "gc_thresholds": before["gc_thresholds"],
    }


def benchmark_command(
    executable,
    probes,
    driver,
    engine,
    result,
    extra,
    quick=False,
    affinity=None,
    observations=None,
):
    for argument in extra:
        flag = argument.split("=", 1)[0]
        if flag.startswith("--") and any(
            reserved.startswith(flag) for reserved in ("--engine", "--output")
        ):
            raise ValueError("Driver arguments cannot override the verified engine or output")
    command = [
        str(executable),
        "-I",
        "-c",
        BOOTSTRAP,
        json.dumps(probes),
        json.dumps(
            {
                "cpu_affinity": affinity,
                "observations": str(observations or Path(result).with_suffix(".host.json")),
            }
        ),
        str(driver),
        "--engine",
        engine,
        "--output",
        str(result),
    ]
    if quick:
        command.append("--quick")
    return command + list(extra)


def driver_fingerprints(directory: Path) -> dict[str, str]:
    """Freeze the driver and local helper modules, excluding generated caches."""
    return {
        str(path.relative_to(directory)): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(directory.rglob("*.py"))
        if "__pycache__" not in path.parts
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--python", required=True, type=Path)
    parser.add_argument("--profile", required=True, choices=("baseline", "optimized", "native"))
    parser.add_argument("--package", action="append", choices=PACKAGES)
    parser.add_argument(
        "--repositories", type=Path, default=Path(__file__).resolve().parents[2] / "packages"
    )
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--redis-url")
    parser.add_argument("--cpu-affinity", help="Fixed comma-separated available CPU IDs")
    parser.add_argument(
        "--peer-package",
        action="append",
        choices=PACKAGES,
        default=[],
        help="Verify a combined peer and its matching native core in both engine profiles",
    )
    parser.add_argument(
        "--driver-arg",
        action="append",
        default=[],
        help="Explicit benchmark driver argument; use --driver-arg=--flag for flags",
    )
    parser.add_argument("--quick", action="store_true")
    parser.add_argument("--timeout", type=int, default=900)
    args = parser.parse_args()
    affinity = cpu_affinity(args.cpu_affinity)
    controller_sha256 = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    # Resolving a venv's python symlink would select the global interpreter and
    # silently discard the installed profile this controller is meant to audit.
    executable = args.python.absolute()
    if not executable.is_file():
        parser.error(f"Python executable does not exist: {executable}")
    output = args.output_dir.resolve()
    output.mkdir(parents=True, exist_ok=True)
    manifest = {
        "schema_version": 1,
        "profile": args.profile,
        "started_at": time.time(),
        "machine": {
            "platform": platform.platform(),
            "architecture": platform.machine(),
            "cpus": os.cpu_count(),
        },
        "quick": args.quick,
        "qualification": False,
        "note": "Exploratory unless paired repeated runs and independent qualification are recorded separately.",
        "packages": [],
    }
    failed = False
    for package in args.package or PACKAGES:
        repository = args.repositories / package
        driver = repository / "benchmarks" / "run.py"
        result = output / (package + ".json")
        row: dict[str, object] = {
            "package": package,
            "result": str(result),
            "started_at": time.time(),
        }
        try:
            if not driver.is_file():
                raise FileNotFoundError(f"Benchmark entry point is not available: {driver}")
            revision = subprocess.check_output(
                ["git", "rev-parse", "HEAD"], cwd=repository, text=True
            ).strip()
            row["driver_revision"] = revision
            row["driver_sha256"] = hashlib.sha256(driver.read_bytes()).hexdigest()
            row["driver_files_sha256"] = driver_fingerprints(driver.parent)
            with tempfile.TemporaryDirectory(prefix="aiogram-benchmark-driver-") as directory:
                row["installed"] = json.loads(
                    subprocess.check_output(
                        [str(executable), "-I", "-c", PROBE, package],
                        cwd=directory,
                        text=True,
                    )
                )
                probes = [row["installed"]]
                if args.profile == "native":
                    row["native_installed"] = json.loads(
                        subprocess.check_output(
                            [str(executable), "-I", "-c", PROBE, package + "-native"],
                            cwd=directory,
                            text=True,
                        )
                    )
                    if row["native_installed"]["version"] != row["installed"]["version"]:
                        raise ValueError("Native and base versions differ")
                    probes.append(row["native_installed"])
                peer_probes = []
                for peer in args.peer_package:
                    if peer == package:
                        raise ValueError("A peer must differ from the measured base package")
                    pair = []
                    for name in (peer, peer + "-native"):
                        pair.append(
                            json.loads(
                                subprocess.check_output(
                                    [str(executable), "-I", "-c", PROBE, name],
                                    cwd=directory,
                                    text=True,
                                )
                            )
                        )
                    if pair[0]["version"] != pair[1]["version"]:
                        raise ValueError("Combined peer base/native versions differ")
                    peer_probes.extend(pair)
                row["peer_installed"] = peer_probes
                probes.extend(peer_probes)
                environment = dict(os.environ)
                for variable in ("PYTHONPATH", "PYTHONHOME", "PYTHONUSERBASE"):
                    environment.pop(variable, None)
                if args.redis_url:
                    for variable in (
                        "AIOGRAM_IDLE_REDIS_URL",
                        "AIOGRAM_NAV_REDIS_URL",
                        "SENTINEL_REDIS_URL",
                        "REDIS_URL",
                    ):
                        environment[variable] = args.redis_url
                command = benchmark_command(
                    executable,
                    probes,
                    driver,
                    "rust" if args.profile == "native" else "python",
                    result,
                    args.driver_arg,
                    quick=args.quick,
                    affinity=affinity,
                    observations=output / (package + ".host.json"),
                )
                if args.redis_url and package in {"aiogram-nav", "aiogram-idle"}:
                    command.extend(["--redis-url", args.redis_url])
                row["command"] = command
                result.unlink(missing_ok=True)
                with (output / (package + ".log")).open("w") as log:
                    subprocess.run(
                        command,
                        cwd=directory,
                        env=environment,
                        stdout=log,
                        stderr=subprocess.STDOUT,
                        check=True,
                        timeout=args.timeout,
                    )
                observations = json.loads((output / (package + ".host.json")).read_text())
                row["host_observations"] = observations
                controls = measurement_controls(observations, affinity)
                controls["controller_sha256"] = controller_sha256
                if hashlib.sha256(Path(__file__).read_bytes()).hexdigest() != controller_sha256:
                    raise ValueError("Benchmark controller changed during measurement")
                row["measurement_controls"] = controls
                row["benchmark"] = json.loads(result.read_text())
                if driver_fingerprints(driver.parent) != row["driver_files_sha256"]:
                    raise ValueError(
                        "Benchmark driver changed during measurement; rerun the frozen driver"
                    )
                document = row["benchmark"]
                metadata = document.get("metadata", document)
                if metadata.get("engine") != ("rust" if args.profile == "native" else "python"):
                    raise ValueError("Driver reported a different engine")
                reported_version = metadata.get("package_version", metadata.get("version"))
                if (
                    metadata.get("package") != package
                    or reported_version != row["installed"]["version"]
                ):
                    raise ValueError("Driver reported a different installed package/version")
                document["measurement_controls"] = controls
                document["run_id"] = str(uuid.uuid4())
                document["qualification_provenance"] = {
                    "base_artifact_sha256": row["installed"].get("artifact_sha256"),
                    "native_artifact_sha256": row.get("native_installed", {}).get(
                        "artifact_sha256"
                    ),
                    "driver_sha256": hashlib.sha256(
                        json.dumps(row["driver_files_sha256"], sort_keys=True).encode()
                    ).hexdigest(),
                }
                if peer_probes:
                    document["qualification_provenance"]["peer_artifacts_sha256"] = {
                        peer["distribution"]: peer["artifact_sha256"] for peer in peer_probes
                    }
                result.write_text(json.dumps(document, indent=2) + "\n")
            row["status"] = "completed"
        except (OSError, ValueError, subprocess.SubprocessError) as error:
            row["status"] = "failed"
            row["error"] = str(error)
            failed = True
        row["finished_at"] = time.time()
        manifest["packages"].append(row)
        (output / "run-manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
        print(package, row["status"], flush=True)
    manifest["finished_at"] = time.time()
    (output / "run-manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
