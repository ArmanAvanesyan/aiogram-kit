"""Bind a complete successful CI platform set and local SDK artifacts before timing."""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import re
import subprocess
import zipfile
from pathlib import Path

from prepare_release_qualification import extract_reviewed, gh_json, read_manifest
from verify_native_artifacts import verify

REPOSITORY = "ArmanAvanesyan/aiogram-kit"


def digest(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def validate_run(package: str, run: dict, source_commit: str) -> None:
    workflow = {
        "aiogram-cmds": ".github/workflows/aiogram-cmds-native.yml",
        "aiogram-nav": ".github/workflows/aiogram-nav-native-ci.yml",
        "aiogram-idle": ".github/workflows/aiogram-idle-native-ci.yml",
    }[package]
    if (
        run["head_sha"] != source_commit
        or run["status"] != "completed"
        or run["conclusion"] != "success"
        or run["path"] != workflow
    ):
        raise ValueError(
            "A complete successful matching platform workflow at the source commit is required"
        )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-commit", required=True)
    parser.add_argument("--version", required=True)
    parser.add_argument("--run", action="append", required=True, help="aiogram-PACKAGE=RUN_ID")
    parser.add_argument("--artifacts", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[2]
    if not re.fullmatch(r"[a-f0-9]{40}", args.source_commit):
        raise ValueError("A full immutable source commit is required")
    if not re.fullmatch(r"\d+\.\d+\.\d+", args.version):
        raise ValueError("Invalid release version")
    pairs = [value.split("=", 1) for value in args.run]
    if len({pair[0] for pair in pairs}) != len(pairs):
        raise ValueError("Duplicate release package")
    data = {"schema_version": 1, "repository": REPOSITORY, "packages": {}}
    for package, run_id in pairs:
        if package not in {"aiogram-cmds", "aiogram-nav", "aiogram-idle"}:
            raise ValueError("Unsupported release pair")
        run = gh_json(f"repos/{REPOSITORY}/actions/runs/{int(run_id)}")
        validate_run(package, run, args.source_commit)
        directory = args.artifacts.resolve() / (package + "-native")
        directory.mkdir(parents=True, exist_ok=True)
        sdk_directory = args.artifacts.resolve() / package
        sdk = sdk_directory / f"{package.replace('-', '_')}-{args.version}-py3-none-any.whl"
        if not sdk.is_file() or sdk.is_symlink():
            raise ValueError("Missing reviewed SDK wheel")
        artifacts = gh_json(
            f"repos/{REPOSITORY}/actions/runs/{int(run_id)}/artifacts?per_page=100"
        )["artifacts"]
        selected = [
            row
            for row in artifacts
            if row["name"].startswith("native-")
            and not row["name"].startswith("native-core-profile-")
        ]
        if len(selected) != 8:
            raise ValueError("Seven wheels and one source archive required")
        rows = []
        for artifact in selected:
            if artifact["expired"] or artifact["workflow_run"]["head_sha"] != args.source_commit:
                raise ValueError("Expired or unrelated artifact")
            raw = subprocess.check_output(
                ["gh", "api", f"repos/{REPOSITORY}/actions/artifacts/{artifact['id']}/zip"]
            )
            archive_hash = digest(raw)
            if artifact.get("digest") != "sha256:" + archive_hash:
                raise ValueError("GitHub archive digest mismatch")
            if len(raw) > 64 * 1024 * 1024:
                raise ValueError("Artifact archive exceeds size bound")
            with zipfile.ZipFile(io.BytesIO(raw)) as archive:
                if len(archive.infolist()) != 1:
                    raise ValueError("Expected one distribution in each artifact")
                member = archive.infolist()[0]
                filename = member.filename
                if (
                    Path(filename).name != filename
                    or member.file_size > 64 * 1024 * 1024
                    or (
                        not filename.startswith(
                            package.replace("-", "_") + "_native-" + args.version + "-"
                        )
                        and filename
                        != package.replace("-", "_") + "_native-" + args.version + ".tar.gz"
                    )
                ):
                    raise ValueError("Unsafe artifact filename")
                content_hash = digest(archive.read(member))
            row = {
                "id": artifact["id"],
                "name": artifact["name"],
                "filename": filename,
                "sha256": content_hash,
                "archive_sha256": archive_hash,
            }
            target = directory / filename
            if target.exists():
                if target.is_symlink() or digest(target.read_bytes()) != content_hash:
                    raise ValueError("Refusing to overwrite retained artifact")
            else:
                extract_reviewed(raw, row, target)
            rows.append(row)
        content = "".join(
            f"{r['sha256']}  {r['filename']}\n" for r in sorted(rows, key=lambda r: r["filename"])
        )
        manifest = directory / "SHA256SUMS"
        if manifest.exists() and manifest.read_text() != content:
            raise ValueError("Refusing to overwrite an artifact manifest")
        manifest.write_text(content)
        manifest_hash = digest(manifest.read_bytes())
        verify(
            directory,
            root_project=root / "packages" / package / "pyproject.toml",
            native_project=root / "packages" / package / "native/pyproject.toml",
            tag=f"{package}-native-v{args.version}",
            manifest_sha256=manifest_hash,
        )
        names = subprocess.check_output(
            [
                "git",
                "ls-files",
                f"packages/{package}/src",
                f"packages/{package}/native",
                f"packages/{package}/pyproject.toml",
            ],
            cwd=root,
            text=True,
        ).splitlines()
        sources = {}
        for name in names:
            blob = subprocess.check_output(
                ["git", "show", args.source_commit + ":" + name], cwd=root
            )
            if (root / name).is_symlink() or (root / name).read_bytes() != blob:
                raise ValueError("Current source differs from the platform commit")
            sources[name] = digest(blob)
        data["packages"][package] = {
            "version": args.version,
            "run_id": int(run_id),
            "source_commit": args.source_commit,
            "source_files": sources,
            "sdk": {"filename": sdk.name, "sha256": digest(sdk.read_bytes())},
            "native_manifest_sha256": manifest_hash,
            "artifacts": rows,
        }
        print(package, "complete source-bound platform set verified", flush=True)
    output = args.output.resolve()
    if not output.is_relative_to(root / "reports"):
        raise ValueError("Manifest must be retained under reports")
    encoded = json.dumps(data, indent=2) + "\n"
    if output.exists() and output.read_text() != encoded:
        raise ValueError("Refusing to replace previously reviewed inputs")
    # Validate the exact same schema and source checks used by CI qualification.
    output.write_text(encoded)
    read_manifest(output, digest(output.read_bytes()), root)
    print("Manifest SHA256:", digest(output.read_bytes()))


if __name__ == "__main__":
    main()
