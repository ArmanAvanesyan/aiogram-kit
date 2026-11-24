"""Paired candidates retain exact versions, independent installs and safe publishers."""

from pathlib import Path

import pytest
import yaml

try:
    import tomllib
except ModuleNotFoundError:
    import tomli as tomllib

ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize("short", ["sentinel", "cmds", "nav", "idle"])
def test_paired_metadata_and_manual_native_publisher(short):
    package = f"aiogram-{short}"
    folder = ROOT / "packages" / package
    base = tomllib.loads((folder / "pyproject.toml").read_text())["project"]
    native = tomllib.loads((folder / "native/pyproject.toml").read_text())["project"]
    cargo = tomllib.loads((folder / "native/Cargo.toml").read_text())["package"]
    assert base["version"] == native["version"] == cargo["version"]
    assert native["name"] == cargo["name"] == package + "-native"
    assert not native.get("dependencies")
    assert all("-native" not in dep for dep in base["dependencies"])
    data = yaml.safe_load((ROOT / f".github/workflows/publish-{package}-native.yml").read_text())
    triggers = data.get("on", data.get(True))
    assert set(triggers) == {"workflow_dispatch"}
    assert triggers["workflow_dispatch"]["inputs"]["manifest_sha256"]["required"] is True
    verify, publish = data["jobs"]["verify"], data["jobs"]["publish"]
    assert f"'{package}-native-v'" in verify["if"]
    assert "github.ref_type == 'tag'" in verify["if"]
    assert publish["needs"] == "verify" and publish["environment"] == "pypi"
    assert publish["permissions"] == {"contents": "read", "id-token": "write"}
    for job in (verify, publish):
        commands = "\n".join(step.get("run", "") for step in job["steps"])
        assert "verify_release_readiness.py" in commands
        assert f"--package {package}" in commands
        report = (
            "reports/2026-11-18-paired-release"
            if short == "sentinel"
            else "reports/2026-11-24-url-patches-0.3.3"
            if short == "idle"
            else "reports/2026-11-24-repeatability-0.3.3"
        )
        assert f"--report {report}" in commands
        for step in job["steps"]:
            if step.get("uses", "").startswith("actions/checkout@"):
                assert step["with"]["ref"] == "${{ github.sha }}"
        assert '--manifest-sha256 "$MANIFEST_SHA256"' in commands
        assert "maturin build" not in commands and "uv build" not in commands
    download = next(s for s in publish["steps"] if "download-artifact@" in s.get("uses", ""))
    assert download["with"]["artifact-ids"] == "${{ needs.verify.outputs.artifact_id }}"
    assert publish["steps"][-1]["with"]["packages-dir"] == "publish-dist/"


def test_sentinel_musl_check_uses_installed_metadata_instead_of_stale_release():
    workflow = yaml.safe_load((ROOT / ".github/workflows/aiogram-sentinel-native.yml").read_text())
    steps = workflow["jobs"]["wheels"]["steps"]
    command = next(s["run"] for s in steps if "n.capabilities()" in s.get("run", ""))
    assert 'version("aiogram-sentinel-native")' in command
    assert '1, "1.3.' not in command
