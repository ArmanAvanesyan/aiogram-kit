"""Stage checksum-reviewed CI release wheels for qualification; never publish/build native code."""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import re
import shutil
import subprocess
import zipfile
from pathlib import Path

from verify_native_artifacts import verify
from verify_release_readiness import source_matches

REPOSITORY = "ArmanAvanesyan/aiogram-kit"
PACKAGES = {f"aiogram-{name}" for name in ("sentinel", "cmds", "nav", "idle")}


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_manifest(path: Path, expected: str, root: Path) -> dict:
    require(re.fullmatch(r"[a-f0-9]{64}", expected) is not None, "Invalid manifest digest")
    require(not path.is_symlink() and digest(path) == expected, "Release manifest changed")
    data = json.loads(path.read_text())
    reconciliations = data.get("source_reconciliation", {})
    require(data["repository"] == REPOSITORY, "Unexpected release repository")
    require(
        bool(data["packages"]) and set(data["packages"]) <= PACKAGES,
        "Unknown or empty release pair selection",
    )
    for package, entry in data["packages"].items():
        require(bool(entry["source_files"]), "Release source inventory is empty")
        require(re.fullmatch(r"\d+\.\d+\.\d+", entry["version"]) is not None, "Invalid version")
        expected_sdk = f"{package.replace('-', '_')}-{entry['version']}-py3-none-any.whl"
        require(entry["sdk"]["filename"] == expected_sdk, "Unexpected SDK filename")
        require(
            re.fullmatch(r"[a-f0-9]{64}", entry["sdk"]["sha256"]) is not None, "Invalid SDK digest"
        )
        if "source_commit" in entry["sdk"]:
            require(
                isinstance(entry["sdk"]["source_commit"], str)
                and re.fullmatch(r"[a-f0-9]{40}", entry["sdk"]["source_commit"]) is not None,
                "Invalid independent SDK source commit",
            )
        require(
            re.fullmatch(r"[a-f0-9]{40}", entry["source_commit"]) is not None,
            "Invalid source commit",
        )
        for filename, expected_hash in entry["source_files"].items():
            rel = Path(filename)
            require(not rel.is_absolute() and ".." not in rel.parts, "Unsafe source path")
            require(filename.startswith(f"packages/{package}/"), "Unrelated release source")
            path = root / rel
            require(
                not path.is_symlink()
                and source_matches(path, expected_hash, entry, reconciliations.get(package, {})),
                "Release source changed",
            )
        require(len(entry["artifacts"]) == 8, "Expected seven wheels and one source artifact")
        require(type(entry["run_id"]) is int and entry["run_id"] > 0, "Invalid release run")
        ids = [row["id"] for row in entry["artifacts"]]
        require(all(type(value) is int and value > 0 for value in ids), "Invalid artifact ID")
        require(len(set(ids)) == 8, "Duplicate artifact IDs")
        for row in entry["artifacts"]:
            require(Path(row["filename"]).name == row["filename"], "Unsafe artifact filename")
            require(
                re.fullmatch(r"[a-f0-9]{64}", row["sha256"]) is not None, "Invalid artifact digest"
            )
    return data


def gh_json(endpoint: str) -> dict:
    result = subprocess.run(["gh", "api", endpoint], check=True, capture_output=True)
    return json.loads(result.stdout)


def extract_reviewed(raw: bytes, row: dict, target: Path) -> None:
    require(len(raw) <= 64 * 1024 * 1024, "Artifact archive exceeds size bound")
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        entries = archive.infolist()
        require(
            len(entries) == 1 and entries[0].filename == row["filename"],
            "Unexpected artifact members",
        )
        require(entries[0].file_size <= 64 * 1024 * 1024, "Artifact member exceeds size bound")
        data = archive.read(entries[0])
    require(hashlib.sha256(data).hexdigest() == row["sha256"], "Reviewed artifact changed")
    require(not target.exists() and not target.is_symlink(), "Duplicate staged artifact")
    target.write_bytes(data)


def stage(data: dict, root: Path, output: Path, reviewed: Path) -> None:
    output.mkdir(parents=True, exist_ok=True)
    reviewed.mkdir(parents=True, exist_ok=False)
    for package, entry in data["packages"].items():
        sdk = output / entry["sdk"]["filename"]
        require(
            sdk.is_file() and not sdk.is_symlink() and digest(sdk) == entry["sdk"]["sha256"],
            "SDK wheel differs from reviewed release",
        )
        run = gh_json(f"repos/{REPOSITORY}/actions/runs/{entry['run_id']}")
        require(run["head_sha"] == entry["source_commit"], "Release run source mismatch")
        require(
            run["status"] == "completed" and run["conclusion"] == "success",
            "Release platform CI has not passed",
        )
        target = reviewed / (package + "-native")
        target.mkdir()
        for row in entry["artifacts"]:
            info = gh_json(f"repos/{REPOSITORY}/actions/artifacts/{row['id']}")
            require(
                not info["expired"] and info["name"] == row["name"], "Artifact expired or renamed"
            )
            require(info["workflow_run"]["id"] == entry["run_id"], "Artifact run mismatch")
            require(
                info["workflow_run"]["head_sha"] == entry["source_commit"],
                "Artifact source mismatch",
            )
            raw = subprocess.run(
                ["gh", "api", f"repos/{REPOSITORY}/actions/artifacts/{row['id']}/zip"],
                check=True,
                capture_output=True,
            ).stdout
            extract_reviewed(raw, row, target / row["filename"])
        checksum = "".join(f"{digest(p)}  {p.name}\n" for p in sorted(target.iterdir()))
        (target / "SHA256SUMS").write_text(checksum)
        verify(
            target,
            root_project=root / "packages" / package / "pyproject.toml",
            native_project=root / "packages" / package / "native/pyproject.toml",
            tag=f"{package}-native-v{entry['version']}",
            manifest_sha256=entry["native_manifest_sha256"],
        )
        linux = [
            p
            for p in target.glob("*.whl")
            if "manylinux" in p.name and p.name.endswith("_x86_64.whl")
        ]
        require(len(linux) == 1, "Expected one reviewed glibc x86_64 wheel")
        destination = output / linux[0].name
        require(
            not destination.exists() and not destination.is_symlink(),
            "Native output already exists",
        )
        shutil.copyfile(linux[0], destination)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--manifest-sha256", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--reviewed", type=Path, required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[2]
    require(
        args.manifest.resolve().is_relative_to(root / "reports"),
        "Release manifest must be retained under reports",
    )
    data = read_manifest(args.manifest, args.manifest_sha256, root)
    stage(data, root, args.output, args.reviewed)
    shutil.copyfile(args.manifest, args.reviewed / "release-manifest.json")


if __name__ == "__main__":
    main()
