"""A successful unrelated workflow cannot qualify a release platform set."""

import importlib.util
from pathlib import Path

import pytest


@pytest.fixture
def collector(monkeypatch):
    tools = Path(__file__).resolve().parents[1]
    monkeypatch.syspath_prepend(str(tools))
    spec = importlib.util.spec_from_file_location(
        "collect_release", tools / "collect_release_artifacts.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_accepts_only_complete_matching_native_platform_workflow(collector):
    commit = "a" * 40
    run = {
        "head_sha": commit,
        "status": "completed",
        "conclusion": "success",
        "path": ".github/workflows/aiogram-nav-native-ci.yml",
    }
    collector.validate_run("aiogram-nav", run, commit)
    for change in (
        {"head_sha": "b" * 40},
        {"status": "in_progress"},
        {"conclusion": "failure"},
        {"path": ".github/workflows/aiogram-nav-ci.yml"},
        {"path": ".github/workflows/aiogram-idle-native-ci.yml"},
    ):
        with pytest.raises(ValueError, match="matching platform workflow"):
            collector.validate_run("aiogram-nav", {**run, **change}, commit)
