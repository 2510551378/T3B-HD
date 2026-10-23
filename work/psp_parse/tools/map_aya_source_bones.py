"""Cross-map Aya's 44 source records to weighted GE draws.

The source record payload is written at 0x08b5251c and the same-frame GE
weighted draw is recovered from PPSSPP's recorder.  A draw whose 3x4 float24
payload matches a source record is assigned to that source index.  This is a
correlation report; unmatched draws are retained rather than guessed.
"""
from __future__ import annotations

import argparse
import json
import math
from collections import Counter, defaultdict
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from extract_ge_timeline import read_ppdmp, register_state, human_weighted, float24
from replay_ge_draws import iter_ge_draws


def rmse(a, b):
    return math.sqrt(sum((x - y) ** 2 for x, y in zip(a, b)) / 12.0)


def all_weighted_draws(path: Path, include_rejected: bool = False, include_all: bool = False):
    """Return weighted draws, or every vertex draw when include_all is set."""
    cmds, push = read_ppdmp(str(path))
    out = []
    for draw in iter_ge_draws(cmds, push):
        i, size, ptr, vtype = draw['draw'], draw['size'], draw['pointer'], draw['vtype']
        mats = [{'slot': slot * 12, 'values': [float24(w) for w in words]}
                for slot, words in draw['palette_payloads'].items()]
        info = human_weighted(push, size, ptr, vtype)
        if info is None:
            if (not include_rejected and not include_all) or not vtype:
                continue
            info = {"vertices": 0, "bbox": None, "vtype": int(vtype)}
        elif include_all and info is not None:
            info = dict(info)
        for mat in mats:
            row = dict(info)
            row.update({"draw": i, "slot": int(mat["slot"]), "matrix": mat["values"]})
            out.append(row)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("pair_manifest", type=Path)
    ap.add_argument("out_json", type=Path)
    ap.add_argument("out_md", type=Path)
    ap.add_argument("--threshold", type=float, default=0.002)
    ap.add_argument("--all-weighted", action="store_true", help="retain weighted blocks rejected by the human-size filter")
    ap.add_argument("--all-draws", action="store_true", help="include non-weighted vertex draws")
    args = ap.parse_args()

    pair = json.loads(args.pair_manifest.read_text(encoding="utf-8"))
    pair_dir = args.pair_manifest.parent
    by_key = defaultdict(list)
    unmatched = []
    frame_rows = []
    skipped_no_dump_frames = []

    for frame in pair["frames"]:
        if not frame.get("dump"):
            skipped_no_dump_frames.append(int(frame.get("frame", len(frame_rows))))
            continue
        dump_path = Path(frame["dump"]["file"])
        # Newer manifests retain an absolute dump path.  Keep the historical
        # same-directory fallback for older portable manifests.
        ppdmp = dump_path if dump_path.is_file() else pair_dir / dump_path.name
        if not ppdmp.is_file():
            raise FileNotFoundError(f"dump file not found: {frame['dump']['file']}")
        ge_bones = all_weighted_draws(ppdmp, args.all_weighted, args.all_draws)
        source = {}
        for rec in frame["records"]:
            source[int(rec["index"])] = [float24(int(x)) for x in rec["matrix"][:12]]

        draws = []
        for item in sorted(ge_bones, key=lambda x: (x["draw"], x["slot"])):
            ge = list(map(float, item["matrix"]))
            candidates = [(rmse(ge, src), idx) for idx, src in source.items()]
            best_rmse, best_idx = min(candidates)
            row = {
                "frame": int(frame["frame"]),
                "ge_slot": int(item["slot"]),
                "draw": int(item["draw"]),
                "vertices": int(item["vertices"]),
                "bbox": item["bbox"],
                "vtype": int(item["vtype"]),
                "source_index": best_idx if best_rmse <= args.threshold else None,
                "match_rmse": best_rmse,
            }
            draws.append(row)
            if row["source_index"] is None:
                unmatched.append(row)
            else:
                key = (row["source_index"], row["ge_slot"], row["draw"])
                by_key[key].append(row)
        frame_rows.append({"frame": int(frame["frame"]), "draws": draws})
        print(f"frame {frame['frame']:02d}: weighted_draws={len(draws)} matched={len(draws)-sum(r['source_index'] is None for r in draws)}")

    mappings = []
    for (source_index, slot, draw), rows in sorted(by_key.items()):
        boxes = [r["bbox"] for r in rows]
        vertices = Counter(r["vertices"] for r in rows)
        mappings.append({
            "source_index": source_index,
            "ge_slot": slot,
            "draw": draw,
            "frames": len(rows),
            "frame_ids": [r["frame"] for r in rows],
            "vertices_mode": vertices.most_common(1)[0][0],
            "bbox_first": boxes[0],
            "match_rmse_max": max(r["match_rmse"] for r in rows),
        })

    result = {
        "schema": "aya-source-bone-ge-draw-map/v1",
        "source": "AYA_BONE_GE_PAIRS + extract_ge_timeline.float24",
        "source_bone_count": 44,
        "frames": len(frame_rows),
        "manifest_frames": len(pair["frames"]),
        "skipped_no_dump_frames": skipped_no_dump_frames,
        "threshold": args.threshold,
        "mappings": mappings,
        "unmatched_count": len(unmatched),
        "unmatched": unmatched,
        "frame_rows": frame_rows,
    }
    args.out_json.parent.mkdir(parents=True, exist_ok=True)
    args.out_json.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

    lines = [
        "# Aya 44 source records ↔ weighted GE draw cross-map", "",
        f"- frames: {len(frame_rows)}; matched draw instances: {sum(len(v) for v in by_key.values())}; unique mappings: {len(mappings)}",
        f"- threshold: RMSE <= {args.threshold:g}; unmatched draw instances: {len(unmatched)}",
        "- A mapping is reported only when the same-frame 3x4 float24 payload matches a source record; unmatched rows remain explicit.",
        "", "| source index | GE slot | draw | frames | vertices | max RMSE | bbox |"
    ]
    lines.append("|---:|---:|---:|---:|---:|---:|---|")
    for m in mappings:
        b = m["bbox_first"]
        bbox_text = "unknown" if b is None else f"{b[0]} .. {b[1]}"
        lines.append(f"| {m['source_index']} | {m['ge_slot']} | {m['draw']} | {m['frames']} | {m['vertices_mode']} | {m['match_rmse_max']:.8f} | {bbox_text} |")
    lines += ["", "## Coverage by source index", ""]
    covered = Counter(m["source_index"] for m in mappings)
    for i in range(44):
        lines.append(f"- source {i:02d}: {covered.get(i, 0)} unique GE mapping(s)")
    args.out_md.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"wrote {args.out_json}")
    print(f"wrote {args.out_md}")


if __name__ == "__main__":
    main()
