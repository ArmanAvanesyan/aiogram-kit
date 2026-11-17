"""Main covers the complete matrix; PR documentation builds cannot deploy."""

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]


def workflow(name):
    data = yaml.safe_load((ROOT / ".github/workflows" / name).read_text())
    return data, data.get(True, data.get("on"))


def test_shared_tool_checks_run_on_every_main_push():
    _, triggers = workflow("optimization-tools.yml")
    assert triggers["push"] == {"branches": ["main"]}


def test_docs_deploy_main_automatically_and_keep_prs_read_only():
    data, triggers = workflow("docs.yml")
    assert triggers["push"] == {"branches": ["main"]}
    assert "pull_request" in triggers and "workflow_dispatch" in triggers
    deploy = data["jobs"]["deploy"]
    assert "github.ref == 'refs/heads/main'" in deploy["if"]
    assert "github.event_name != 'pull_request'" in deploy["if"]
    assert deploy["permissions"] == {"pages": "write", "id-token": "write"}
    assert data["permissions"] == {"contents": "read"}
    assert data["concurrency"]["cancel-in-progress"] is True


def test_workspace_checks_cover_minimum_and_latest_python():
    data, _ = workflow("workspace.yml")
    assert set(data["jobs"]["verify"]["strategy"]["matrix"]["python"]) >= {"3.10", "3.12", "3.14"}
