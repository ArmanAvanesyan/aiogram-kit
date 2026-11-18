from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

SPEC = spec_from_file_location(
    "benchmark_controller", Path(__file__).parents[1] / "run_benchmarks.py"
)
assert SPEC is not None and SPEC.loader is not None
MODULE = module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def test_helper_changes_and_additions_change_fingerprint(tmp_path):
    (tmp_path / "run.py").write_text("pass\n")
    nested = tmp_path / "helpers"
    nested.mkdir()
    helper = nested / "wire.py"
    helper.write_text("VERSION = 1\n")
    before = MODULE.driver_fingerprints(tmp_path)
    assert set(before) == {"run.py", "helpers/wire.py"}
    helper.write_text("VERSION = 2\n")
    changed = MODULE.driver_fingerprints(tmp_path)
    assert changed != before
    assert changed["run.py"] == before["run.py"]
    (tmp_path / "extra.py").write_text("pass\n")
    assert MODULE.driver_fingerprints(tmp_path) != changed


def test_generated_non_source_files_do_not_change_fingerprint(tmp_path):
    (tmp_path / "run.py").write_text("pass\n")
    before = MODULE.driver_fingerprints(tmp_path)
    (tmp_path / "result.json").write_text("{}")
    (tmp_path / "__pycache__").mkdir()
    (tmp_path / "__pycache__" / "ignored.py").write_text("pass\n")
    assert MODULE.driver_fingerprints(tmp_path) == before


def test_benchmark_bootstrap_uses_same_isolation_as_probe(tmp_path):
    import json
    import os
    import subprocess
    import sys

    probe = json.loads(
        subprocess.check_output([sys.executable, "-I", "-c", MODULE.PROBE, "pytest"], text=True)
    )
    # Both normal script-directory precedence and PYTHONPATH must lose to the
    # verified installed module preimport. Local benchmark helpers still work.
    (tmp_path / "pytest.py").write_text("raise RuntimeError('source shadow')\n")
    (tmp_path / "local_helper.py").write_text("VALUE = 42\n")
    driver = tmp_path / "run.py"
    driver.write_text(
        "import json,sys,pytest,local_helper\n"
        "print(json.dumps({'module':pytest.__file__,'helper':local_helper.VALUE,'argv':sys.argv[1:]}))\n"
    )
    output = tmp_path / "result.json"
    command = MODULE.benchmark_command(
        sys.executable, [probe], driver, "python", output, ["--samples", "3"]
    )
    env = dict(os.environ, PYTHONPATH=str(tmp_path))
    result = json.loads(subprocess.check_output(command, env=env, cwd=tmp_path, text=True))
    assert result["module"] == probe["module"]
    assert result["helper"] == 42
    assert result["argv"] == ["--engine", "python", "--output", str(output), "--samples", "3"]


def test_reserved_driver_flags_cannot_override_profile(tmp_path):
    import pytest

    for extra in [
        ["--engine", "rust"],
        ["--engine=rust"],
        ["--output=/tmp/other.json"],
        ["--eng=rust"],
        ["--out=other"],
    ]:
        with pytest.raises(ValueError, match="cannot override"):
            MODULE.benchmark_command("python", [], tmp_path / "run.py", "python", "out", extra)


def test_local_uv_wheel_without_recorded_digest_requires_installed_file_parity(
    tmp_path, monkeypatch
):
    import hashlib
    import json
    import types
    import zipfile

    installed = tmp_path / "site-packages"
    module = installed / "demo_pkg" / "__init__.py"
    module.parent.mkdir(parents=True)
    module.write_text("VERSION = '1.0'\n")
    archive = tmp_path / "demo_pkg-1.0-py3-none-any.whl"
    with zipfile.ZipFile(archive, "w") as wheel:
        wheel.writestr("demo_pkg/__init__.py", module.read_bytes())
        wheel.writestr("demo_pkg-1.0.dist-info/RECORD", "")
    namespace = {}
    exec(MODULE.PROBE_COMMON, namespace)
    importer = namespace["importlib"]
    original_import = importer.import_module
    original_distribution = importer.metadata.distribution

    class Distribution:
        version = "1.0"

        def read_text(self, name):
            assert name == "direct_url.json"
            return json.dumps({"url": archive.as_uri(), "archive_info": {}})

        def locate_file(self, name):
            return installed / name

    monkeypatch.setattr(
        importer,
        "import_module",
        lambda name, *args: (
            types.SimpleNamespace(__file__=str(module))
            if name == "demo_pkg"
            else original_import(name, *args)
        ),
    )
    monkeypatch.setattr(
        importer.metadata,
        "distribution",
        lambda name: Distribution() if name == "demo-pkg" else original_distribution(name),
    )
    probe = namespace["installed"]("demo-pkg")
    assert probe["artifact_sha256"] == hashlib.sha256(archive.read_bytes()).hexdigest()
    module.write_text("VERSION = 'tampered'\n")
    import pytest

    with pytest.raises(RuntimeError, match="Installed files differ"):
        namespace["installed"]("demo-pkg")


def test_cpu_affinity_rejects_unavailable_or_ambiguous_ids(monkeypatch):
    import pytest

    monkeypatch.setattr(MODULE.os, "sched_getaffinity", lambda pid: {2, 4}, raising=False)
    monkeypatch.setattr(MODULE.os, "sched_setaffinity", lambda *args: None, raising=False)
    assert MODULE.cpu_affinity(None) is None
    assert MODULE.cpu_affinity("4,2") == [2, 4]
    for bad in ("", "1", "2,2", "-1", "2-4", " 2", "\uff12"):
        with pytest.raises(ValueError, match="CPU affinity"):
            MODULE.cpu_affinity(bad)


def test_measurement_controls_reject_mid_driver_affinity_changes():
    import pytest

    before = {
        "cpu_affinity": [2],
        "host_cpu_count": 8,
        "gc_enabled": True,
        "gc_thresholds": [700, 10, 10],
    }
    after = {**before, "cpu_affinity": [3]}
    with pytest.raises(ValueError, match="affinity changed"):
        MODULE.measurement_controls({"before": before, "after": after}, [2])
    with pytest.raises(ValueError, match="affinity changed"):
        MODULE.measurement_controls({"before": before, "after": before}, [3])
    controls = MODULE.measurement_controls({"before": before, "after": before}, [2])
    assert controls["effective_cpu_count"] == 1
    assert controls["host_cpu_count"] == 8
    assert controls["gc_policy"] == "unchanged"


def test_bootstrap_observations_survive_driver_failure_without_changing_gc(tmp_path):
    import json
    import subprocess
    import sys

    import pytest

    driver = tmp_path / "failure.py"
    driver.write_text("raise RuntimeError('deliberate driver failure')\n")
    observations = tmp_path / "host.json"
    command = MODULE.benchmark_command(
        sys.executable,
        [],
        driver,
        "python",
        tmp_path / "result.json",
        [],
        observations=observations,
    )
    with pytest.raises(subprocess.CalledProcessError):
        subprocess.check_output(command, stderr=subprocess.STDOUT)
    recorded = json.loads(observations.read_text())
    assert recorded["before"]["gc_enabled"] is True
    assert recorded["after"]["gc_enabled"] is True
    assert recorded["before"]["gc_thresholds"] == recorded["after"]["gc_thresholds"]
    assert "process_usage" in recorded["before"]
    assert "linux_cpu" in recorded["before"]


def test_bootstrap_pins_only_child_and_records_effective_count(tmp_path):
    import json
    import os
    import subprocess
    import sys

    import pytest

    if not hasattr(os, "sched_getaffinity"):
        pytest.skip("Linux affinity is unavailable")
    original = sorted(os.sched_getaffinity(0))
    selected = [original[0]]
    driver = tmp_path / "affinity.py"
    driver.write_text("import os,json; print(json.dumps(sorted(os.sched_getaffinity(0))))\n")
    output = tmp_path / "result.json"
    command = MODULE.benchmark_command(
        sys.executable,
        [],
        driver,
        "python",
        output,
        [],
        affinity=selected,
    )
    assert json.loads(subprocess.check_output(command, text=True)) == selected
    assert sorted(os.sched_getaffinity(0)) == original
    recorded = json.loads(output.with_suffix(".host.json").read_text())
    assert MODULE.measurement_controls(recorded, selected)["effective_cpu_count"] == 1


def test_cmds_driver_preserves_existing_individual_samples_without_resampling():
    import ast

    driver = Path(__file__).parents[3] / "packages/aiogram-cmds/benchmarks/run.py"
    tree = ast.parse(driver.read_text())
    found = set()
    for function in tree.body:
        if isinstance(function, (ast.FunctionDef, ast.AsyncFunctionDef)) and function.name in {
            "sample",
            "sample_async",
        }:
            for node in ast.walk(function):
                if not isinstance(node, ast.Dict):
                    continue
                for key, value in zip(node.keys, node.values, strict=True):
                    if isinstance(key, ast.Constant) and key.value == "individual_latency_ns":
                        assert isinstance(value, ast.Dict)
                        fields = dict(zip((k.value for k in value.keys), value.values, strict=True))
                        assert isinstance(fields["values"], ast.Name)
                        assert fields["values"].id == "individual"
                        found.add(function.name)
    assert found == {"sample", "sample_async"}


def test_measurement_controls_cannot_hide_disabled_or_changed_gc():
    import pytest

    before = {
        "cpu_affinity": [2],
        "host_cpu_count": 8,
        "gc_enabled": True,
        "gc_thresholds": [700, 10, 10],
    }
    for after in ({**before, "gc_enabled": False}, {**before, "gc_thresholds": [0, 10, 10]}):
        with pytest.raises(ValueError, match="GC controls"):
            MODULE.measurement_controls({"before": before, "after": after}, [2])
