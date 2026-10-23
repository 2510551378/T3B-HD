"""assemble.py -- merge the skinned parts with per-block sanity checks.

Each block is decoded with its real vtype; blocks whose cloud is implausible (outliers, huge
extent) are dropped instead of poisoning the merge.
"""
import os
import struct
import sys

import numpy as np

sys.path.insert(0, r"work\psp_parse\archive")
from ppdmp2 import read  # noqa: E402
from vtype_decode import layout, positions  # noqa: E402

SKIN = (0x4522, 0x8522, 0xC522)


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    cmds, buf = read(sys.argv[1])
    out = sys.argv[2]
    cur = None
    kept, dropped = [], 0
    for i, (t, sz, ptr) in enumerate(cmds):
        if ptr + sz > len(buf):
            continue
        if t == 1:
            for x in struct.unpack_from("<%dI" % (sz // 4), buf, ptr):
                if (x >> 24) == 0x12:
                    cur = x & 0xFFFFFF
        elif t == 2 and cur in SKIN and sz >= 40:
            stride, offs = layout(cur)
            po, ps = offs["pos"]
            P = positions(buf[ptr:ptr + sz], stride, po, ps)
            if P is None or len(P) < 8:
                continue
            lo = np.percentile(P, 2, axis=0)
            hi = np.percentile(P, 98, axis=0)
            d = hi - lo
            if np.abs(np.abs(P).max(axis=0)).max() > 20 or d.max() > 2.2:
                dropped += 1
                continue
            kept.append((i, P))
            cur = cur
    V = np.vstack([k[1] for k in kept])
    lo, hi = np.percentile(V, 1, axis=0), np.percentile(V, 99, axis=0)
    print(f"kept {len(kept)} blocks ({dropped} dropped), {len(V)} vertices")
    print(f"robust bbox {(hi-lo)[0]:.2f} x {(hi-lo)[1]:.2f} x {(hi-lo)[2]:.2f} m")
    print(f"y range {lo[1]:.2f} .. {hi[1]:.2f}")
    for a, b in ((0, .4), (.4, .8), (.8, 1.2), (1.2, 1.6), (1.6, 2.0)):
        m = (V[:, 1] >= a) & (V[:, 1] < b)
        if m.sum():
            print(f"  y {a:.1f}-{b:.1f}: {m.sum():>5} verts  "
                  f"x {V[m,0].min():.2f}..{V[m,0].max():.2f}  z {V[m,2].min():.2f}..{V[m,2].max():.2f}")
    with open(out, "w", encoding="utf-8") as fh:
        fh.write("# assembled skinned parts\n")
        base = 0
        for i, P in kept:
            fh.write(f"o cmd{i}\n")
            for p in P:
                fh.write("v %.4f %.4f %.4f\n" % tuple(p))
            n = len(P)
            for k in range(0, n - 2, 3):
                fh.write(f"f {base+k+1} {base+k+2} {base+k+3}\n")
            base += n
    print("->", out)


if __name__ == "__main__":
    main()
