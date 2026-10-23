"""char_pack.py -- inspect a character model container found by skin_scan.

    python char_pack.py 0x5730f800
"""
import mmap
import os
import struct
import sys

import numpy as np

ROOT = r"C:\Users\25105\Documents\寄生前夜第四日"
ISO = os.path.join(ROOT, r"PSP\The_3rd_birthday_cn_full_v101.iso")
PKG_LBA, PKG_SIZE, SEC = 59600, 1344292864, 2048
SC = 3.125 / 32768.0


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    off = int(sys.argv[1], 0)
    with open(ISO, "rb") as f:
        mm = mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ)
        ptype = struct.unpack_from("<I", mm, off + 4)[0]
        hdr = struct.unpack_from("<I", mm, off + 12)[0]
        count = (hdr - 8) // 8
        secs = []
        for i in range(count):
            sz, so = struct.unpack_from("<II", mm, off + 8 + i * 8)
            if sz and so:
                secs.append((i, sz, so))
        print(f"pack 0x{off:08x} type {ptype} hdr 0x{hdr:x} sections {len(secs)}")
        for i, sz, so in secs:
            head = bytes(mm[off + so:off + so + 24])
            a = bytes(mm[off + so:off + so + min(sz, 4096)])
            pads = a.count(b"\xcc\xcc")
            print(f"  sect {i}: {sz:>8} B  head {head.hex()}  cc={pads}")

        # try to decode the big sections as vertex arrays
        for i, sz, so in secs:
            if sz < 8192:
                continue
            base = off + so
            for stride in (20, 24, 28, 32, 36):
                n = sz // stride
                if n < 50:
                    continue
                for off2 in range(0, stride - 6 + 1, 2):
                    P = np.array([struct.unpack_from("<3h", mm, base + k * stride + off2)
                                  for k in range(min(n, 600))], dtype=np.float64) * SC
                    if not np.isfinite(P).all() or np.abs(P).max() > 100:
                        continue
                    lo, hi = P.min(axis=0), P.max(axis=0)
                    d = hi - lo
                    if 1.2 <= d[1] <= 2.2 and max(d[0], d[2]) <= 1.4:
                        print(f"  => sect {i} stride {stride} pos@{off2}: "
                              f"{n} verts  {d[0]:.2f} x {d[1]:.2f} x {d[2]:.2f} m  HUMANOID")
        mm.close()


if __name__ == "__main__":
    main()
