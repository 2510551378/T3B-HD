"""skinned_probe.py -- find the record layout of the blocks that are not in the 0x11F layout.

For every VERTICES block whose size is not a multiple of 20 (so it cannot be the environment
format) we search stride and position offset for an s16 triple array that looks like real
geometry.
"""
import struct
import sys

import numpy as np

sys.path.insert(0, r"work\psp_parse\archive")
from ppdmp2 import read  # noqa: E402

SC = 3.125 / 32768.0


def score(P):
    if len(P) < 16:
        return None
    d = np.linalg.norm(np.diff(P, axis=0), axis=1)
    med = float(np.median(d))
    if not (0.0008 <= med <= 0.4):
        return None
    ext = np.sort(P.max(axis=0) - P.min(axis=0))
    if ext[2] < 0.3:
        return None
    good = float(np.mean((d > 1e-6) & (d < max(0.25, med * 5))))
    if good < 0.7:
        return None
    return ext, med, good


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    cmds, buf = read(sys.argv[1])
    out = []
    for i, (t, sz, ptr) in enumerate(cmds):
        if t != 2 or sz < 160 or ptr + sz > len(buf) or sz % 20 == 0:
            continue
        d = buf[ptr:ptr + sz]
        best = None
        for stride in range(10, 45):
            n = sz // stride
            if n < 16:
                continue
            for off in range(0, stride - 6 + 1, 2):
                P = np.array([struct.unpack_from("<3h", d, k * stride + off)
                              for k in range(n)], dtype=np.float64) * SC
                sc = score(P)
                if not sc:
                    continue
                ext, med, good = sc
                rank = (good, -med)
                if best is None or rank > best[0]:
                    best = (rank, stride, off, n, ext, med, P)
        if best:
            out.append((i, sz) + best[1:])
    print(f"{len(out)} non-20-byte blocks decoded")
    out.sort(key=lambda r: -r[3])
    print(f"{'cmd':>6} {'size':>6} {'stride':>6} {'off':>3} {'n':>5}  dims (sorted)      med")
    people = 0
    for i, sz, stride, off, n, ext, med, P in out[:14]:
        flag = ""
        if 1.2 <= ext[2] <= 2.2 and ext[1] >= 0.12 and ext[0] <= 1.2:
            flag = "  <== person?"
            people += 1
        print(f"{i:>6} {sz:>6} {stride:>6} {off:>3} {n:>5}  "
              f"{ext[2]:.2f} x {ext[1]:.2f} x {ext[0]:.2f}   {med:.3f}{flag}")
    print(f"person-shaped: {people}")


if __name__ == "__main__":
    main()
