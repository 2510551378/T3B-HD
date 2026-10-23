"""Resolve runtime CLUTs through draw-local TEXTURE0 matches."""
from __future__ import annotations
import argparse, json
from collections import defaultdict
from pathlib import Path


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("bindings", type=Path); ap.add_argument("pack_match", type=Path); ap.add_argument("out_json", type=Path); ap.add_argument("out_md", type=Path); a = ap.parse_args()
    b = json.loads(a.bindings.read_text(encoding="utf-8")); p = json.loads(a.pack_match.read_text(encoding="utf-8"))
    by_tex = defaultdict(list)
    for t in p["textures"]: by_tex[t["pixel_sha1"]].append(t)
    resolved = {}; unresolved = defaultdict(int)
    for d in b["draws"]:
        tex = d.get("texture0"); clut = d.get("clut")
        if not tex: continue
        targets = by_tex.get(tex["sha1"], [])
        if not targets: unresolved[tex["sha1"]] += 1; continue
        for t in targets:
            key = (d["action"], d["frame"], d["command"], clut["sha1"] if clut else None, t["pack"], t["texture_index"])
            resolved[key] = {"action": d["action"], "frame": d["frame"], "command": d["command"], "runtime_clut_sha1": clut["sha1"] if clut else None, "runtime_texture0_sha1": tex["sha1"], "pack": t["pack"], "texture_index": t["texture_index"], "width": t["width"], "height": t["height"], "bpp": t["bpp"], "vertices": d["vertices"], "vtype": d["vtype"], "weighted": d["weighted"], "bbox": d["bbox"], "uv_bbox": d["uv_bbox"]}
    rows = list(resolved.values()); result = {"schema": "runtime-material-resolution/v1", "resolved_draws": len(rows), "unique_runtime_cluts": len({r["runtime_clut_sha1"] for r in rows}), "unique_pack_textures": len({(r["pack"], r["texture_index"]) for r in rows}), "unresolved_texture0_signatures": dict(unresolved), "rows": rows}
    a.out_json.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    by_pack = defaultdict(int)
    for r in rows: by_pack[(r["pack"], r["texture_index"])] += 1
    lines = ["# Runtime CLUT resolved through pack TEXTURE0", "", f"- resolved draw/resource links: {len(rows)}", f"- unique runtime CLUT payloads: {result['unique_runtime_cluts']}", f"- unique pack textures: {result['unique_pack_textures']}", f"- unresolved TEXTURE0 signatures: {len(unresolved)}", "", "| pack | texture | size | bpp | linked draws | runtime CLUTs |", "|---|---:|---|---:|---:|---:|"]
    for (pack, idx), n in sorted(by_pack.items()):
        rs = [r for r in rows if r["pack"] == pack and r["texture_index"] == idx]
        lines.append(f"| {pack} | {idx} | {rs[0]['width']}x{rs[0]['height']} | {rs[0]['bpp']} | {n} | {len({r['runtime_clut_sha1'] for r in rs})} |")
    a.out_md.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"resolved_draws={len(rows)} unique_pack_textures={result['unique_pack_textures']} unresolved_texture0={len(unresolved)}")


if __name__ == "__main__": main()
