"""Check real built wheel/sdist metadata, not just source TOML declarations."""

from importlib.metadata import metadata


def test_built_project_urls_use_the_monorepo():
    project = metadata("aiogram-nav-native")
    urls = dict(value.split(", ", 1) for value in project.get_all("Project-URL", []))
    assert urls["Repository"] == "https://github.com/ArmanAvanesyan/aiogram-kit"
    assert urls["Homepage"].endswith("/packages/aiogram-nav/native")
    assert urls["Issues"] == urls["Repository"] + "/issues"
