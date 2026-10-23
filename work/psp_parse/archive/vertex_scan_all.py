"""Step 20: which packs contain 20-byte vertex records, and how many?"""
import os
import struct
import sys

ROOT = r"C:\Users\25105\Documents\寄生前夜第四日"
ISO = os.path.join(ROOT, r"PSP\The_3rd_birthday_cn_full_v101.iso")
SEC = 2048
PKG_LBA, PKG_SIZE = 59600, 1344292864
sys.path.insert(0, os.path.dirname(__file__))
from psp_pack import parse_pack, iter_pack_offsets, open_pack  # noqa: E402
from pack_export import find_runs  # noqa: E402


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    rows = []
    with open(ISO, "rb") as f:
        offs = iter_pack_offsets(f)
        spans = {o: (offs[i + 1] if i + 1 < len(offs) else PKG_SIZE) - o for i, o in enumerate(offs)}
        for o in offs:
            buf = open_pack(f, o, spans[o])
            p = parse_pack(buf, o, spans[o])
            if not p.sections:
                continue
            big = max(p.sections, key=lambda s: s[0])
            blob = buf[big[1]:big[1] + big[0]]
            runs = [r for r in find_runs(blob) if len(r) >= 3]
            nv = sum(len(r) for r in runs)
            rows.append((nv, o, p.type, len(runs), big[0], sum(1 for r in runs if len(r) % 3 == 0)))
    rows.sort(reverse=True)
    print(f"{'offset':>12} {'type':>4} {'runs':>5} {'verts':>7} {'div3':>5} {'sec_size':>10}")
    for nv, o, t, nr, sz, d3 in rows[:18]:
        print(f"0x{o:08x} {t:>4} {nr:>5} {nv:>7} {d3:>5} {sz:>10,}")
    print(f"\npacks with >=100 verts: {sum(1 for r in rows if r[0] >= 100)} / {len(rows)}")
    print(f"total vertices across all packs: {sum(r[0] for r in rows):,}")


if __name__ == "__main__":
    main()
