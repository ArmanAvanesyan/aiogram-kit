"""A project-specific publisher cannot build or upload another project's artifacts."""

from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
PACKAGES = [
    "aiogram-kit",
    "aiogram-coordination",
    "aiogram-sentinel",
    "aiogram-cmds",
    "aiogram-nav",
    "aiogram-idle",
]


@pytest.mark.parametrize("package", PACKAGES)
def test_publisher_is_tag_scoped_and_uploads_only_verified_artifacts(package):
    workflow = yaml.safe_load((ROOT / f".github/workflows/publish-{package}.yml").read_text())
    triggers = workflow.get(True, workflow.get("on"))
    assert set(triggers) == {"workflow_dispatch"}
    assert triggers["workflow_dispatch"]["inputs"]["manifest_sha256"]["required"] is True
    verify = workflow["jobs"]["verify"]
    assert "github.ref_type == 'tag'" in verify["if"]
    assert f"'{package}-v'" in verify["if"]
    runs = [step.get("run", "") for step in verify["steps"]]
    assert any(f'--package {package} --tag "$GITHUB_REF_NAME"' in run for run in runs)
    assert not any("uv build" in run or "python -m build" in run for run in runs)
    upload = next(
        step
        for step in verify["steps"]
        if step.get("uses", "").startswith("actions/upload-artifact@")
    )
    publish = workflow["jobs"]["publish"]
    assert publish["needs"] == "verify"
    assert publish["environment"] == "pypi"
    assert publish["permissions"] == {"id-token": "write"}
    download = next(
        step
        for step in publish["steps"]
        if step.get("uses", "").startswith("actions/download-artifact@")
    )
    assert upload["id"] == "artifacts"
    assert verify["outputs"] == {"artifact_id": "${{ steps.artifacts.outputs.artifact-id }}"}
    assert download["with"]["artifact-ids"] == "${{ needs.verify.outputs.artifact_id }}"
    assert download["with"]["path"] == "verified-input"
    assert "dist/SHA256SUMS" in upload["with"]["path"]
    handoff = next(
        step
        for step in publish["steps"]
        if step.get("name") == "Recheck the reviewed manifest after artifact download"
    )
    assert handoff["env"]["RELEASE_PACKAGE"] == package
    assert handoff["env"]["MANIFEST_SHA256"] == "${{ inputs.manifest_sha256 }}"
    assert (
        publish["steps"].index(download)
        < publish["steps"].index(handoff)
        < len(publish["steps"]) - 1
    )
