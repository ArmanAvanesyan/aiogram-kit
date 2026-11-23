"""Detect lost advertised history even when its Git objects remain locally available."""

import importlib.util
import json
import subprocess
from pathlib import Path

import pytest

SOURCE = Path(__file__).resolve().parents[2] / "tools/verify_migration.py"
spec = importlib.util.spec_from_file_location("history_verifier", SOURCE)
assert spec and spec.loader
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


@pytest.fixture
def history(tmp_path, monkeypatch):
    root = tmp_path / "checkout"
    root.mkdir()
    remote = tmp_path / "origin.git"

    def git(*args, cwd=root):
        return subprocess.check_output(
            ["git", *args], cwd=cwd, text=True, stderr=subprocess.PIPE
        ).strip()

    git("init", "-b", "main")
    git("init", "--bare", str(remote))
    (root / "source").write_text("original\n")
    git("add", "source")
    git(
        "-c", "user.name=Test", "-c", "user.email=test@example.invalid", "commit", "-qm", "original"
    )
    original = git("rev-parse", "HEAD")
    ref = "refs/heads/history/example/heads/main"
    git("update-ref", ref, original)
    git("remote", "add", "origin", str(remote))
    git("push", "origin", ref)
    (root / "source").write_text("later\n")
    git("add", "source")
    git("-c", "user.name=Test", "-c", "user.email=test@example.invalid", "commit", "-qm", "later")
    report = root / "reports"
    report.mkdir()
    (report / "history-map.json").write_text(
        json.dumps(
            [
                {
                    "repository": "example",
                    "source_head": original,
                    "history_ref": ref,
                }
            ]
        )
    )
    (report / "refs-map.json").write_text(
        json.dumps(
            [
                {
                    "repository": "example",
                    "object_id": original,
                    "destination_ref": ref,
                }
            ]
        )
    )
    (report / "preserved-kit-working-copy.json").write_text("[]")
    (report / "repository-map.json").write_text(json.dumps([{"source_name": "example"}]))
    monkeypatch.setattr(module, "ROOT", root)
    monkeypatch.setattr(module, "REPORT", report)
    return git, remote, ref, report


def test_verifies_original_ancestry_and_remote_namespace(history):
    module.verify(historical_objects=True, remote_refs=True)


@pytest.mark.parametrize("change", ["deleted", "retargeted"])
def test_remote_drift_fails_despite_retained_local_objects(history, change):
    git, remote, ref, _ = history
    if change == "deleted":
        git("update-ref", "-d", ref, cwd=remote)
    else:
        git("push", "origin", "main")
        git("update-ref", ref, git("rev-parse", "HEAD"), cwd=remote)
    module.verify(historical_objects=True)
    with pytest.raises(ValueError, match="Remote historical ref differs"):
        module.verify(historical_objects=True, remote_refs=True)


def test_rejects_temporary_or_unmapped_history_references(history):
    _, _, _, report = history
    path = report / "history-map.json"
    rows = json.loads(path.read_text())
    rows[0]["history_ref"] = "refs/migration/example/heads/"
    path.write_text(json.dumps(rows))
    with pytest.raises(ValueError, match="no matching preserved ref"):
        module.verify()


def test_rejects_missing_source_ancestry_inventory(history):
    _, _, _, report = history
    (report / "history-map.json").write_text("[]")
    with pytest.raises(ValueError, match="Source history inventory differs"):
        module.verify()


def test_rejects_duplicate_published_ref_mapping(history):
    _, _, _, report = history
    path = report / "refs-map.json"
    rows = json.loads(path.read_text())
    path.write_text(json.dumps(rows * 2))
    with pytest.raises(ValueError, match="Duplicate historical"):
        module.verify()
