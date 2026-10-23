"""Match runtime CLUT/TEXTURE0 uploads to type-8 pack palette/pixel bytes."""
from __future__ import annotations
import argparse, hashlib, json, struct, sys
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from extract_runtime_character import read_ppdmp
from psp_pack import iter_pack_offsets, open_pack, parse_pack, PKG_SIZE


def sha(b): return hashlib.sha1(b).hexdigest()[:12]


def pack_textures(iso: Path):
    out = []
    with iso.open("rb") as f:
        offs = iter_pack_offsets(f); spans = {o: (offs[i + 1] if i + 1 < len(offs) else PKG_SIZE) - o for i, o in enumerate(offs)}
        for off in offs:
            buf = open_pack(f, off, spans[off]); p = parse_pack(buf, off, spans[off])
            if p.type != 8 or not p.sections: continue
            _, bo = max(p.sections, key=lambda s: s[0]); blob = buf[bo:bo + max(p.sections, key=lambda s: s[0])[0]]
            if len(blob) < 0x24: continue
            tbl = struct.unpack_from("<I", blob, 0x20)[0]; idx = 0
            while tbl + 16 * (idx + 1) <= len(blob):
                w, h, code, coff, poff = struct.unpack_from("<HHIII", blob, tbl + idx * 16)
                if not (0 < w <= 1024 and 0 < h <= 1024 and code in (4, 8)): break
                ncl = 16 if code == 4 else 256; psize = w * h * code // 8
                if coff + ncl * 4 > len(blob) or poff + psize > len(blob): break
                clut = blob[coff:coff + ncl * 4]; pixels = blob[poff:poff + psize]
                out.append({"pack": f"0x{off:08x}", "texture_index": idx, "width": w, "height": h, "bpp": code, "clut_sha1": sha(clut), "pixel_sha1": sha(pixels), "clut_bytes": len(clut), "pixel_bytes": len(pixels), "clut": clut, "pixels": pixels})
                idx += 1
    return out


def runtime_payloads(roots):
    out = {}
    for raw in roots:
        root = Path(raw)
        for p in sorted(root.glob("frame_*.ppdmp")):
            cmds, push = read_ppdmp(str(p))
            for typ, size, ptr in cmds:
                if typ not in (4, 0x10) or ptr + size > len(push): continue
                payload = bytes(push[ptr:ptr + size]); key = (typ, sha(payload), size)
                out[key] = {"type": "CLUT" if typ == 4 else "TEXTURE0", "sha1": key[1], "bytes": size, "sample": str(p)}
    return list(out.values())


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("iso", type=Path); ap.add_argument("roots", nargs="+"); ap.add_argument("--out-json", required=True); ap.add_argument("--out-md", required=True); a = ap.parse_args()
    textures = pack_textures(a.iso); runtime = runtime_payloads(a.roots)
    by_sha = defaultdict(list)
    for t in textures: by_sha[("CLUT", t["clut_sha1"], t["clut_bytes"])].append(t); by_sha[("TEXTURE0", t["pixel_sha1"], t["pixel_bytes"])].append(t)
    matches = []
    for r in runtime:
        exact = by_sha.get((r["type"], r["sha1"], r["bytes"]), [])
        row = {**r, "exact_matches": [{k: v for k, v in t.items() if k not in ("clut", "pixels")} for t in exact], "subsequence_matches": []}
        if r["type"] == "CLUT":
            # Runtime CLUT uploads can be 256 entries even when the source is a 16-entry palette.
            sample_path = Path(r["sample"]); cmds, push = read_ppdmp(str(sample_path)); payloads = [bytes(push[ptr:ptr + size]) for typ, size, ptr in cmds if typ == 4 and ptr + size <= len(push) and sha(bytes(push[ptr:ptr + size])) == r["sha1"]]
            payload = payloads[0] if payloads else b""
            if payload:
                for t in textures:
                    if len(t["clut"]) <= len(payload) and payload.find(t["clut"]) >= 0:
                        row["subsequence_matches"].append({k: v for k, v in t.items() if k not in ("clut", "pixels")})
        matches.append(row)
    result = {"schema": "runtime-clut-pack-match/v1", "type8_textures": len(textures), "runtime_payloads": len(runtime), "matched_runtime_payloads": sum(bool(x["exact_matches"] or x["subsequence_matches"]) for x in matches), "textures": [{k: v for k, v in t.items() if k not in ("clut", "pixels")} for t in textures], "runtime": matches}
    Path(a.out_json).write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    lines = ["# Runtime CLUT/TEXTURE0 ↔ type-8 pack match", "", f"- type-8 texture records: {len(textures)}", f"- runtime payload signatures: {len(runtime)}", f"- runtime signatures with exact/subsequence pack match: {result['matched_runtime_payloads']}", "", "| type | runtime SHA1 | bytes | exact pack records | subsequence pack records |", "|---|---|---:|---:|---:|"]
    for r in matches: lines.append(f"| {r['type']} | `{r['sha1']}` | {r['bytes']} | {len(r['exact_matches'])} | {len(r['subsequence_matches'])} |")
    Path(a.out_md).write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"type8_textures={len(textures)} runtime_payloads={len(runtime)} matched={result['matched_runtime_payloads']}")


if __name__ == "__main__": main()
