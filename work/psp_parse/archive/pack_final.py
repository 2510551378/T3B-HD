"""Step 11: final pack inventory with honest spans (no next-pack guessing)."""
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
    (b"FEP", "FEP_geometry"),
    (b"SEDBSSCF", "SEDB_entity"),
    (b"pack", "pack_nested"),
    (b"\x89PNG", "PNG"),
    (b"RIFF", "AT3_audio"),
    (b"PSMF", "PSMF_video"),
    (b"MIG.00", "GIM_texture"),
]


def classify(d):
    for m, n in MAGICS:
        if d.startswith(m):
            return n
    return "blob"


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    rows = []
    kinds = collections.Counter()
    kind_bytes = collections.Counter()
    with open(ISO, "rb") as f:
        offs = iter_pack_offsets(f)
        spans = {o: (offs[i + 1] if i + 1 < len(offs) else PKG_SIZE) - o for i, o in enumerate(offs)}
        total = 0
        for o in offs:
            buf = open_pack(f, o, spans[o])
            p = parse_pack(buf, o, spans[o])
            total += p.span
            for i, (sz, off) in enumerate(p.sections):
                k = classify(buf[off:off + 12])
                kinds[k] += 1
                kind_bytes[k] += sz
                rows.append({"pack": f"0x{o:08x}", "type": p.type, "section": i,
                             "sec_off": f"0x{off:06x}", "size": sz, "kind": k})
    print(f"packs={len(offs)}  volume={total:,}  sections={len(rows)}")
    for k in kind_bytes:
        print(f"  {k:14} {kinds[k]:>5} secs {kind_bytes[k]:>14,} B")
    with open(os.path.join(OUT, "pack_sections.csv"), "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    print("-> extract/packs/pack_sections.csv")
    print("\ntype -> pack count / volume:")
    per = collections.defaultdict(lambda: [0, 0])
    for o in offs:
        buf = open_pack(f, o, spans[o])
        p = parse_pack(buf, o, spans[o])
        per[p.type][0] += 1
        per[p.type][1] += p.span
    for t in sorted(per):
        print(f"  type {t:>2}: {per[t][0]:>4} packs  {per[t][1]:>14,} B")


if __name__ == "__main__":
    main()
