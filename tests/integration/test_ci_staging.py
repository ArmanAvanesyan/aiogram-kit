"""CI stages distributions beside the checkout, keeping other packages out of sdists."""

import importlib.util
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("port_ci", ROOT / "tools/port_ci.py")
assert spec and spec.loader
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def test_native_build_and_artifacts_share_an_isolated_directory():
    package = ROOT / "packages/aiogram-sentinel"
    result = module.port(package, package / ".github/workflows/native.yml")
    job = result["jobs"]["wheels"]
    assert job["defaults"]["run"]["working-directory"] == "distribution"
    stage = next(
        step for step in job["steps"] if step.get("name") == "Stage isolated distribution checkout"
    )
    assert '"$GITHUB_WORKSPACE/distribution/"' in stage["run"]
    assert stage["shell"] == "bash"
    maturin = next(
        step for step in job["steps"] if step.get("uses", "").startswith("PyO3/maturin-action@")
    )
    assert maturin["with"]["working-directory"] == "distribution"
    upload = next(
        step for step in job["steps"] if step.get("uses", "").startswith("actions/upload-artifact@")
    )
    assert upload["with"]["path"] == "distribution/wheelhouse/*.whl"


def test_combined_ci_uses_current_peers_outside_the_distribution():
    package = ROOT / "packages/aiogram-idle"
    result = module.port(package, package / ".github/workflows/nav-integration.yml")
    job = result["jobs"]["combined"]
    assert job["defaults"]["run"]["working-directory"] == "aiogram-idle"
    assert not any(step.get("with", {}).get("repository") for step in job["steps"])
    peers = next(
        step
        for step in job["steps"]
        if step.get("name") == "Install matching monorepo peer artifacts"
    )
    assert "/monorepo-source/packages/aiogram-nav" in peers["run"]
    assert "/monorepo-source/packages/aiogram-coordination" in peers["run"]
    assert not any("uv run --frozen" in step.get("run", "") for step in job["steps"])


def test_generated_workflows_preserve_staging_and_schedule_rules():
    for path in (ROOT / ".github/workflows").glob("aiogram-*.yml"):
        document = yaml.safe_load(path.read_text())
        for job in document["jobs"].values():
            stages = [
                step
                for step in job.get("steps", [])
                if step.get("name") == "Stage isolated distribution checkout"
            ]
            if stages:
                assert job["defaults"]["run"]["working-directory"] != "."
    cmds = yaml.safe_load((ROOT / ".github/workflows/aiogram-cmds-ci.yml").read_text())
    triggers = cmds.get(True, cmds.get("on"))
    assert triggers["schedule"] == [{"cron": "0 6 * * 1"}]
    assert "github.ref == 'refs/heads/main'" in cmds["jobs"]["platform-tests"]["if"]


def test_cmds_pypy_uses_locked_test_dependencies_without_publication_tools():
    package = ROOT / "packages/aiogram-cmds"
    result = module.port(package, package / ".github/workflows/ci.yml")
    runs = "\n".join(s.get("run", "") for s in result["jobs"]["pypy-tests"]["steps"])
    assert "uv export --frozen" in runs
    assert "uv venv --python pypy3.10" in runs
    assert "--prune pydantic" in runs
    assert "pydantic>=2.12,<2.13" in runs
    assert "uv pip install --constraint" in runs
    assert "hypothesis==6.140.3" in runs
    assert "--prune hypothesis" in runs
    assert "uv sync --frozen --all-extras" not in runs


def test_cmds_timing_probes_report_results_without_an_unused_benchmark_plugin():
    package = ROOT / "packages/aiogram-cmds"
    job = module.port(package, package / ".github/workflows/ci.yml")["jobs"]["performance"]
    runs = "\n".join(s.get("run", "") for s in job["steps"])
    assert "--benchmark-json" not in runs
    assert "--junitxml=reports/performance-results.xml" in runs
    upload = next(
        s for s in job["steps"] if s.get("uses", "").startswith("actions/upload-artifact@")
    )
    assert upload["with"]["path"] == "distribution/reports/performance-results.xml"


def test_nav_artifact_tests_stage_benchmark_helpers_without_sdk_source():
    package = ROOT / "packages/aiogram-nav"
    generated = module.port(package, package / ".github/workflows/ci.yml")
    artifact_scripts = [
        step["run"]
        for job in generated["jobs"].values()
        for step in job["steps"]
        if "cp -R tests examples tools" in step.get("run", "")
    ]
    assert len(artifact_scripts) == 2
    for script in artifact_scripts:
        assert "cp -R tests examples tools benchmarks" in script
        assert "cp -R src" not in script
        assert "uv pip install" in script
        assert "-m pytest" in script


def test_cmds_benchmark_tools_are_installed_after_clean_sdk_verification():
    package = ROOT / "packages/aiogram-cmds"
    result = module.port(package, package / ".github/workflows/ci.yml")
    scripts = [
        step["run"]
        for job in result["jobs"].values()
        for step in job["steps"]
        if step.get("name") == "Verify independent wheel and sdist without optional packages"
    ]
    assert len(scripts) == 1
    script = scripts[0]
    assert "cp -R tests examples benchmarks" in script
    assert "cp -R src" not in script
    assert script.index('find_spec("redis") is None') < script.index("orjson psutil pyperf")
    assert script.index("examples/application_profiles.py --dry-run") < script.index(
        "orjson psutil pyperf"
    )
    assert "-m pytest tests/unit/test_benchmark_sampling.py" in script
