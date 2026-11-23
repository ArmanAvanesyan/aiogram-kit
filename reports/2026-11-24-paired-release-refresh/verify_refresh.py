"""Recheck refreshed SDK artifacts without rebuilding or resampling native candidates."""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))
from verify_release import verify


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run(arguments: list[str], cwd: Path) -> str:
    result = subprocess.run(arguments, cwd=cwd, text=True, capture_output=True, check=False)
    if result.returncode:
        raise RuntimeError(f"{arguments}:\n{result.stdout}\n{result.stderr}")
    return result.stdout


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifacts", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--uv", default="uv")
    args = parser.parse_args()
    baseline = ROOT / "reports/2026-11-18-paired-release"
    old = json.loads((baseline / "final-artifact-index.json").read_text())
    inventory = json.loads((baseline / "ci-artifact-manifest.json").read_text())["packages"]
    for distribution in old["distributions"]:
        directory = Path(distribution["directory"])
        assert digest(directory / "SHA256SUMS") == distribution["manifest_sha256"]
        for artifact in distribution["files"]:
            assert digest(directory / artifact["filename"]) == artifact["sha256"]

    rows = []
    loaders = {
        "sentinel": "from aiogram_sentinel.native import load_native; load_native()",
        "cmds": 'from aiogram_cmds.engines import native_engine; native_engine("rust")',
        "nav": 'from aiogram_nav.engine import require_engine; require_engine("rust")',
        "idle": 'from aiogram_idle.engines import require_engine; require_engine("rust")',
    }
    with tempfile.TemporaryDirectory(prefix="paired-refresh-") as temporary:
        scratch = Path(temporary)
        for short in ("sentinel", "cmds", "nav", "idle"):
            name = "aiogram-" + short
            module = name.replace("-", "_")
            version = "1.3.2" if short == "sentinel" else "0.3.2"
            directory = args.artifacts.resolve() / name
            wheel = directory / f"{module}-{version}-py3-none-any.whl"
            source = directory / f"{module}-{version}.tar.gz"
            files = [{"filename": p.name, "sha256": digest(p)} for p in (wheel, source)]
            manifest = directory / "SHA256SUMS"
            manifest.write_text("".join(f"{r['sha256']}  {r['filename']}\n" for r in files))
            verify(ROOT, name, f"{name}-v{version}", directory, digest(manifest))
            previous = next(r for r in old["distributions"] if r["distribution"] == name)
            previous_wheel = Path(previous["directory"]) / wheel.name
            with zipfile.ZipFile(wheel) as current, zipfile.ZipFile(previous_wheel) as earlier:
                assert current.testzip() is None
                payload_equal = sorted(current.namelist()) == sorted(earlier.namelist()) and all(
                    current.read(filename) == earlier.read(filename)
                    for filename in current.namelist()
                )
            changed = [
                filename
                for filename, expected in inventory[name]["source_files"].items()
                if digest(ROOT / filename) != expected
            ]
            native = next(r for r in old["distributions"] if r["distribution"] == name + "-native")
            if platform.system() != "Darwin":
                raise RuntimeError("This retained shipping-wheel install probe requires macOS")
            architecture = "arm64" if platform.machine() == "arm64" else "x86_64"
            native_wheel = next(Path(native["directory"]).glob(f"*macosx*_{architecture}.whl"))
            native_module = (
                "_" + module + "_native" if short in {"sentinel", "cmds"} else module + "_native"
            )
            profiles = []
            minimum = "3.0.0" if short in {"sentinel", "cmds"} else "3.22.0"
            selections = (
                ("wheel-latest", [str(wheel), "aiogram>=3,<4"]),
                ("wheel-minimum", [str(wheel), "aiogram==" + minimum]),
                ("source", [str(source)]),
                ("native-only", [str(native_wheel)]),
                ("paired", [str(wheel), str(native_wheel)]),
            )
            for profile, artifacts in selections:
                environment = scratch / (name + "-" + profile)
                # Match minimum-aiogram CI: aiogram 3.0's aiohttp predates Python 3.12.
                python_version = "3.10" if profile == "wheel-minimum" else "3.12"
                run([args.uv, "venv", "--python", python_version, str(environment)], scratch)
                python = str(environment / "bin/python")
                run([args.uv, "pip", "install", "--python", python, *artifacts], scratch)
                run([args.uv, "pip", "check", "--python", python], scratch)
                code = "import importlib, importlib.util as u, importlib.metadata as m\n"
                code += 'assert u.find_spec("redis") is None\n'
                if profile == "native-only":
                    code += f"assert u.find_spec({module!r}) is None\n"
                    code += f"importlib.import_module({native_module!r})\n"
                    code += f"assert m.version({name + '-native'!r}) == {version!r}\n"
                    code += f"assert not m.requires({name + '-native'!r})\n"
                else:
                    code += f"sdk=importlib.import_module({module!r})\n"
                    code += f"assert sdk.__version__ == m.version({name!r}) == {version!r}\n"
                    code += "assert '/site-packages/' in sdk.__file__\n"
                    for peer in ("aiogram_sentinel", "aiogram_cmds", "aiogram_nav", "aiogram_idle"):
                        if peer != module:
                            code += f"assert u.find_spec({peer!r}) is None\n"
                    if profile == "paired":
                        code += loaders[short] + "\n"
                    else:
                        code += f"assert u.find_spec({native_module!r}) is None\n"
                        code += "try:\n " + loaders[short] + "\n"
                        code += (
                            "except Exception as error:\n assert 'native' in str(error).lower()\n"
                        )
                        code += (
                            "else:\n raise AssertionError('Missing companion must be rejected')\n"
                        )
                code += "print(m.version('aiogram') if u.find_spec('aiogram') else 'native-only')\n"
                installed = run([python, "-I", "-c", code], scratch).strip()
                profiles.append({"profile": profile, "result": "pass", "aiogram": installed})
                print(name, profile, "PASS", flush=True)
            rows.append(
                {
                    "sdk": name,
                    "version": version,
                    "directory": str(directory),
                    "manifest_sha256": digest(manifest),
                    "files": files,
                    "wheel_bytes_unchanged": digest(wheel) == digest(previous_wheel),
                    "wheel_payload_unchanged": payload_equal,
                    "changed_qualified_source_files": changed,
                    "profiles": profiles,
                }
            )
    args.output.write_text(
        json.dumps(
            {
                "source_commit": run(["git", "rev-parse", "HEAD"], ROOT).strip(),
                "publishing_performed": False,
                "historical_artifacts_verified": old["artifact_count"],
                "packages": rows,
            },
            indent=2,
        )
        + "\n"
    )


if __name__ == "__main__":
    main()
