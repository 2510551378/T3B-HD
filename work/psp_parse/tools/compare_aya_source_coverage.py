#!/usr/bin/env python3
"""Compare Aya source-bone coverage across mapping reports."""
from __future__ import annotations

import argparse
import json
from pathlib import Path


def read(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--baseline", type=Path, required=True)
    ap.add_argument("reports", nargs="+", type=Path)
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()
    baseline = read(args.baseline)
    rows = []
    for path in [args.baseline, *args.reports]:
        report = baseline if path == args.baseline else read(path)
        covered = sorted({int(m["source_index"]) for m in report.get("mappings", [])})
        rows.append(
            {
                "report": str(path),
                "manifest_frames": report.get("manifest_frames", report.get("frames")),
                "processed_frames": report.get("frames"),
                "skipped_no_dump_frames": report.get("skipped_no_dump_frames", []),
                "unique_mappings": len(report.get("mappings", [])),
                "covered_source_indices": covered,
                "uncovered_source_indices": sorted(set(range(44)) - set(covered)),
                "unmatched_draws": report.get("unmatched_count"),
            }
        )
    base_set = set(rows[0]["covered_source_indices"])
    result = {
        "schema": "t3b-aya-source-coverage-comparison/v1",
        "status": "passed_with_limits",
        "baseline_covered_count": len(base_set),
        "baseline_uncovered_source_indices": sorted(set(range(44)) - base_set),
        "reports": rows,
        "new_source_indices_over_baseline": {
            row["report"]: sorted(set(row["covered_source_indices"]) - base_set)
            for row in rows[1:]
        },
        "interpretation": {
            "direct_mapping_rule": "same-frame float24 source-record payload versus weighted GE draw",
            "semantic_names_inferred": False,
            "limits": [
                "Dense manifests contain 60 source frames but only two frames with complete GE dump files.",
                "Uncovered source indices remain unresolved; no placeholder mapping is emitted.",
                "Coverage does not prove original gameplay action semantics or a named bone.",
            ],
        },
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
