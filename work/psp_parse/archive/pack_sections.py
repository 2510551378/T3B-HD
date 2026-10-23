"""Step 8: classify every section of every pack by its magic, and summarise roles."""
import collections
import csv
import os
import struct
import sys

ROOT = r"C:\Users\25105\Documents\寄生前夜第四日"
ISO = os.path.join(ROOT, r"PSP\The_3rd_birthday_cn_full_v101.iso")
SEC = 2048
PKG_LBA, PKG_SIZE = 59600, 1344292864
OUT = os.path.join(os.path.dirname(__file__), "extract", "packs")
sys.path.insert(0, os.path.dirname(__file__))
from psp_pack import parse_pack, iter_pack_offsets, open_pack  # noqa: E402

MAGICS = [
    (b"FEP", "FEP geometry"),
    (b"SEDBSSCF", "SEDB entity"),
    (b"pack", "pack nested"),
    (b"\x89PNG", "PNG"),
    (b"RIFF", "AT3 audio"),
    (b"PSMF", "PSMF video"),
    (b"MIG.00", "GIM texture"),
    (b"OMG.00", "GMO model"),
]


def classify(data):
    for m, name in MAGICS:
        if data.startswith(m):
            return name
    if len(data) >= 4 and data[:4] == b"\x00\x00\x00\x00":
        return "zero-head"
    # descriptor-like: first dword 0 and f32 1.0 nearby
    return "raw/other"


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    rows = []
    with open(ISO, "rb") as f:
        offs = iter_pack_offsets(f)
        spans = {o: (offs[i + 1] if i + 1 < len(offs) else PKG_SIZE) - o for i, o in enumerate(offs)}
        for o in offs:
            buf = open_pack(f, o, spans[o])
            p = parse_pack(buf, o, spans[o])
            for i, (sz, off) in enumerate(p.sections):
                head = buf[off:off + 16]
                kind = classify(head)
                rows.append({"pack": f"0x{o:08x}", "type": p.type, "section": i,
                             "offset": f"0x{off:06x}", "size": sz, "kind": kind,
                             "head": head.hex(" ")})
    c = collections.Counter(r["kind"] for r in rows)
    print(f"packs={len(offs)} sections={len(rows)}")
    for k, n in c.most_common():
        tot = sum(r["size"] for r in rows if r["kind"] == k)
        print(f"  {k:14} {n:>5} sections  {tot:>14,} bytes")
    with open(os.path.join(OUT, "sections.csv"), "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    print("-> extract/packs/sections.csv")

    # FEP: head fields per version
    fep = [r for r in rows if r["kind"] == "FEP geometry"]
    print(f"\nFEP sections: {len(fep)}")
    vers = collections.Counter()
    for r in fep:
        vers[r["head"][8:10]] += 1
    print("  versions:", dict(vers))


if __name__ == "__main__":
    main()
