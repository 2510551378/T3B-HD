#!/usr/bin/env python3
"""Audit the delta between two runtime CLUT/TEXTURE0 match reports."""
from __future__ import annotations

import argparse
import json
from pathlib import Path


def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def key(row):
    return row["type"], row["sha1"], row["bytes"]


def matched(row):
    return bool(row.get("exact_matches") or row.get("subsequence_matches"))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("old", type=Path)
    ap.add_argument("new", type=Path)
    ap.add_argument("out", type=Path)
    args = ap.parse_args()
    old = load(args.old)
    new = load(args.new)
    old_rows = {key(row): row for row in old["runtime"]}
    new_rows = {key(row): row for row in new["runtime"]}
    gained = []
    new_unmatched = []
    for k, row in sorted(new_rows.items()):
        previous = old_rows.get(k)
        if previous is None and not matched(row):
            new_unmatched.append({"type": row["type"], "sha1": row["sha1"], "bytes": row["bytes"], "sample": row["sample"]})
        if matched(row) and (previous is None or not matched(previous)):
            gained.append(
                {
                    "type": row["type"],
                    "sha1": row["sha1"],
                    "bytes": row["bytes"],
                    "sample": row["sample"],
                    "exact_matches": len(row.get("exact_matches", [])),
                    "subsequence_matches": len(row.get("subsequence_matches", [])),
                }
            )
    report = {
        "schema": "t3b-runtime-clut-match-delta/v1",
        "status": "passed_with_limits",
        "old_report": str(args.old),
        "new_report": str(args.new),
        "old_runtime_payloads": old["runtime_payloads"],
        "new_runtime_payloads": new["runtime_payloads"],
        "old_matched_runtime_payloads": old["matched_runtime_payloads"],
        "new_matched_runtime_payloads": new["matched_runtime_payloads"],
        "gained_rows": gained,
        "gained_count": len(gained),
        "new_unmatched_rows": new_unmatched,
        "new_unmatched_count": len(new_unmatched),
        "interpretation": {
            "new_inputs_are_read_only": True,
            "runtime_assets_replaced": False,
            "remaining_runtime_unmatched": sum(not matched(row) for row in new["runtime"]),
            "limits": [
                "A CLUT/TEXTURE0 byte match identifies a pack payload, not a semantic material name.",
                "Repeated pack records remain ambiguous without draw/object provenance.",
                "This report does not change the default M1 material binding.",
            ],
        },
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
