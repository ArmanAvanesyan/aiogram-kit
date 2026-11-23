"""Development dependency groups cannot bypass news for published package changes."""

import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("news_policy", ROOT / "tools/check_news.py")
assert spec is not None and spec.loader is not None
news = importlib.util.module_from_spec(spec)
spec.loader.exec_module(news)

BASE = """[build-system]
requires = ["hatchling>=1"]
[project]
name = "example"
version = "1.0.0"
dependencies = ["aiogram>=3,<4"]
[project.optional-dependencies]
redis = ["redis>=5"]
dev = ["pytest>=8"]
[dependency-groups]
dev = ["pytest-asyncio>=0.24"]
"""


def test_only_non_distributed_dependency_groups_are_exempt():
    updated = BASE.replace("pytest-asyncio>=0.24", "pytest-asyncio>=1.5")
    assert news.development_only_change(BASE, updated)
    path = "packages/example/pyproject.toml"
    assert news.missing_news([path], development_only_pyprojects={path}) == set()
    assert news.missing_news([path]) == {"example"}
    assert news.missing_news(
        [path, "packages/example/src/public.py"], development_only_pyprojects={path}
    ) == {"example"}


@pytest.mark.parametrize(
    "old,new",
    [
        ('version = "1.0.0"', 'version = "1.0.1"'),
        ("aiogram>=3,<4", "aiogram>=3.22,<4"),
        ("redis>=5", "redis>=6"),
        ("pytest>=8", "pytest>=9"),
        ("hatchling>=1", "hatchling>=2"),
        ('name = "example"', 'name = "renamed"'),
    ],
)
def test_published_metadata_always_requires_news(old, new):
    assert not news.development_only_change(BASE, BASE.replace(old, new))


@pytest.mark.parametrize(
    "before,after", [(None, BASE), (BASE, None), ("not toml", BASE), (BASE, "[broken")]
)
def test_missing_or_invalid_projects_fail_closed(before, after):
    assert not news.development_only_change(before, after)


def test_formatting_only_change_and_group_addition_are_non_public():
    assert news.development_only_change(BASE, "# comment\n" + BASE)
    assert news.development_only_change(BASE.split("[dependency-groups]")[0], BASE)


def test_cli_compares_committed_contents_and_keeps_source_guard(tmp_path):
    def git(*args):
        return subprocess.check_output(["git", *args], cwd=tmp_path, text=True).strip()

    git("init", "-q")
    git("config", "user.name", "News policy test")
    git("config", "user.email", "test@example.invalid")
    project = tmp_path / "packages/example/pyproject.toml"
    project.parent.mkdir(parents=True)
    project.write_text(BASE)
    git("add", ".")
    git("commit", "-qm", "baseline")
    base = git("rev-parse", "HEAD")
    project.write_text(BASE.replace("pytest-asyncio>=0.24", "pytest-asyncio>=1.5"))
    git("add", ".")
    git("commit", "-qm", "development dependency update")
    command = [sys.executable, str(ROOT / "tools/check_news.py"), "--base", base]
    result = subprocess.run(command, cwd=tmp_path, text=True, capture_output=True)
    assert result.returncode == 0, result.stderr
    source = project.parent / "src/public.py"
    source.parent.mkdir()
    source.write_text("public_change = True\n")
    git("add", ".")
    git("commit", "-qm", "public change")
    result = subprocess.run(command, cwd=tmp_path, text=True, capture_output=True)
    assert result.returncode != 0 and "example" in result.stderr
    fragment = project.parent / "CHANGES/1.misc.rst"
    fragment.parent.mkdir()
    fragment.write_text("Document the public change.\n")
    git("add", ".")
    git("commit", "-qm", "news")
    assert subprocess.run(command, cwd=tmp_path, capture_output=True).returncode == 0
