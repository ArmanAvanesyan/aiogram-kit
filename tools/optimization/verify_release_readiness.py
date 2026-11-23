"""Enforce exact-artifact native qualification before publisher credentials are usable."""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import tempfile
from pathlib import Path

from compare_results import compare, load
from verify_native_artifacts import verify as verify_artifacts

try:
    import tomllib
except ModuleNotFoundError:
    import tomli as tomllib

PACKAGES = frozenset(f"aiogram-{name}" for name in ("sentinel", "cmds", "nav", "idle"))
PROTOCOL_SHA256 = "2ffc522b54182bbcb90397aed7342eb67ef94def9d5adb21c15f5f76b2ce2bd0"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def source_matches(source: Path, expected: str, entry: dict, reconciliation: dict) -> bool:
    """Reconcile only reviewed non-distributed TOML changes, never runtime source."""
    current = source.read_bytes()
    if hashlib.sha256(current).hexdigest() == expected:
        return True
    if source.name != "pyproject.toml" or source.parent.name not in PACKAGES:
        return False
    original = reconciliation.get("original_pyproject")
    if not isinstance(original, str):
        return False
    if (
        hashlib.sha256(original.encode()).hexdigest() != expected
        or reconciliation.get("current_sha256") != hashlib.sha256(current).hexdigest()
        or reconciliation.get("sdk_wheel_sha256") != entry["sdk"]["sha256"]
    ):
        return False
    try:
        before, after = tomllib.loads(original), tomllib.loads(current.decode())
    except (UnicodeError, tomllib.TOMLDecodeError):
        return False
    before.pop("dependency-groups", None)
    after.pop("dependency-groups", None)
    return before == after


def verify(
    root: Path,
    package: str,
    tag: str,
    directory: Path,
    manifest_sha256: str,
    report_path: Path = Path("reports/2026-11-18-paired-release"),
) -> dict:
    require(package in PACKAGES, "Unknown SDK/native pair")
    require(
        bool(report_path.parts)
        and not report_path.is_absolute()
        and ".." not in report_path.parts
        and report_path.parts[0] == "reports",
        "Unsafe readiness report path",
    )
    report = root / report_path
    require(
        report.resolve().is_relative_to((root / "reports").resolve()),
        "Readiness report escapes repository",
    )
    readiness = json.loads((report / "readiness.json").read_text())
    rows = [row for row in readiness["packages"] if row["sdk"] == package]
    require(len(rows) == 1, "Missing or duplicate release readiness")
    row = rows[0]
    require(tag == f"{package}-native-v{row['version']}", "Readiness tag/version mismatch")
    require(
        row["native_performance"] == "pass", "Native release is held by performance qualification"
    )
    require(row["native_platform_and_artifacts"] == "pass", "Platform qualification has not passed")
    require(row["sdk_packaging_and_standalone"] == "pass", "SDK qualification has not passed")
    require(row["performance_failures"] == [], "Contradictory qualification failures")
    require(
        row["native_manifest_sha256"] == manifest_sha256, "Manifest is not performance-qualified"
    )
    verify_artifacts(
        directory,
        root_project=root / "packages" / package / "pyproject.toml",
        native_project=root / "packages" / package / "native/pyproject.toml",
        tag=tag,
        manifest_sha256=manifest_sha256,
    )
    manifest_path = report / "ci-artifact-manifest.json"
    manifest_bytes = manifest_path.read_bytes()
    require(
        hashlib.sha256(manifest_bytes).hexdigest() == readiness["performance_manifest_sha256"],
        "Qualification input manifest changed",
    )
    entry = json.loads(manifest_bytes)["packages"][package]
    reconciliation_file = report / "source-reconciliation.json"
    reconciliations = {}
    if reconciliation_file.exists():
        require(not reconciliation_file.is_symlink(), "Unsafe source reconciliation")
        reconciliation_data = json.loads(reconciliation_file.read_text())
        require(
            reconciliation_data["baseline_manifest_sha256"]
            == readiness["performance_manifest_sha256"],
            "Source reconciliation refers to different evidence",
        )
        reconciliations = reconciliation_data["packages"]
    require(
        entry["version"] == row["version"] and entry["native_manifest_sha256"] == manifest_sha256,
        "Artifact/version readiness mismatch",
    )
    require(bool(entry["source_files"]), "Empty qualified source inventory")
    for filename, digest in entry["source_files"].items():
        path = Path(filename)
        require(
            not path.is_absolute()
            and ".." not in path.parts
            and filename.startswith(f"packages/{package}/"),
            "Unsafe qualification source path",
        )
        source = root / path
        require(
            not source.is_symlink()
            and source_matches(source, digest, entry, reconciliations.get(package, {})),
            "Performance-qualified source changed",
        )
    folder = report / "shipping-qualification/native-qualification" / package
    gate = json.loads((folder / "native-gate.json").read_text())
    require(
        gate["qualified"] is True and gate["failures"] == [],
        "Recorded native gate is not qualified",
    )
    protocol_bytes = (folder.parent / "protocol.json").read_bytes()
    require(
        hashlib.sha256(protocol_bytes).hexdigest() == PROTOCOL_SHA256,
        "Performance protocol changed",
    )
    protocol = json.loads(protocol_bytes)
    require(
        set(gate["cpu_workloads_selected"]) == set(protocol["cpu_workloads"][package]),
        "CPU workload selection changed",
    )
    require(
        set(gate["required_latency_workloads"]) == set(protocol["required_latency"][package]),
        "Latency workload selection changed",
    )
    linux = [
        r
        for r in entry["artifacts"]
        if "manylinux" in r["filename"] and r["filename"].endswith("_x86_64.whl")
    ]
    require(len(linux) == 1, "Missing or duplicate qualified platform artifact")
    require(len(gate["inputs"]) == 4, "Expected four independent ABBA inputs")
    profiles = {}
    with tempfile.TemporaryDirectory(prefix="native-release-proof-") as temporary:
        for label in ("python-a", "rust-a", "rust-b", "python-b"):
            original = folder / label / (package + ".json")
            raw = (
                original.read_bytes()
                if original.exists()
                else gzip.decompress(original.with_suffix(".json.gz").read_bytes())
            )
            inputs = [i for i in gate["inputs"] if label in Path(i["path"]).parts]
            require(
                len(inputs) == 1 and hashlib.sha256(raw).hexdigest() == inputs[0]["sha256"],
                "Raw qualification evidence changed",
            )
            proof = inputs[0]["qualification_provenance"]
            require(
                proof["base_artifact_sha256"] == entry["sdk"]["sha256"],
                "SDK artifact is not qualified",
            )
            if label.startswith("rust"):
                require(
                    proof["native_artifact_sha256"] == linux[0]["sha256"],
                    "Native binary is not qualified",
                )
            path = Path(temporary) / (label + ".json")
            path.write_bytes(raw)
            profiles[label] = load(path)
        recalculated = compare(
            [profiles[k] for k in ("python-a", "python-b")],
            [profiles[k] for k in ("rust-a", "rust-b")],
            protocol["cpu_workloads"][package],
            protocol["required_latency"][package],
        )
    require(
        recalculated["qualified"] is True and recalculated["failures"] == [],
        "Recomputed performance gate has not passed",
    )
    require(
        recalculated["comparisons"] == gate["comparisons"],
        "Recorded ratios contradict raw evidence",
    )
    return {
        "package": package + "-native",
        "version": row["version"],
        "qualified": True,
        "manifest_sha256": manifest_sha256,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--package", required=True, choices=sorted(PACKAGES))
    parser.add_argument("--report", type=Path, default=Path("reports/2026-11-18-paired-release"))
    parser.add_argument("--tag", required=True)
    parser.add_argument("--directory", type=Path, required=True)
    parser.add_argument("--manifest-sha256", required=True)
    args = parser.parse_args()
    print(
        json.dumps(
            verify(
                Path(__file__).resolve().parents[2],
                args.package,
                args.tag,
                args.directory,
                args.manifest_sha256,
                args.report,
            ),
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
