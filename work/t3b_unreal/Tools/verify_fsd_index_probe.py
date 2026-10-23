#!/usr/bin/env python3
"""Verify the FSD probe and its rejection boundaries."""
from __future__ import annotations

import argparse
import json
import shutil
import struct
import subprocess
import tempfile
from pathlib import Path


def run(exe: Path, source: Path):
    return subprocess.run([str(exe), str(source)], capture_output=True, text=True)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("source", type=Path)
    ap.add_argument("probe", type=Path)
    ap.add_argument("out", type=Path)
    args = ap.parse_args()
    good = run(args.probe, args.source)
    cases = {"good": {"exit_code": good.returncode, "stdout": good.stdout.strip()}}
    if good.returncode != 0:
        raise RuntimeError("valid 3rd.fsd rejected")
    with tempfile.TemporaryDirectory(prefix="t3b_fsd_verify_") as td:
        tmp = Path(td)
        original = args.source.read_bytes()
        mutations = {
            "bad_version": (0, struct.pack("<I", 2)),
            "bad_record_tag": (0x730, struct.pack("<I", 2)),
            "bad_sentinel": (0x1EF8, struct.pack("<I", 2)),
            "truncated": (len(original) - 1, b""),
        }
        for name, (offset, replacement) in mutations.items():
            data = bytearray(original)
            if name == "truncated":
                data = data[:offset]
            else:
                data[offset : offset + len(replacement)] = replacement
            path = tmp / f"{name}.fsd"
            path.write_bytes(data)
            result = run(args.probe, path)
            cases[name] = {"exit_code": result.returncode, "stderr": result.stderr.strip()}
            if result.returncode == 0:
                raise RuntimeError(f"negative FSD case accepted: {name}")
    report = {
        "schema": "t3b-fsd-index-probe-verification/v1",
        "status": "passed",
        "source": str(args.source),
        "probe": str(args.probe),
        "cases": cases,
        "scope": "format/header/extent rejection only; no second-field semantics inferred",
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
