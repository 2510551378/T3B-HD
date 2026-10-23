#!/usr/bin/env python3
"""Compare the recorded right-hand GE timeline with T3BSKN2 clip matrices.

This is a read-only provenance check.  It never changes runtime bindings: a
low error is only evidence that two captures may share a coordinate frame.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import struct
from pathlib import Path


def read_skin(path: Path):
    data = path.read_bytes()

    def u32(off: int) -> int:
        return struct.unpack_from("<I", data, off)[0]

    bones, packets, vertices, frames = u32(12), u32(16), u32(20), u32(24)
    off = 56 + bones * 4 + packets * 16 + vertices * 100
    times = list(struct.unpack_from(f"<{frames}f", data, off))
    off += frames * 4
    matrices = []
    for _ in range(frames):
        row = []
        for _ in range(bones):
            row.append(struct.unpack_from("<12f", data, off))
            off += 48
        matrices.append(row)
    if off != len(data):
        raise ValueError(f"unexpected trailing bytes in {path}: {len(data)-off}")
    return bones, times, matrices


def matrix_error(a, b):
    return math.sqrt(sum((x - y) ** 2 for x, y in zip(a, b)))


def translation_error(a, b):
    return math.sqrt(sum((a[i] - b[i]) ** 2 for i in (3, 7, 11)))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()
    root = args.root.resolve()
    timeline_path = root / "work/t3b_hd/assets/models/aya_true_right_hand_timeline.csv"
    clip_dir = root / "work/t3b_hd/assets/models/clips"
    rows = list(csv.DictReader(timeline_path.open(encoding="utf-8")))
    hand_rows = [
        [float(r[f"hand_m{i}{j}"]) for i in range(3) for j in range(4)]
        for r in rows
    ]
    mount_rows = [
        [float(r[f"mount_m{i}{j}"]) for i in range(3) for j in range(4)]
        for r in rows
    ]
    muzzle_rows = [
        [float(r[f"muzzle_m{i}{j}"]) for i in range(3) for j in range(4)]
        for r in rows
    ]

    clips = []
    for path in sorted(clip_dir.glob("aya_*.bin")):
        bones, times, matrices = read_skin(path)
        if bones <= 36:
            continue
        candidates = []
        for frame, matrix in enumerate(matrices):
            source = matrix[36]
            hand_err = min(matrix_error(source, target) for target in hand_rows)
            hand_trans = min(translation_error(source, target) for target in hand_rows)
            mount_err = min(matrix_error(source, target) for target in mount_rows)
            muzzle_err = min(matrix_error(source, target) for target in muzzle_rows)
            candidates.append(
                {
                    "frame": frame,
                    "time": times[frame],
                    "hand_matrix_l2": hand_err,
                    "hand_translation_l2": hand_trans,
                    "mount_matrix_l2": mount_err,
                    "muzzle_matrix_l2": muzzle_err,
                }
            )
        best = min(candidates, key=lambda x: x["hand_matrix_l2"])
        clips.append(
            {
                "clip": str(path.relative_to(root)).replace("\\", "/"),
                "bones": bones,
                "frames": len(times),
                "duration": times[-1],
                "best_source_bone_36": best,
                "direct_matrix_match_threshold_1e-3": best["hand_matrix_l2"] <= 1e-3,
            }
        )

    report = {
        "schema": "t3b-hand-timeline-clip-comparison/v1",
        "status": "passed_with_limits",
        "timeline": str(timeline_path.relative_to(root)).replace("\\", "/"),
        "timeline_rows": len(rows),
        "timeline_source_bone": int(rows[0]["source_bone_index"]),
        "timeline_draw": int(rows[0]["draw"]),
        "timeline_palette_slot": int(rows[0]["palette_slot"]),
        "candidate_clips": clips,
        "interpretation": {
            "direct_binding_allowed": any(
                c["direct_matrix_match_threshold_1e-3"] for c in clips
            ),
            "reason": "A direct matrix match is required before activating the separate GE timeline in the source-pair runtime.",
            "unknowns": [
                "The timeline may be in GE world/draw space while T3BSKN2 matrices are clip-local.",
                "Capture frame identity is not established by shared row counts or labels.",
                "This validator does not infer a socket when the direct comparison fails.",
            ],
        },
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
