"""Asset-free syntax and existing source-data checks; no Unreal runtime claim."""
from __future__ import annotations

import argparse
import ast
import os
from pathlib import Path
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOTS = (
    ROOT / "scripts",
    ROOT / "work/psp_parse/tools",
    ROOT / "work/psp_parse/archive",
    ROOT / "work/t3b_unreal/Tools",
)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--compiler", default="g++")
    args = parser.parse_args()
    paths = sorted(p for root in SOURCE_ROOTS for p in root.rglob("*.py"))
    for path in paths:
        ast.parse(path.read_text(encoding="utf-8-sig"), filename=str(path))
    print(f"python_syntax_files={len(paths)}", flush=True)
    compiler = shutil.which(args.compiler)
    if compiler is None:
        raise SystemExit(f"C++17 compiler not found: {args.compiler}")
    output = ROOT / "build/source_check"
    output.mkdir(parents=True, exist_ok=True)
    executable = output / ("source_data_tests.exe" if os.name == "nt" else "source_data_tests")
    project = ROOT / "work/t3b_unreal"
    subprocess.run([
        compiler, "-std=c++17", "-O2", "-Wall", "-Wextra", "-Werror",
        "-ffp-contract=off", str(project / "Tools/source_data_tests.cpp"),
        str(project / "Source/T3BRemake/Private/T3BSourceData.cpp"),
        "-o", str(executable),
    ], check=True)
    subprocess.run([str(executable)], check=True)
    print("source_only_check=passed; UE/runtime/assets not exercised", flush=True)


if __name__ == "__main__":
    main()
