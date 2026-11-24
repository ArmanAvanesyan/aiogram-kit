"""Bind revised native CI artifacts and SDK wheel hashes before release timing."""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import subprocess
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools/optimization"))
from verify_native_artifacts import verify

SOURCE = "87a28811c9c633abdea012228a2a1e190975605f"
RUNS = {"aiogram-cmds": 45289854108, "aiogram-idle": 45289853834}


def digest(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def gh(endpoint: str) -> bytes:
    return subprocess.check_output(["gh", "api", "--allow-escape-sequences", endpoint])


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifacts", required=True, type=Path)
    parser.add_argument("--sdk-source-commit", default=SOURCE)
    parser.add_argument("--packages", nargs="+", choices=sorted(RUNS), default=list(RUNS))
    parser.add_argument("--base-manifest", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    original = ROOT / "reports/2026-11-18-paired-release"
    report = Path(__file__).parent
    data = json.loads((args.base_manifest or original / "ci-artifact-manifest.json").read_text())
    data["source_reconciliation"] = json.loads(
        (original / "source-reconciliation.json").read_text()
    )["packages"]
    for package in args.packages:
        run_id = RUNS[package]
        endpoint = f"repos/ArmanAvanesyan/aiogram-kit/actions/runs/{run_id}"
        run = json.loads(gh(endpoint))
        if (
            run["head_sha"] != SOURCE
            or run["status"] != "completed"
            or run["conclusion"] != "success"
        ):
            raise ValueError(f"{package}: complete successful platform CI required")
        directory = args.artifacts.resolve() / (package + "-native")
        directory.mkdir(exist_ok=True)
        rows = []
        artifacts = json.loads(gh(endpoint + "/artifacts?per_page=100"))["artifacts"]
        for artifact in artifacts:
            if not artifact["name"].startswith("native-") or artifact["name"].startswith(
                "native-core-profile-"
            ):
                continue
            if artifact["expired"] or artifact["workflow_run"]["head_sha"] != SOURCE:
                raise ValueError("Expired or foreign artifact")
            raw = gh(f"repos/ArmanAvanesyan/aiogram-kit/actions/artifacts/{artifact['id']}/zip")
            if artifact.get("digest") != "sha256:" + digest(raw):
                raise ValueError("GitHub artifact archive checksum mismatch")
            with zipfile.ZipFile(io.BytesIO(raw)) as archive:
                members = archive.infolist()
                if len(members) != 1:
                    raise ValueError("Expected one distribution per artifact")
                member = members[0]
                if Path(member.filename).name != member.filename or not member.filename.startswith(
                    package.replace("-", "_") + "_native-"
                ):
                    raise ValueError("Unexpected artifact filename")
                content = archive.read(member)
            target = directory / member.filename
            if target.exists() and target.read_bytes() != content:
                raise ValueError("Refusing to overwrite retained artifacts")
            target.write_bytes(content)
            rows.append(
                {
                    "id": artifact["id"],
                    "name": artifact["name"],
                    "filename": target.name,
                    "sha256": digest(content),
                    "bytes": len(content),
                    "archive_sha256": digest(raw),
                }
            )
        if len(rows) != 8:
            raise ValueError("Seven platform wheels and one source archive required")
        manifest = directory / "SHA256SUMS"
        manifest.write_text(
            "".join(
                f"{r['sha256']}  {r['filename']}\n"
                for r in sorted(rows, key=lambda r: r["filename"])
            )
        )
        version = "0.3.2"
        verify(
            directory,
            root_project=ROOT / "packages" / package / "pyproject.toml",
            native_project=ROOT / "packages" / package / "native/pyproject.toml",
            tag=f"{package}-native-v{version}",
            manifest_sha256=digest(manifest.read_bytes()),
        )
        filenames = subprocess.check_output(
            [
                "git",
                "ls-files",
                f"packages/{package}/src",
                f"packages/{package}/native",
                f"packages/{package}/pyproject.toml",
            ],
            cwd=ROOT,
            text=True,
        ).splitlines()
        sources = {}
        for filename in filenames:
            commit = SOURCE if "/native/" in filename else args.sdk_source_commit
            raw = subprocess.check_output(["git", "show", commit + ":" + filename], cwd=ROOT)
            if (ROOT / filename).read_bytes() != raw:
                raise ValueError("Runtime source differs from the platform commit")
            sources[filename] = digest(raw)
        sdk = next((args.artifacts / package).glob("*.whl"))
        data["packages"][package] = {
            "version": version,
            "run_id": run_id,
            "source_commit": SOURCE,
            "source_files": sources,
            "sdk": {"filename": sdk.name, "sha256": digest(sdk.read_bytes())},
            "native_manifest_sha256": digest(manifest.read_bytes()),
            "artifacts": rows,
        }
        if args.sdk_source_commit != SOURCE:
            data["packages"][package]["sdk"]["source_commit"] = args.sdk_source_commit
        print(package, "exact platform set and SDK input verified", flush=True)
    output = args.output or report / "ci-artifact-manifest.json"
    content = json.dumps(data, indent=2) + "\n"
    if output.exists() and output.read_text() != content:
        raise ValueError("Refusing to overwrite reviewed evidence; select a new report")
    output.write_text(content)
    print("Manifest SHA256:", digest(output.read_bytes()))


if __name__ == "__main__":
    main()
