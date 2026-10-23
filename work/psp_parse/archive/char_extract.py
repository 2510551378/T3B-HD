"""char_extract.py -- export the two human-shaped arrays found by human_scan.

    python char_extract.py <pack_abs_offset> <section_index> <stride> <pos_offset> <out.obj>
"""
import mmap
import os
import struct
import sys

import numpy as np

ROOT = r"C:\Users\25105\Documents\寄生前夜第四日"
ISO = os.path.join(ROOT, r"PSP\The_3rd_birthday_cn_full_v101.iso")
SC = 3.125 / 32768.0


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    packoff = int(sys.argv[1], 0)
    sect = int(sys.argv[2])
    stride = int(sys.argv[3])
    posoff = int(sys.argv[4])
    out = sys.argv[5]

    with open(ISO, "rb") as f:
        mm = mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ)
        hdr = struct.unpack_from("<I", mm, packoff + 12)[0]
        sz, so = struct.unpack_from("<II", mm, packoff + 8 + sect * 8)
        base = packoff + so
        print(f"pack 0x{packoff:08x} sect {sect}: {sz} B at +0x{so:x} (hdr 0x{hdr:x})")
        n = (sz - posoff) // stride
        P = np.array([struct.unpack_from("<3h", mm, base + k * stride + posoff)
                      for k in range(n)], dtype=np.float64) * SC
        mm.close()

    lo, hi = P.min(axis=0), P.max(axis=0)
    print(f"{n} vertices, {lo.round(2)} .. {hi.round(2)}  "
          f"({(hi-lo)[0]:.2f} x {(hi-lo)[1]:.2f} x {(hi-lo)[2]:.2f} m)")
    with open(out, "w", encoding="utf-8") as fh:
        fh.write(f"# pack 0x{packoff:08x} sect {sect} stride {stride} pos@{posoff}\n")
        for p in P:
            fh.write("v %.4f %.4f %.4f\n" % tuple(p))
        for k in range(0, n - 2, 3):
            fh.write(f"f {k+1} {k+2} {k+3}\n")
    print("->", out)


if __name__ == "__main__":
    main()
