"""pool_probe.py -- decode the small vertex pools and report their dimensions.

The vertex pool layout on disc is 20 bytes: colour RGBA @0, position s16x3 @4,
0xCCCC pad @10, UV f32x2 @12.
"""
import csv
import os
import struct
import sys

import numpy as np

ROOT = r"C:\Users\25105\Documents\寄生前夜第四日"
ISO = os.path.join(ROOT, r"PSP\The_3rd_birthday_cn_full_v101.iso")
PKG_LBA, SEC = 59600, 2048
SC = 3.125 / 32768.0


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    rows = [r for r in csv.DictReader(open(sys.argv[1]))
            if r["content"] == "vertex pool"]
    rows.sort(key=lambda r: int(r["size"]))
    lim = int(sys.argv[2]) if len(sys.argv) > 2 else 20

    f = open(ISO, "rb")
    print(f"{'pack':>10} {'type':>5} {'bytes':>8} {'verts':>6}  dims (sorted, m)      colour")
    for r in rows[:lim]:
        off = int(r["pack_offset"], 16) + int(r["rel_offset"], 16)
        size = int(r["size"])
        f.seek(off)
        d = f.read(size)
        n = size // 20
        if n < 8:
            continue
        P = np.array([struct.unpack_from("<3h", d, k * 20 + 4) for k in range(n)],
                     dtype=np.float64) * SC
        C = [tuple(d[k * 20:k * 20 + 3]) for k in range(n)]
        ext = np.sort(P.max(axis=0) - P.min(axis=0))
        rr = sorted(c[0] for c in C)[n // 2]
        gg = sorted(c[1] for c in C)[n // 2]
        bb = sorted(c[2] for c in C)[n // 2]
        tip = ""
        if 1.2 <= ext[2] <= 2.2 and ext[1] >= 0.12 and ext[0] <= 1.2 and ext[2] >= 1.5 * ext[1]:
            tip = "  <== person?"
        print(f"{r['pack_offset']:>10} {r['type']:>5} {size:>8} {n:>6}  "
              f"{ext[2]:5.2f} x {ext[1]:5.2f} x {ext[0]:5.2f}   ({rr},{gg},{bb}){tip}")
    f.close()


if __name__ == "__main__":
    main()
