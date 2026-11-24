"""Retirement must not regress live links or erase protected historical snapshots."""

import importlib.util
import subprocess
from pathlib import Path

import pytest

try:
    import tomllib
except ModuleNotFoundError:
    import tomli as tomllib

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location(
    "retired_links", ROOT / "tools/check_retired_references.py"
)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def test_no_maintained_links_to_retired_repositories():
    assert module.violations() == []


@pytest.mark.parametrize("name", module.RETIRED)
def test_retired_urls_match_only_whole_repository_names(name):
    assert module.OLD_URL.search(f"https://github.com/ArmanAvanesyan/{name}/blob/main/file")
    assert module.OLD_URL.search(f"https://armanavanesyan.github.io/{name}/")
    assert not module.OLD_URL.search(f"https://github.com/ArmanAvanesyan/{name}-native")


def test_immutable_inputs_are_excluded_but_live_workflows_are_checked():
    for name in (
        "reports/monorepo-migration/refs-map.json",
        "packages/aiogram-nav/reports/old.md",
        "packages/aiogram-kit/docs/design/aiogram-idle.md",
        "packages/aiogram-kit/mkdocs.yml",
        "packages/aiogram-nav/.github/workflows/ci.yml",
    ):
        assert not module.maintained(Path(name))
    assert module.maintained(Path(".github/workflows/publish-aiogram-nav.yml"))
    assert module.maintained(Path("packages/aiogram-nav/native/pyproject.toml"))


@pytest.mark.parametrize("package", ["aiogram-cmds", "aiogram-nav", "aiogram-idle"])
def test_native_project_links_target_the_monorepo(package):
    project = tomllib.loads((ROOT / "packages" / package / "native/pyproject.toml").read_text())
    urls = project["project"]["urls"]
    assert urls["Repository"] == "https://github.com/ArmanAvanesyan/aiogram-kit"
    assert urls["Homepage"].endswith(f"/packages/{package}/native")
    assert urls["Issues"] == urls["Repository"] + "/issues"
    assert not any(module.OLD_URL.search(url) for url in urls.values())


def test_standalone_deploy_cannot_create_or_push_tags(tmp_path):
    script = ROOT / "packages/aiogram-cmds/tools/deploy.sh"
    result = subprocess.run(
        ["bash", str(script)], cwd=tmp_path, capture_output=True, text=True, check=False
    )
    assert result.returncode == 2
    assert "package-specific publishing workflows" in result.stderr
    assert not list(tmp_path.iterdir())


def test_dead_standalone_documentation_domain_is_rejected():
    assert module.OLD_DOCS.search("https://aiogram-cmds.dev/quickstart/")
    assert not module.OLD_DOCS.search("https://armanavanesyan.github.io/aiogram-kit/")
