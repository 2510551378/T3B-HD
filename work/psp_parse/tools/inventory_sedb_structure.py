#!/usr/bin/env python3
"""Inventory SEDBSSCF structure without assigning gameplay semantics."""
from __future__ import annotations

import argparse
import json
import math
import struct
from pathlib import Path


def u32(data: bytes, off: int) -> int:
    return struct.unpack_from("<I", data, off)[0]


def finite_float(data: bytes, off: int):
    value = struct.unpack_from("<f", data, off)[0]
    return value if math.isfinite(value) else None


def inventory(path: Path):
    data = path.read_bytes()
    if len(data) < 0x38 or data[:8] != b"SEDBSSCF":
        raise ValueError(f"invalid SEDBSSCF header: {path}")
    declared = u32(data, 0x10)
    if declared != len(data):
        raise ValueError(f"declared length mismatch: {path}")
    count = u32(data, 0x34)
    offsets = []
    for i in range(count):
        off = 0x38 + i * 4
        if off + 4 > len(data):
            break
        value = u32(data, off)
        if value and value < len(data):
            offsets.append(value)
    unique = sorted(set(offsets))
    regions = []
    for i, start in enumerate(unique):
        end = next((x for x in unique[i + 1 :] if x > start), len(data))
        if end <= start:
            continue
        # Keep only a bounded numeric summary.  This is evidence of bytes that
        # look like finite floats, not a decoded record schema.
        numeric = 0
        candidate_triplets = 0
        minimum = math.inf
        maximum = -math.inf
        for p in range(start, end - 11, 4):
            values = [finite_float(data, p + 4 * j) for j in range(3)]
            if any(v is None for v in values):
                continue
            if all(-1000.0 <= v <= 1000.0 for v in values):
                numeric += 1
                minimum = min(minimum, *values)
                maximum = max(maximum, *values)
                if any(abs(v) > 1e-4 for v in values):
                    candidate_triplets += 1
        regions.append(
            {
                "start": start,
                "end": end,
                "bytes": end - start,
                "finite_float_triplets": numeric,
                "nonzero_float_triplets": candidate_triplets,
                "finite_float_min": None if numeric == 0 else minimum,
                "finite_float_max": None if numeric == 0 else maximum,
            }
        )
    return {
        "file": str(path),
        "bytes": len(data),
        "version": u32(data, 8),
        "format_word": u32(data, 0xC),
        "declared_bytes": declared,
        "header_word_30": u32(data, 0x30),
        "offset_table_count": count,
        "nonzero_offset_count": len(offsets),
        "unique_offsets": len(unique),
        "regions": regions,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("sedb_dir", type=Path)
    ap.add_argument("out_json", type=Path)
    ap.add_argument("out_md", type=Path)
    args = ap.parse_args()
    rows = [inventory(p) for p in sorted(args.sedb_dir.glob("*.bin"))]
    result = {
        "schema": "t3b-sedb-structure-inventory/v1",
        "status": "passed_with_limits",
        "files": len(rows),
        "total_bytes": sum(row["bytes"] for row in rows),
        "rows": rows,
        "interpretation": {
            "semantic_names_assigned": False,
            "collision_navigation_trigger_semantics": "unknown",
            "limits": [
                "Offset tables and finite-float windows are structural candidates only.",
                "No record stride, entity ID, room ID, collision shape, or script event is decoded here.",
                "This inventory does not replace runtime entity/scene correlation.",
            ],
        },
    }
    args.out_json.parent.mkdir(parents=True, exist_ok=True)
    args.out_json.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    lines = [
        "# SEDBSSCF structural inventory",
        "",
        f"- files: {len(rows)}",
        f"- total bytes: {result['total_bytes']:,}",
        "- semantics: unresolved; no collision/navigation/trigger label is assigned",
        "",
        "| file | bytes | version | offset count | nonzero offsets | regions |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for row in rows:
        lines.append(
            f"| {Path(row['file']).name} | {row['bytes']:,} | {row['version']} | "
            f"{row['offset_table_count']} | {row['nonzero_offset_count']} | {len(row['regions'])} |"
        )
    args.out_md.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps({k: result[k] for k in ("files", "total_bytes")}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
