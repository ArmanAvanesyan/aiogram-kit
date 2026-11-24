"""Retain every raw observation and recompute exact-artifact release qualification."""

import argparse
import gzip
import hashlib
import io
import json
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REPORT = Path(__file__).parent
sys.path.insert(0, str(ROOT / "tools/optimization"))
from verify_release_readiness import verify


def gh(endpoint):
    return subprocess.check_output(["gh", "api", "--allow-escape-sequences", endpoint])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--package", choices=["aiogram-cmds", "aiogram-nav", "aiogram-idle"], required=True
    )
    parser.add_argument("--run", type=int, required=True)
    parser.add_argument("--artifacts", type=Path, required=True)
    args = parser.parse_args()
    endpoint = f"repos/ArmanAvanesyan/aiogram-kit/actions/runs/{args.run}"
    run = json.loads(gh(endpoint))
    if run["status"] != "completed":
        raise ValueError("Qualification must finish; failures are retained too")
    available = json.loads(gh(endpoint + "/artifacts?per_page=100"))["artifacts"]
    rows = [a for a in available if a["name"] == f"native-qualification-{args.package}-{args.run}"]
    if len(rows) != 1 or rows[0]["expired"]:
        raise ValueError("Missing or expired qualification artifact")
    item = rows[0]
    if item["workflow_run"]["head_sha"] != run["head_sha"]:
        raise ValueError("Qualification source mismatch")
    raw = gh(f"repos/ArmanAvanesyan/aiogram-kit/actions/artifacts/{item['id']}/zip")
    sha = hashlib.sha256(raw).hexdigest()
    if item["digest"] != "sha256:" + sha:
        raise ValueError("Qualification archive checksum mismatch")
    store = args.artifacts.resolve() / (args.package + "-qualification-" + str(args.run))
    store.mkdir(parents=True, exist_ok=False)
    (store / "artifact.zip").write_bytes(raw)
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        for member in archive.infolist():
            path = Path(member.filename)
            if path.is_absolute() or ".." in path.parts or "\\" in member.filename:
                raise ValueError("Unsafe qualification artifact path")
        archive.extractall(store / "extracted")
    matches = list((store / "extracted").rglob(args.package + "/native-gate.json"))
    if len(matches) != 1:
        raise ValueError("Missing or duplicate native gate")
    package_source = matches[0].parent
    native_source = package_source.parent
    target = REPORT / "shipping-qualification/native-qualification"
    package_target = target / args.package
    if package_target.exists():
        raise ValueError("Retain each candidate once; never overwrite raw evidence")
    shutil.copytree(package_source, package_target)
    for name in [
        "protocol.json",
        "host-controls.json",
        "redis-service-control.json",
        "qualification-summary.json",
        "SHA256SUMS",
    ]:
        source = native_source / name
        if not source.exists():
            continue
        # Host controls/summaries are run-specific, never overwrite another package's data.
        destination = target / "run-metadata" / args.package / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, destination)
        if name == "protocol.json":
            common = target / name
            if common.exists() and common.read_bytes() != source.read_bytes():
                raise ValueError("Performance protocols differ")
            common.write_bytes(source.read_bytes())
    for path in list(package_target.rglob("*.json")):
        if path.name in {args.package + ".json", "run-manifest.json"}:
            path.with_suffix(path.suffix + ".gz").write_bytes(
                gzip.compress(path.read_bytes(), mtime=0)
            )
            path.unlink()
    gate = json.loads((package_target / "native-gate.json").read_text())
    manifest_bytes = (REPORT / "ci-artifact-manifest.json").read_bytes()
    manifest = json.loads(manifest_bytes)
    readiness_path = REPORT / "readiness.json"
    readiness = json.loads(readiness_path.read_text())
    readiness["performance_manifest_sha256"] = hashlib.sha256(manifest_bytes).hexdigest()
    result = next(r for r in readiness["packages"] if r["sdk"] == args.package)
    result.update(
        {
            "sdk_packaging_and_standalone": "pass",
            "native_platform_and_artifacts": "pass",
            "native_performance": "pass" if gate["qualified"] else "hold",
            "performance_failures": gate["failures"],
            "native_manifest_sha256": manifest["packages"][args.package]["native_manifest_sha256"],
        }
    )
    readiness_path.write_text(json.dumps(readiness, indent=2) + "\n")
    proof = {
        "run_id": args.run,
        "workflow_conclusion": run["conclusion"],
        "source_commit": run["head_sha"],
        "artifact_id": item["id"],
        "archive_sha256": sha,
        "qualified": gate["qualified"],
        "failures": gate["failures"],
    }
    (REPORT / (args.package + "-qualification-run.json")).write_text(
        json.dumps(proof, indent=2) + "\n"
    )
    if gate["qualified"]:
        # Recompute from raw inputs with the exact verifier used by both publish jobs.
        print(
            json.dumps(
                verify(
                    ROOT,
                    args.package,
                    args.package + "-native-v0.3.3",
                    args.artifacts / (args.package + "-native"),
                    result["native_manifest_sha256"],
                    REPORT.relative_to(ROOT),
                ),
                indent=2,
            )
        )
    else:
        raise SystemExit("Performance hold retained: " + repr(gate["failures"]))


if __name__ == "__main__":
    main()
