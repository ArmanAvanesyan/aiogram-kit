"""Publisher credentials cannot be reached with held or substituted performance evidence."""

import gzip
import hashlib
import importlib.util
import json
from pathlib import Path

import pytest

TOOLS = Path(__file__).resolve().parents[1]


@pytest.fixture
def proof(tmp_path, monkeypatch):
    monkeypatch.syspath_prepend(str(TOOLS))
    spec = importlib.util.spec_from_file_location(
        "release_readiness", TOOLS / "verify_release_readiness.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    report = tmp_path / "reports/2026-11-18-paired-release"
    folder = report / "shipping-qualification/native-qualification/aiogram-nav"
    folder.mkdir(parents=True)
    source = tmp_path / "packages/aiogram-nav/src/pkg.py"
    source.parent.mkdir(parents=True)
    source.write_bytes(b"reviewed source")
    manifest = {
        "packages": {
            "aiogram-nav": {
                "version": "1.0.0",
                "native_manifest_sha256": "b" * 64,
                "sdk": {"sha256": "c" * 64},
                "source_files": {
                    "packages/aiogram-nav/src/pkg.py": hashlib.sha256(
                        source.read_bytes()
                    ).hexdigest()
                },
                "artifacts": [{"filename": "native-manylinux_2_17_x86_64.whl", "sha256": "d" * 64}],
            }
        }
    }
    raw = json.dumps(manifest).encode()
    (report / "ci-artifact-manifest.json").write_bytes(raw)
    readiness = {
        "performance_manifest_sha256": hashlib.sha256(raw).hexdigest(),
        "packages": [
            {
                "sdk": "aiogram-nav",
                "version": "1.0.0",
                "native_performance": "pass",
                "native_platform_and_artifacts": "pass",
                "sdk_packaging_and_standalone": "pass",
                "performance_failures": [],
                "native_manifest_sha256": "b" * 64,
            }
        ],
    }
    (report / "readiness.json").write_text(json.dumps(readiness))
    protocol = json.dumps(
        {
            "cpu_workloads": {"aiogram-nav": ["cpu"]},
            "required_latency": {"aiogram-nav": ["latency"]},
        }
    ).encode()
    (folder.parent / "protocol.json").write_bytes(protocol)
    monkeypatch.setattr(module, "PROTOCOL_SHA256", hashlib.sha256(protocol).hexdigest())
    comparisons = [{"workload": "cpu", "rust_over_python_cpu": 0.7}]
    gate = {
        "qualified": True,
        "failures": [],
        "cpu_workloads_selected": ["cpu"],
        "required_latency_workloads": ["latency"],
        "comparisons": comparisons,
        "inputs": [],
    }
    for label in ("python-a", "rust-a", "rust-b", "python-b"):
        raw = json.dumps({"label": label}).encode()
        path = folder / label / "aiogram-nav.json.gz"
        path.parent.mkdir()
        path.write_bytes(gzip.compress(raw))
        gate["inputs"].append(
            {
                "path": f"/ci/{label}/aiogram-nav.json",
                "sha256": hashlib.sha256(raw).hexdigest(),
                "qualification_provenance": {
                    "base_artifact_sha256": "c" * 64,
                    "native_artifact_sha256": "d" * 64 if label.startswith("rust") else None,
                },
            }
        )
    (folder / "native-gate.json").write_text(json.dumps(gate))
    calls = []
    monkeypatch.setattr(
        module, "verify_artifacts", lambda *args, **kwargs: calls.append((args, kwargs))
    )
    monkeypatch.setattr(module, "load", lambda path: json.loads(path.read_text()))

    def compare(python, rust, cpu, latency):
        assert [p["label"] for p in python] == ["python-a", "python-b"]
        assert [p["label"] for p in rust] == ["rust-a", "rust-b"]
        assert cpu == ["cpu"] and latency == ["latency"]
        return {"qualified": True, "failures": [], "comparisons": comparisons}

    monkeypatch.setattr(module, "compare", compare)
    return module, tmp_path, report, folder, calls


def verify(proof, **changes):
    module, root, _, _, _ = proof
    return module.verify(
        root,
        "aiogram-nav",
        changes.get("tag", "aiogram-nav-native-v1.0.0"),
        root / "artifacts",
        changes.get("digest", "b" * 64),
    )


def test_recomputed_exact_proof_allows_only_the_named_pair(proof):
    result = verify(proof)
    assert result["qualified"] is True and result["package"] == "aiogram-nav-native"
    assert len(proof[-1]) == 1


@pytest.mark.parametrize(
    "field", ["native_performance", "native_platform_and_artifacts", "sdk_packaging_and_standalone"]
)
def test_hold_stops_before_artifact_handoff(proof, field):
    _, _, report, _, calls = proof
    path = report / "readiness.json"
    data = json.loads(path.read_text())
    data["packages"][0][field] = "hold"
    path.write_text(json.dumps(data))
    with pytest.raises(ValueError):
        verify(proof)
    assert not calls


@pytest.mark.parametrize(
    "change", ["source", "raw", "native_digest", "gate", "ratios", "input_manifest"]
)
def test_changed_evidence_cannot_authorize_publication(proof, change):
    _, root, report, folder, _ = proof
    gate_path = folder / "native-gate.json"
    gate = json.loads(gate_path.read_text())
    if change == "source":
        (root / "packages/aiogram-nav/src/pkg.py").write_bytes(b"changed")
    elif change == "raw":
        (folder / "rust-a/aiogram-nav.json.gz").write_bytes(gzip.compress(b"changed"))
    elif change == "input_manifest":
        (report / "ci-artifact-manifest.json").write_bytes(b"changed")
    elif change == "native_digest":
        gate["inputs"][1]["qualification_provenance"]["native_artifact_sha256"] = "e" * 64
    elif change == "gate":
        gate["qualified"] = False
    else:
        gate["comparisons"] = []
    gate_path.write_text(json.dumps(gate))
    with pytest.raises(ValueError):
        verify(proof)


@pytest.mark.parametrize("change", [{"tag": "aiogram-idle-native-v1.0.0"}, {"digest": "e" * 64}])
def test_wrong_release_or_manifest_is_rejected(proof, change):
    with pytest.raises(ValueError):
        verify(proof, **change)
