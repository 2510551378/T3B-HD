"""Step 30: per-run bbox scan -- are there character-sized meshes inside the room packs?"""
import os
import struct
import sys

ROOT = r"C:\Users\25105\Documents\寄生前夜第四日"
ISO = os.path.join(ROOT, r"PSP\The_3rd_birthday_cn_full_v101.iso")
SEC = 2048
PKG_LBA, PKG_SIZE = 59600, 1344292864
sys.path.insert(0, os.path.dirname(__file__))
from psp_pack import parse_pack, iter_pack_offsets, open_pack  # noqa: E402
from pack_export import find_runs, SCALE  # noqa: E402


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
            runs = [r for r in find_runs(blob) if len(r) >= 30]
            for ri, r in enumerate(runs):
                xs = []
                ys = []
                zs = []
                for off in r:
                    x, y, z = struct.unpack_from("<3h", blob, off + 4)
                    xs.append(x * SCALE)
                    ys.append(y * SCALE)
                    zs.append(z * SCALE)
                dx = max(xs) - min(xs)
                dy = max(ys) - min(ys)
                dz = max(zs) - min(zs)
                rows.append((dy, dx, dz, len(r), o, ri))
    rows.sort(reverse=True)
    print(f"{'dy':>6} {'dx':>6} {'dz':>6} {'verts':>6} {'pack':>12} run")
    cand = [r for r in rows if 1.2 < r[0] < 2.4 and r[1] < 1.2 and r[2] < 1.2 and r[3] >= 300]
    print(f"\ncharacter-proportioned runs: {len(cand)}")
    for dy, dx, dz, n, o, ri in cand[:15]:
        print(f"{dy:>6.2f} {dx:>6.2f} {dz:>6.2f} {n:>6} 0x{o:08x} {ri}")
    print(f"\ntotal runs scanned: {len(rows)}")


if __name__ == "__main__":
    main()
