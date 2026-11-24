"""Reject active links to retired repositories without rewriting preserved evidence."""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RETIRED = (
    "aiogram-idle",
    "aiogram-nav",
    "aiogram-cmds",
    "aiogram-coordination",
    "aiogram-kit-legacy",
)
OLD_URL = re.compile(
    r"https?://(?:github\.com/ArmanAvanesyan|armanavanesyan\.github\.io)/(?:"
    + "|".join(RETIRED)
    + r")(?=[/\s.?#)\"'`]|$)",
    re.IGNORECASE,
)
OLD_DOCS = re.compile(r"https?://(?:www\.)?aiogram-cmds\.dev(?=[/\s?#)\"'`]|$)", re.IGNORECASE)


def maintained(path: Path) -> bool:
    parts = path.parts
    if path.suffix not in {".md", ".toml", ".yml", ".yaml", ".sh", ".ps1"}:
        return False
    if not parts or "reports" in parts:
        return False
    if parts[0] == "docs" or parts[:2] == (".github", "workflows"):
        return True
    if len(parts) == 1:
        return True
    if parts[0] != "packages" or len(parts) < 3:
        return False
    if parts[1] == "aiogram-kit" and (parts[2] in {"docs", "mkdocs.yml"}):
        # Original Kit snapshots are byte-pinned preservation inputs, not the site source.
        return False
    if len(parts) == 3:
        return True
    if parts[2] == "docs":
        return True
    return len(parts) == 4 and parts[2] in {"native", "tools"}


def violations(root: Path = ROOT) -> list[str]:
    paths = subprocess.check_output(["git", "ls-files", "-z"], cwd=root).decode().split("\0")
    found = []
    for name in paths:
        path = Path(name)
        if not maintained(path) or not (root / path).is_file():
            continue
        for number, line in enumerate((root / path).read_text().splitlines(), 1):
            if OLD_URL.search(line) or OLD_DOCS.search(line):
                found.append(f"{name}:{number}: {line.strip()}")
    return found


if __name__ == "__main__":
    failures = violations()
    if failures:
        raise SystemExit("Retired repository links in maintained files:\n" + "\n".join(failures))
    print("No maintained references require the retired repositories")
