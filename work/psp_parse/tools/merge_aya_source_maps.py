"""Merge source→GE maps from multiple PPSSPP pose/action captures."""
from __future__ import annotations
import argparse, json
from collections import defaultdict
from pathlib import Path


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("inputs", nargs="+"); ap.add_argument("--out-json", required=True); ap.add_argument("--out-md", required=True); a = ap.parse_args()
    mappings = {}
    covered = set(); total_instances = 0; actions = []
    for raw in a.inputs:
        p = Path(raw); d = json.loads(p.read_text(encoding="utf-8")); action = p.parent.name if p.parent.name != "out" else p.stem
        actions.append(action); total_instances += sum(len(x["draws"]) for x in d.get("frame_rows", []))
        for m in d.get("mappings", []):
            key = (m["source_index"], m["ge_slot"], m["draw"]); covered.add(m["source_index"])
            row = mappings.setdefault(key, {**m, "actions": []})
            if action not in row["actions"]: row["actions"].append(action)
    rows = sorted(mappings.values(), key=lambda x: (x["source_index"], x["ge_slot"], x["draw"]))
    result = {"schema": "aya-source-bone-ge-draw-merged/v1", "inputs": a.inputs, "actions": actions, "source_bone_count": 44, "instances": total_instances, "unique_mappings": len(rows), "covered_source_indices": sorted(covered), "uncovered_source_indices": sorted(set(range(44)) - covered), "mappings": rows}
    Path(a.out_json).write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    lines = ["# Aya source bone ↔ GE draw merged map", "", f"- action captures: {', '.join(actions)}", f"- weighted draw instances: {total_instances}", f"- unique mappings: {len(rows)}", f"- covered source indices: {len(covered)}/44", f"- uncovered source indices: {sorted(set(range(44)) - covered)}", "", "| source | GE slot | draw | actions | frames | vertices | max RMSE |", "|---:|---:|---:|---|---:|---:|---:|"]
    for m in rows: lines.append(f"| {m['source_index']} | {m['ge_slot']} | {m['draw']} | {', '.join(m['actions'])} | {m['frames']} | {m['vertices_mode']} | {m['match_rmse_max']:.8f} |")
    Path(a.out_md).write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"covered={len(covered)}/44 unique_mappings={len(rows)} uncovered={sorted(set(range(44)) - covered)}")


if __name__ == "__main__": main()
