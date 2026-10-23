#!/usr/bin/env python3
"""Inventory the verified structural pattern of 3rd.fsd."""
from __future__ import annotations

import argparse
import collections
import json
import struct
from pathlib import Path


def u32(data: bytes, off: int) -> int:
    return struct.unpack_from("<I", data, off)[0]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("input", type=Path)
    ap.add_argument("out_json", type=Path)
    ap.add_argument("out_md", type=Path)
    args = ap.parse_args()
    data = args.input.read_bytes()
    header = [u32(data, off) for off in range(0, min(0x80, len(data)), 4)]
    declared_records = u32(data, 8)
    record_start = 0x730
    complete = []
    for i in range(declared_records):
        off = record_start + i * 8
        if off + 8 > len(data):
            break
        complete.append({"index": i, "offset": off, "tag": u32(data, off), "value": u32(data, off + 4)})
    sentinel_offset = record_start + declared_records * 8
    sentinel = u32(data, sentinel_offset) if sentinel_offset + 4 <= len(data) else None
    values = [row["value"] for row in complete]
    deltas = [values[i + 1] - values[i] for i in range(len(values) - 1)]
    result = {
        "schema": "t3b-3rd-fsd-structure-inventory/v1",
        "status": "passed_with_limits",
        "file": str(args.input),
        "bytes": len(data),
        "header_u32_le": header,
        "declared_record_count": declared_records,
        "record_start": record_start,
        "record_stride": 8,
        "complete_records": len(complete),
        "all_record_tags_are_one": all(row["tag"] == 1 for row in complete),
        "sentinel_offset": sentinel_offset,
        "sentinel_u32": sentinel,
        "second_field": {
            "min": min(values) if values else None,
            "max": max(values) if values else None,
            "unique": len(set(values)),
            "monotonic_non_decreasing": all(d >= 0 for d in deltas),
            "low_values_below_0x10000": sum(v < 0x10000 for v in values),
            "delta_histogram_top": collections.Counter(deltas).most_common(12),
        },
        "interpretation": {
            "record_semantics": "unknown",
            "second_field_is_pack_offset": False,
            "second_field_is_entity_id": False,
            "limits": [
                "The repeated tag/stride and sentinel are structural observations only.",
                "The second u32 field is not assigned a semantic name or decoded encoding.",
                "No package, room, entity, collision, or script linkage is inferred.",
            ],
        },
    }
    args.out_json.parent.mkdir(parents=True, exist_ok=True)
    args.out_json.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    lines = [
        "# 3rd.fsd structural inventory",
        "",
        f"- bytes: {len(data):,}",
        f"- declared records: {declared_records}",
        f"- complete records at `0x{record_start:x}`: {len(complete)} × 8 bytes",
        f"- all record tags equal one: {result['all_record_tags_are_one']}",
        f"- trailing sentinel at `0x{sentinel_offset:x}`: `{sentinel}`",
        "- second field semantics: unresolved",
    ]
    args.out_md.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps({k: result[k] for k in ("bytes", "declared_record_count", "complete_records", "sentinel_u32")}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
