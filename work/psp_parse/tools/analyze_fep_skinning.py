"""Inventory FEP geometry/skinning fields across all type-8 packs.

This intentionally reports candidates and coverage instead of inventing a
vertex layout.  FEP does not carry the type-8 0xCCCC marker, so index, weight,
name and offset evidence are retained per block for later runtime matching.
"""
from __future__ import annotations
import argparse, csv, json, mmap, re, struct
from collections import Counter
from pathlib import Path

SEC = 2048
PKG_LBA = 59600
PKG_BASE = PKG_LBA * SEC
ASCII = re.compile(rb"[ -~]{8,}")


def u32(b, o): return struct.unpack_from("<I", b, o)[0]


def index_runs(data: bytes):
    # Candidate u16 index runs: bounded values with a non-trivial maximum.
    vals = struct.unpack("<%dH" % (len(data) // 2), data[: len(data) & ~1])
    hits = []
    start = None; last = None; vmax = 0
    for i, v in enumerate(vals):
        good = v < 4096
        if good and start is None: start = i; vmax = v
        elif good and start is not None: vmax = max(vmax, v)
        elif not good and start is not None:
            if i - start >= 32 and vmax >= 32: hits.append((start * 2, (i - start) * 2, vmax))
            start = None
    if start is not None and len(vals) - start >= 32 and vmax >= 32: hits.append((start * 2, (len(vals) - start) * 2, vmax))
    merged = []
    for off, size, mx in hits:
        if merged and off <= merged[-1][0] + merged[-1][1] + 8:
            a, b, c = merged[-1]; merged[-1] = (a, max(b, off + size - a), max(c, mx))
        else: merged.append((off, size, mx))
    return [{"offset": o, "bytes": s, "u16_count": s // 2, "max": m} for o, s, m in merged if s >= 64]


def weight_regions(data: bytes):
    # Four-byte normalized weights are often exact 255 or 1 sums.
    blocks = []
    step = 0x1000
    for base in range(0, len(data), step):
        chunk = data[base:base + step]
        n = max(0, len(chunk) - 3); s255 = s1 = 0
        for i in range(0, n, 4):
            q = chunk[i:i + 4]
            if len(q) < 4: break
            sm = sum(q); s255 += sm == 255; s1 += sm == 1
        if s255 >= 16 or s1 >= 16:
            blocks.append({"offset": base, "bytes": len(chunk), "sum255": s255, "sum1": s1})
    return blocks


def object_offset_hint(data: bytes):
    vals = []
    off = 0x50
    while off + 4 <= min(len(data), 0x400):
        v = u32(data, off)
        if v < 0x48 or v >= len(data): break
        if vals and v < vals[-1]: break
        vals.append(v); off += 4
    return vals


def analyze_block(data: bytes):
    hdr = {"version_word": u32(data, 4) if len(data) >= 8 else None, "header_bytes": u32(data, 8) if len(data) >= 12 else None, "block_bytes": u32(data, 0x14) if len(data) >= 0x18 else None}
    fields = {f"u32_{o:x}": u32(data, o) for o in [0x18, 0x1c, 0x20, 0x24, 0x28, 0x2c, 0x30, 0x34, 0x38, 0x3c, 0x40, 0x44, 0x48, 0x4c] if o + 4 <= len(data)}
    names = sorted({m.group().decode("ascii", "ignore") for m in ASCII.finditer(data) if len(m.group()) <= 96})[:128]
    idx = index_runs(data)
    weights = weight_regions(data)
    return {"header": hdr, "fields": fields, "offset_table_hint": object_offset_hint(data), "index_runs": idx, "weight_regions": weights, "ascii_names": names, "index_candidate_count": len(idx), "weight_region_count": len(weights), "max_index": max((x["max"] for x in idx), default=0)}


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("sections_csv", type=Path); ap.add_argument("iso", type=Path); ap.add_argument("out_json", type=Path); ap.add_argument("out_md", type=Path); a = ap.parse_args()
    rows = []
    with a.iso.open("rb") as f, mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ) as mm, a.sections_csv.open(encoding="utf-8") as sf:
        for r in csv.DictReader(sf):
            if r.get("kind") not in ("FEP geometry", "FEP_geometry"): continue
            pack = int(r["pack"], 16); sec = int(r["sec_off"], 16); size = int(r["size"])
            data = mm[PKG_BASE + pack + sec:PKG_BASE + pack + sec + size]
            x = analyze_block(data); x.update({"pack": r["pack"], "section": r["section"], "offset": r["sec_off"], "bytes": size})
            rows.append(x)
    result = {"schema": "fep-skinning-inventory/v1", "blocks": len(rows), "rows": rows}
    a.out_json.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    total_indices = sum(r["index_candidate_count"] for r in rows); total_weights = sum(r["weight_region_count"] for r in rows); max_idx = max((r["max_index"] for r in rows), default=0)
    lines = ["# FEP skinning inventory", "", f"- FEP blocks: {len(rows)}", f"- candidate u16 index runs: {total_indices}", f"- candidate normalized-weight regions: {total_weights}", f"- global maximum candidate index: {max_idx}", "- Candidate streams are retained with offsets; no vertex layout is declared until runtime draw matching validates it.", "", "| pack | bytes | version | header | index runs | weight regions | max index | names |", "|---|---:|---:|---:|---:|---:|---:|---:|"]
    for r in rows: lines.append(f"| {r['pack']} | {r['bytes']} | 0x{r['header']['version_word']:x} | 0x{r['header']['header_bytes']:x} | {r['index_candidate_count']} | {r['weight_region_count']} | {r['max_index']} | {len(r['ascii_names'])} |")
    a.out_md.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"blocks={len(rows)} index_runs={total_indices} weight_regions={total_weights} max_index={max_idx}")


if __name__ == "__main__": main()
