"""Keep each independent publisher's immutable-artifact handoff identical."""

from __future__ import annotations

import argparse
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
PACKAGES = ("kit", "coordination", "sentinel", "cmds", "nav", "idle")
STEP_NAME = "Recheck the reviewed manifest after artifact download"
SCRIPT = """python3 - <<'PYTHON'
import hashlib
import os
import re
import shutil
from pathlib import Path

package = os.environ["RELEASE_PACKAGE"]
tag = os.environ["RELEASE_TAG"]
prefix = package + "-v"
if not tag.startswith(prefix):
    raise ValueError("Incorrect package tag")
version = tag[len(prefix):]
normalized = package.replace("-", "_")
expected = {f"{normalized}-{version}-py3-none-any.whl", f"{normalized}-{version}.tar.gz"}
source = Path("verified-input")
if {p.name for p in source.iterdir()} != expected | {"SHA256SUMS"}:
    raise ValueError("Unexpected handoff files")
if any(p.is_symlink() or not p.is_file() for p in source.iterdir()):
    raise ValueError("Handoff must contain regular files")
manifest = source / "SHA256SUMS"
if hashlib.sha256(manifest.read_bytes()).hexdigest() != os.environ["MANIFEST_SHA256"]:
    raise ValueError("Handoff manifest checksum mismatch")
checked = set()
for line in manifest.read_text().splitlines():
    digest, filename = line.split()
    if filename not in expected or filename in checked or not re.fullmatch(r"[a-f0-9]{64}", digest):
        raise ValueError("Invalid handoff manifest entry")
    if hashlib.sha256((source / filename).read_bytes()).hexdigest() != digest:
        raise ValueError("Handoff distribution checksum mismatch")
    checked.add(filename)
if checked != expected:
    raise ValueError("Incomplete handoff")
destination = Path("dist")
destination.mkdir()
for filename in sorted(expected):
    shutil.copyfile(source / filename, destination / filename)
PYTHON
"""


class WorkflowDumper(yaml.SafeDumper):
    """Render scripts as reviewable literal blocks, rather than escaped strings."""


def _string(dumper, value):
    return dumper.represent_scalar(
        "tag:yaml.org,2002:str", value, style="|" if "\n" in value else None
    )


WorkflowDumper.add_representer(str, _string)


def expected_handoff(package: str) -> dict:
    return {
        "name": STEP_NAME,
        "env": {
            "RELEASE_PACKAGE": package,
            "RELEASE_TAG": "${{ github.ref_name }}",
            "MANIFEST_SHA256": "${{ inputs.manifest_sha256 }}",
        },
        "run": SCRIPT,
    }


def synchronize(*, write: bool = False) -> None:
    for name in PACKAGES:
        package = "aiogram-" + name
        path = ROOT / f".github/workflows/publish-{package}.yml"
        workflow = yaml.safe_load(path.read_text())
        verify = workflow["jobs"]["verify"]
        publish = workflow["jobs"]["publish"]
        upload = next(
            step
            for step in verify["steps"]
            if step.get("uses", "").startswith("actions/upload-artifact@")
        )
        download = next(
            step
            for step in publish["steps"]
            if step.get("uses", "").startswith("actions/download-artifact@")
        )
        expected_outputs = {"artifact_id": "${{ steps.artifacts.outputs.artifact-id }}"}
        expected_upload = "dist/*.whl\ndist/*.tar.gz\ndist/SHA256SUMS\n"
        expected_download = {
            "artifact-ids": "${{ needs.verify.outputs.artifact_id }}",
            "path": "verified-input",
            "merge-multiple": True,
        }
        expected_step = expected_handoff(package)
        handoffs = [step for step in publish["steps"] if step.get("name") == STEP_NAME]
        valid = (
            verify.get("outputs") == expected_outputs
            and upload.get("id") == "artifacts"
            and upload["with"]["path"] == expected_upload
            and download["with"] == expected_download
            and handoffs == [expected_step]
            and publish["steps"].index(handoffs[0]) == publish["steps"].index(download) + 1
        )
        if not write:
            if not valid:
                raise ValueError(f"Publisher handoff is out of date: {package}")
            continue
        verify["outputs"] = expected_outputs
        upload["id"] = "artifacts"
        upload["with"]["path"] = expected_upload
        download["with"] = expected_download
        publish["steps"] = [step for step in publish["steps"] if step.get("name") != STEP_NAME]
        publish["steps"].insert(publish["steps"].index(download) + 1, expected_step)
        triggers = workflow.pop(True, workflow.pop("on", {}))
        workflow["on"] = triggers
        path.write_text(yaml.dump(workflow, Dumper=WorkflowDumper, sort_keys=False, width=120))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true", help="Update the six publisher workflows")
    synchronize(write=parser.parse_args().write)
