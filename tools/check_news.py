"""Require package-specific news for public source or packaging changes."""

from __future__ import annotations

import argparse
import subprocess
from pathlib import PurePosixPath

try:
    import tomllib
except ModuleNotFoundError:  # Python 3.10 workspace checks
    import tomli as tomllib


def development_only_change(before: str | None, after: str | None) -> bool:
    """Exempt only non-distributed dependency groups or TOML-only formatting."""
    if before is None or after is None:
        return False
    try:
        original, updated = tomllib.loads(before), tomllib.loads(after)
    except tomllib.TOMLDecodeError:
        return False
    original.pop("dependency-groups", None)
    updated.pop("dependency-groups", None)
    return original == updated


def missing_news(
    paths: list[str], *, development_only_pyprojects: set[str] | None = None
) -> set[str]:
    affected = set()
    documented = set()
    for path in paths:
        parts = PurePosixPath(path).parts
        if len(parts) < 3 or parts[0] != "packages":
            continue
        package, relative = parts[1], parts[2:]
        if relative == ("pyproject.toml",) and path in (development_only_pyprojects or set()):
            continue
        if relative[0] in {"src", "pyproject.toml"} or relative[:2] in {
            ("native", "src"),
            ("native", "Cargo.toml"),
            ("native", "pyproject.toml"),
        }:
            affected.add(package)
        if (
            relative[0] == "CHANGELOG.md"
            or relative[0] == "CHANGES"
            and relative[-1] not in {"README.md", ".template.rst.jinja2"}
        ):
            documented.add(package)
    return affected - documented


def git_blob(ref: str, path: str) -> str | None:
    result = subprocess.run(
        ["git", "show", f"{ref}:{path}"], text=True, capture_output=True, check=False
    )
    return result.stdout if result.returncode == 0 else None


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", required=True)
    args = parser.parse_args()
    paths = subprocess.check_output(
        ["git", "diff", "--name-only", args.base, "HEAD"], text=True
    ).splitlines()
    development_only = {
        path
        for path in paths
        if path.startswith("packages/")
        and path.endswith("/pyproject.toml")
        and development_only_change(git_blob(args.base, path), git_blob("HEAD", path))
    }
    missing = missing_news(paths, development_only_pyprojects=development_only)
    if missing:
        raise SystemExit("Missing package changelog/fragment: " + ", ".join(sorted(missing)))
    print("Package-specific changelog coverage verified")
