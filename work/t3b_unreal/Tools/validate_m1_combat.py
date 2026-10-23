"""Run the actual UE M1 smoke and reject stale, partial or failed reports."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import time


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--engine", type=Path, default=Path("C:/Program Files/Epic Games/UE_5.8"))
    parser.add_argument("--project", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--rhi", choices=("nullrhi", "d3d11"), default="nullrhi")
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    project = args.project.resolve()
    probe = project.parent / "Saved/Combat/m1_combat_probe.json"
    previous = json.loads(probe.read_text(encoding="utf-8")) if probe.exists() else {}
    started = time.time()
    command = [str(args.engine / "Engine/Binaries/Win64/UnrealEditor-Cmd.exe"), str(project),
               "/Game/T3B/Maps/M1_SourceReplay", "-game", "-" + args.rhi, "-unattended", "-nosound",
               "-T3BCombatSmoke", "-T3BCombatSmokeExit", "-stdout", "-FullStdOutLogOutput",
               "-abslog=" + str((args.output / "runtime.log").resolve())]
    with (args.output / "stdout.log").open("w", encoding="utf-8") as log:
        result = subprocess.run(command, stdout=log, stderr=subprocess.STDOUT, timeout=180)
    report = json.loads(probe.read_text(encoding="utf-8"))
    if (result.returncode or probe.stat().st_mtime < started or not report.get("run_id")
            or report.get("run_id") == previous.get("run_id")
            or not report.get("smoke_complete") or not report.get("passed")
            or not report.get("checks") or not all(row["passed"] for row in report["checks"])):
        raise SystemExit("Actual UE combat acceptance failed; inspect runtime log/probe")
    (args.output / "combat_probe.json").write_bytes(probe.read_bytes())
    module = project.parent / "Binaries/Win64/UnrealEditor-T3BRemake.dll"
    summary = {"schema": "t3b-actual-ue-combat-validation/v1", "rhi": args.rhi,
               "exit_code": result.returncode, "actual_runtime": True, "passed": True,
               "run_id": report["run_id"], "checks": len(report["checks"]),
               "module_sha256": hashlib.sha256(module.read_bytes()).hexdigest()}
    (args.output / "validation.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
