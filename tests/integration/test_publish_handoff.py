"""Exercise the actual publisher-side script after immutable artifact download."""

import hashlib
import importlib.util
import os
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("publish_handoff", ROOT / "tools/publish_handoff.py")
assert spec and spec.loader
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def test_generated_publisher_handoffs_are_current():
    module.synchronize()


@pytest.fixture
def handoff(tmp_path):
    source = tmp_path / "verified-input"
    source.mkdir()
    files = ["aiogram_nav-0.3.1-py3-none-any.whl", "aiogram_nav-0.3.1.tar.gz"]
    for name in files:
        (source / name).write_bytes(name.encode())
    manifest = source / "SHA256SUMS"
    manifest.write_text(
        "".join(
            f"{hashlib.sha256((source / name).read_bytes()).hexdigest()}  {name}\n"
            for name in files
        )
    )
    env = {
        **os.environ,
        "RELEASE_PACKAGE": "aiogram-nav",
        "RELEASE_TAG": "aiogram-nav-v0.3.1",
        "MANIFEST_SHA256": hashlib.sha256(manifest.read_bytes()).hexdigest(),
    }
    return tmp_path, source, files, env


def test_handoff_copies_only_two_reviewed_distributions(handoff):
    root, _, files, env = handoff
    subprocess.run(
        ["bash", "-e", "-c", module.SCRIPT], cwd=root, env=env, check=True, capture_output=True
    )
    assert {p.name for p in (root / "dist").iterdir()} == set(files)


@pytest.mark.parametrize(
    "change", ["blob", "manifest", "extra", "missing", "duplicate", "symlink", "tag"]
)
def test_publish_side_rejects_changed_handoff(handoff, change):
    root, source, files, env = handoff
    if change == "blob":
        (source / files[0]).write_bytes(b"changed after verification")
    elif change == "manifest":
        (source / "SHA256SUMS").write_text("bad")
    elif change == "extra":
        (source / "unreviewed.whl").write_bytes(b"bad")
    elif change == "missing":
        (source / files[0]).unlink()
    elif change == "duplicate":
        manifest = source / "SHA256SUMS"
        manifest.write_text(manifest.read_text() * 2)
        env["MANIFEST_SHA256"] = hashlib.sha256(manifest.read_bytes()).hexdigest()
    elif change == "symlink":
        external = root / "external"
        external.write_bytes((source / files[0]).read_bytes())
        (source / files[0]).unlink()
        (source / files[0]).symlink_to(external)
    else:
        env["RELEASE_TAG"] = "aiogram-idle-v0.3.1"
    result = subprocess.run(
        ["bash", "-e", "-c", module.SCRIPT], cwd=root, env=env, capture_output=True, check=False
    )
    assert result.returncode != 0
    assert not (root / "dist").exists()
