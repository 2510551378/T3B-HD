#!/usr/bin/env python3
"""Verify synchronized action-pair probe and rejection cases."""
from __future__ import annotations

import argparse
import json
import subprocess
import tempfile
from pathlib import Path


def run(exe: Path, body: Path, weapon: Path):
    return subprocess.run([str(exe), str(body), str(weapon)], capture_output=True, text=True)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("probe", type=Path)
    ap.add_argument("body", type=Path)
    ap.add_argument("weapon", type=Path)
    ap.add_argument("mismatched_body", type=Path)
    ap.add_argument("out", type=Path)
    args = ap.parse_args()
    good = run(args.probe, args.body, args.weapon)
    if good.returncode != 0:
        raise RuntimeError("valid action pair rejected")
    cases = {"valid": {"exit_code": good.returncode, "stdout": good.stdout.strip()}}
    with tempfile.TemporaryDirectory(prefix="t3b_action_probe_") as td:
        truncated = Path(td) / "truncated_weapon.bin"
        truncated.write_bytes(args.weapon.read_bytes()[:-1])
        bad_truncated = run(args.probe, args.body, truncated)
        cases["truncated_weapon"] = {"exit_code": bad_truncated.returncode, "stderr": bad_truncated.stderr.strip()}
        if bad_truncated.returncode == 0:
            raise RuntimeError("truncated weapon accepted")
    bad_mismatch = run(args.probe, args.mismatched_body, args.weapon)
    cases["mismatched_body"] = {"exit_code": bad_mismatch.returncode, "stderr": bad_mismatch.stderr.strip()}
    if bad_mismatch.returncode == 0:
        raise RuntimeError("mismatched body accepted")
    report = {
        "schema": "t3b-action-clip-probe-verification/v1",
        "status": "passed",
        "probe": str(args.probe),
        "cases": cases,
        "scope": "synchronized sample-time and binary contract rejection; no action semantics inferred",
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
