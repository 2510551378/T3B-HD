"""Merge runtime CLUT/TEXTURE0 bindings across PPSSPP pose captures."""
from __future__ import annotations
import argparse, hashlib, json, struct
from collections import Counter, defaultdict
from pathlib import Path
import numpy as np
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from extract_runtime_character import SCALE, layout, read_ppdmp, decode_uv


def digest(data): return hashlib.sha1(data).hexdigest()[:12]


def parse_dump(path: Path, action: str, frame: int):
    cmds, push = read_ppdmp(str(path)); cur = 0; clut = None; tex = None; rows = []
    for i, (typ, size, ptr) in enumerate(cmds):
        if ptr + size > len(push): continue
        payload = push[ptr:ptr + size]
        if typ == 1:
            for word in struct.unpack_from(f"<{size // 4}I", payload):
                if word >> 24 == 0x12: cur = word & 0xFFFFFF
        elif typ == 4: clut = {"command": i, "sha1": digest(payload), "bytes": size}
        elif typ == 0x10: tex = {"command": i, "sha1": digest(payload), "bytes": size}
        elif typ != 2 or not cur: continue
        try: stride, offs = layout(cur)
        except (KeyError, ValueError): continue
        if "pos" not in offs or stride <= 0: continue
        po, ps = offs["pos"]; count = (size - po) // stride
        if count < 3 or ptr + po + count * stride > len(push): continue
        if ps == 6: arr = np.frombuffer(payload[po:po + count * stride], dtype="<i2").reshape(count, stride // 2)[:, :3] * SCALE
        elif ps == 12: arr = np.frombuffer(payload[po:po + count * stride], dtype="<f4").reshape(count, stride // 4)[:, :3]
        else: continue
        row = {"action": action, "frame": frame, "command": i, "vtype": f"0x{cur:x}", "stride": stride, "vertices": count, "weighted": bool((cur >> 9) & 3), "bbox": {"min": arr.min(0).round(6).tolist(), "max": arr.max(0).round(6).tolist()}, "clut": clut, "texture0": tex}
        if "uv" in offs:
            uoff, _ = offs["uv"]; uv = np.asarray([decode_uv(payload[k * stride:(k + 1) * stride], uoff, cur & 3) for k in range(count)])
            row["uv_bbox"] = {"min": uv.min(0).round(6).tolist(), "max": uv.max(0).round(6).tolist()}
        else: row["uv_bbox"] = None
        rows.append(row)
    return rows


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("roots", nargs="+", help="pair/action directories containing frame_*.ppdmp"); ap.add_argument("--out-json", required=True); ap.add_argument("--out-md", required=True); a = ap.parse_args()
    rows = []
    for raw in a.roots:
        root = Path(raw); action = root.name
        for p in sorted(root.glob("frame_*.ppdmp")):
            frame = int(p.stem.split("_")[-1]); rows.extend(parse_dump(p, action, frame))
    signatures = defaultdict(list)
    for row in rows:
        c = row["clut"]; t = row["texture0"]; key = (c["sha1"] if c else None, t["sha1"] if t else None, row["vtype"], row["weighted"])
        signatures[key].append(row)
    materials = []
    for (clut, tex, vtype, weighted), refs in sorted(signatures.items(), key=lambda x: str(x[0])):
        materials.append({"clut_sha1": clut, "texture0_sha1": tex, "vtype": vtype, "weighted": weighted, "observations": len(refs), "actions": sorted({r["action"] for r in refs}), "commands": sorted({r["command"] for r in refs}), "vertices_min": min(r["vertices"] for r in refs), "vertices_max": max(r["vertices"] for r in refs), "bbox_examples": [r["bbox"] for r in refs[:3]], "uv_examples": [r["uv_bbox"] for r in refs[:3]]})
    result = {"schema": "aya-runtime-clut-binding/v1", "roots": a.roots, "draw_observations": len(rows), "unique_material_signatures": len(materials), "materials": materials, "draws": rows}
    Path(a.out_json).write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    lines = ["# Runtime CLUT/TEXTURE0 binding manifest", "", f"- draw observations: {len(rows)}", f"- unique signatures: {len(materials)}", "- Signature key = CLUT payload SHA-1 + TEXTURE0 payload SHA-1 + vertex type + weighted flag.", "", "| # | CLUT | TEXTURE0 | vtype | weighted | observations | actions | vertices |", "|---:|---|---|---|:---:|---:|---|---:|"]
    for i, m in enumerate(materials): lines.append(f"| {i} | `{m['clut_sha1']}` | `{m['texture0_sha1']}` | `{m['vtype']}` | {m['weighted']} | {m['observations']} | {', '.join(m['actions'])} | {m['vertices_min']}–{m['vertices_max']} |")
    Path(a.out_md).write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"draw_observations={len(rows)} unique_material_signatures={len(materials)}")


if __name__ == "__main__": main()
