"""Isolated 0.3.3 SDK source/minimum/latest, native-only and paired artifact installs."""

import argparse
import concurrent.futures
import hashlib
import json
import platform
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REPORT = Path(__file__).parent


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifacts", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--profiles",
        nargs="+",
        default=["sdk-wheel", "sdk-minimum", "sdk-source", "native-only", "paired"],
    )
    parser.add_argument("--uv", default="uv")
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    allowed = {"sdk-wheel", "sdk-minimum", "sdk-source", "native-only", "paired"}
    assert set(args.profiles) <= allowed
    assert platform.system() == "Darwin"
    architecture = "arm64" if platform.machine() == "arm64" else "x86_64"

    def check(selection):
        short, profile = selection
        package = "aiogram-" + short
        label = short + "-" + profile
        files = []
        if profile != "native-only":
            directory = args.artifacts.resolve() / package
            files.append(
                directory
                / (
                    package.replace("-", "_")
                    + "-0.3.3"
                    + (".tar.gz" if profile == "sdk-source" else "-py3-none-any.whl")
                )
            )
        if profile in {"native-only", "paired"}:
            directory = args.artifacts.resolve() / (package + "-native")
            files.append(next(directory.glob(f"*macosx*_{architecture}.whl")))
        # Hash inputs independently of the environment and preserve them with each result.
        inputs = [
            {"filename": p.name, "sha256": hashlib.sha256(p.read_bytes()).hexdigest()}
            for p in files
        ]
        with tempfile.TemporaryDirectory(prefix="aiogram-033-" + label + "-") as temporary:
            scratch = Path(temporary)
            environment = scratch / "env"
            python = environment / "bin/python"
            requirements = list(map(str, files))
            if profile == "sdk-minimum":
                requirements.append("aiogram==" + ("3.0.0" if short == "cmds" else "3.22.0"))
            commands = [
                [
                    args.uv,
                    "venv",
                    "--python",
                    "3.10" if profile == "sdk-minimum" else "3.12",
                    str(environment),
                ],
                [args.uv, "pip", "install", "--python", str(python), *requirements],
                [str(python), "-I", str(REPORT / "smoke_installs.py"), short, profile, str(ROOT)],
                [args.uv, "pip", "check", "--python", str(python)],
            ]
            with (args.output / (label + ".log")).open("w") as stream:
                for command in commands:
                    subprocess.run(
                        command, cwd=scratch, stdout=stream, stderr=subprocess.STDOUT, check=True
                    )
        row = {"package": package, "profile": profile, "inputs": inputs, "result": "pass"}
        (args.output / (label + ".json")).write_text(json.dumps(row, indent=2) + "\n")
        print(label, "PASS", flush=True)
        return row

    selection = [(short, profile) for short in ("cmds", "nav", "idle") for profile in args.profiles]
    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as pool:
        rows = list(pool.map(check, selection))
    (args.output / "results.json").write_text(json.dumps(rows, indent=2) + "\n")


if __name__ == "__main__":
    main()
