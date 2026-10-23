"""Audit active skinning influences, rather than every retained GE palette slot.

Byte-identical float24 payloads are correlation evidence. They do not prove
an anatomical name, a skeleton parent, or that two sampled passes are atomic.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import math
import struct
from collections import defaultdict
from pathlib import Path
from extract_ge_timeline import read_ppdmp
from extract_runtime_character import layout, SCALE
from replay_ge_draws import iter_ge_draws


def audit(manifest_path):
    root = manifest_path.parent
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    observations = []
    unused = 0
    for frame in manifest["frames"]:
        if not frame.get("dump"):
            continue
        source = defaultdict(list)
        for record in frame["records"]:
            # Source words include the 0x2B command byte; match payload bits.
            source[tuple(w & 0xffffff for w in record["matrix"][:12])].append(record["index"])
        path = root / Path(frame["dump"]["file"]).name
        cmds, push = read_ppdmp(str(path))
        for ge in iter_ge_draws(cmds, push):
            draw, size, ptr, vt = ge['draw'], ge['size'], ge['pointer'], ge['vtype']
            if vt is None or not ((vt >> 9) & 3):
                continue
            stride, offsets = layout(vt)
            if stride <= 0 or "wt" not in offsets:
                continue
            n = size // stride
            if not n:
                continue
            nw = ((vt >> 14) & 7) + 1
            wt = (vt >> 9) & 3
            width, code, scale = {1:(1,"B",128),2:(2,"H",32768),3:(4,"f",1)}[wt]
            sums = [0.0]*nw
            for v in range(n):
                for j in range(nw):
                    weight = struct.unpack_from("<"+code, push, ptr+v*stride+offsets["wt"][0]+j*width)[0]/scale
                    if math.isfinite(weight) and weight > 0:
                        sums[j] += weight
            bbox = None
            if "pos" in offsets and offsets["pos"][1] == 6:
                points = [struct.unpack_from("<3h", push, ptr+v*stride+offsets["pos"][0]) for v in range(n)]
                bbox = [[min(p[k] for p in points)*SCALE for k in range(3)], [max(p[k] for p in points)*SCALE for k in range(3)]]
            signature = hashlib.sha256(struct.pack("<I",vt)+push[ptr:ptr+size]).hexdigest()
            for palette_index, matrix in ge['palette_payloads'].items():
                slot = palette_index * 12
                palette_index = slot//12
                if slot%12 or palette_index >= nw or sums[palette_index] == 0:
                    unused += 1
                    continue
                payload = tuple(matrix)
                candidates = source.get(payload, [])
                observations.append({"capture":root.name,"frame":frame["frame"],"object":frame["object"],"draw":draw,"vertex_sha256":signature,"vtype":vt,"vertices":n,"ge_slot":slot,"weight_sum":sums[palette_index],"source_candidates":candidates,"source_index":candidates[0] if len(candidates)==1 else None,"bbox":bbox})
    return observations, unused


def main():
    ap=argparse.ArgumentParser();ap.add_argument("manifests",nargs="+",type=Path);ap.add_argument("--out",required=True,type=Path);a=ap.parse_args()
    observations=[]; unused=0
    for path in a.manifests:
        obs, count=audit(path);observations.extend(obs);unused+=count
    covered=sorted({r["source_index"] for r in observations if r["source_index"] is not None})
    report={"schema":"aya-active-source-influences/v1","manifests":[str(p) for p in a.manifests],"active_observations":len(observations),"unused_palette_observations":unused,"unique_exact_match_observations":sum(r["source_index"] is not None for r in observations),"ambiguous_observations":sum(len(r["source_candidates"])>1 for r in observations),"unmatched_observations":sum(not r["source_candidates"] for r in observations),"covered_source_indices":covered,"uncovered_source_indices":sorted(set(range(44))-set(covered)),"observations":observations}
    a.out.write_text(json.dumps(report,ensure_ascii=False,indent=2,allow_nan=False),encoding="utf-8")
    summary={k:v for k,v in report.items() if k!="observations"}
    a.out.with_suffix(".md").write_text("# Active Aya skinning influence audit\n\n```json\n"+json.dumps(summary,ensure_ascii=False,indent=2)+"\n```\n\nExact payload correlation is not an anatomical label or proof of source/GE frame atomicity.\n",encoding="utf-8")
    print(json.dumps(summary,ensure_ascii=False))


if __name__=="__main__":main()
