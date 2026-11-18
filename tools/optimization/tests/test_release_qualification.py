"""Release qualification consumes reviewed platform artifacts, never substitute builds."""

import hashlib
import importlib.util
import io
import json
import zipfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]


@pytest.fixture
def module(monkeypatch):
    tools = ROOT / "tools/optimization"
    monkeypatch.syspath_prepend(str(tools))
    spec = importlib.util.spec_from_file_location(
        "release_qualification", tools / "prepare_release_qualification.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def manifest(tmp_path, module):
    data = {"repository": module.REPOSITORY, "packages": {}}
    for package in sorted(module.PACKAGES):
        source = tmp_path / "packages" / package / "native/src/lib.rs"
        source.parent.mkdir(parents=True)
        source.write_bytes(b"reviewed source")
        data["packages"][package] = {
            "version": "1.0.0",
            "source_commit": "a" * 40,
            "run_id": 123,
            "sdk": {
                "filename": package.replace("-", "_") + "-1.0.0-py3-none-any.whl",
                "sha256": "a" * 64,
            },
            "source_files": {str(source.relative_to(tmp_path)): module.digest(source)},
            "artifacts": [
                {"id": i + 1, "filename": f"artifact-{i}.whl", "sha256": "a" * 64} for i in range(8)
            ],
        }
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(data))
    return path, tmp_path


def test_manifest_binds_reviewed_source(module, manifest):
    path, root = manifest
    data = module.read_manifest(path, module.digest(path), root)
    assert set(data["packages"]) == module.PACKAGES


@pytest.mark.parametrize(
    "change", ["digest", "source", "package", "sdk_path", "duplicate_id", "source_path"]
)
def test_manifest_rejects_substitutions(module, tmp_path, change, manifest):
    original, root = manifest
    data = json.loads(original.read_text())
    entry = data["packages"]["aiogram-nav"]
    if change == "source":
        entry["source_files"][next(iter(entry["source_files"]))] = "0" * 64
    elif change == "package":
        del data["packages"]["aiogram-idle"]
    elif change == "sdk_path":
        entry["sdk"]["filename"] = "/outside.whl"
    elif change == "duplicate_id":
        entry["artifacts"][1]["id"] = entry["artifacts"][0]["id"]
    elif change == "source_path":
        entry["source_files"] = {"../../outside": "0" * 64}
    path = tmp_path / "changed.json"
    path.write_text(json.dumps(data))
    expected = "0" * 64 if change == "digest" else module.digest(path)
    with pytest.raises(ValueError):
        module.read_manifest(path, expected, root)


@pytest.mark.parametrize("change", [None, "name", "extra", "digest"])
def test_extract_only_exact_reviewed_member(module, tmp_path, change):
    body = b"reviewed bytes"
    raw = io.BytesIO()
    with zipfile.ZipFile(raw, "w") as archive:
        archive.writestr("../outside" if change == "name" else "reviewed.whl", body)
        if change == "extra":
            archive.writestr("extra.whl", body)
    row = {"filename": "reviewed.whl", "sha256": hashlib.sha256(body).hexdigest()}
    if change == "digest":
        row["sha256"] = "0" * 64
    target = tmp_path / "reviewed.whl"
    if change:
        with pytest.raises(ValueError):
            module.extract_reviewed(raw.getvalue(), row, target)
        assert not target.exists()
    else:
        module.extract_reviewed(raw.getvalue(), row, target)
        assert target.read_bytes() == body
        with pytest.raises(ValueError, match="Duplicate"):
            module.extract_reviewed(raw.getvalue(), row, target)


def test_unfinished_platform_ci_stops_before_download(module, tmp_path, monkeypatch):
    output = tmp_path / "wheels"
    output.mkdir()
    sdk = output / "sdk.whl"
    sdk.write_bytes(b"sdk")
    entry = {
        "sdk": {"filename": sdk.name, "sha256": module.digest(sdk)},
        "run_id": 123,
        "source_commit": "a" * 40,
    }
    monkeypatch.setattr(
        module,
        "gh_json",
        lambda _: {"head_sha": "a" * 40, "status": "in_progress", "conclusion": None},
    )
    with pytest.raises(ValueError, match="platform CI has not passed"):
        module.stage({"packages": {"aiogram-nav": entry}}, ROOT, output, tmp_path / "reviewed")


@pytest.mark.parametrize("change", ["expired", "name", "run", "source"])
def test_foreign_or_expired_artifact_stops_before_download(module, tmp_path, monkeypatch, change):
    output = tmp_path / "wheels"
    output.mkdir()
    sdk = output / "sdk.whl"
    sdk.write_bytes(b"sdk")
    entry = {
        "sdk": {"filename": sdk.name, "sha256": module.digest(sdk)},
        "run_id": 123,
        "source_commit": "a" * 40,
        "artifacts": [{"id": 456, "name": "native-source"}],
    }
    metadata = {
        "expired": False,
        "name": "native-source",
        "workflow_run": {"id": 123, "head_sha": "a" * 40},
    }
    if change == "expired":
        metadata["expired"] = True
    elif change == "name":
        metadata["name"] = "other"
    elif change == "run":
        metadata["workflow_run"]["id"] = 999
    else:
        metadata["workflow_run"]["head_sha"] = "b" * 40
    monkeypatch.setattr(
        module,
        "gh_json",
        lambda endpoint: (
            metadata
            if "/artifacts/" in endpoint
            else {"head_sha": "a" * 40, "status": "completed", "conclusion": "success"}
        ),
    )
    with pytest.raises(ValueError):
        module.stage({"packages": {"aiogram-nav": entry}}, ROOT, output, tmp_path / "reviewed")
    assert not list((tmp_path / "reviewed/aiogram-nav-native").iterdir())


def test_extract_refuses_broken_symlink(module, tmp_path):
    raw = io.BytesIO()
    with zipfile.ZipFile(raw, "w") as archive:
        archive.writestr("reviewed.whl", b"body")
    outside = tmp_path / "outside"
    target = tmp_path / "reviewed.whl"
    target.symlink_to(outside)
    with pytest.raises(ValueError, match="Duplicate"):
        module.extract_reviewed(
            raw.getvalue(),
            {"filename": target.name, "sha256": hashlib.sha256(b"body").hexdigest()},
            target,
        )
    assert not outside.exists()
