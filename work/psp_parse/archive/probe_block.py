"""probe_block.py -- find the field layout of one recorded VERTICES block.

Tries every stride that divides the block size exactly and every 4-byte position offset,
then reports the interpretations whose point cloud looks like real geometry.
"""
import struct
import sys

import numpy as np

sys.path.insert(0, r"work\psp_parse\archive")
from ppdmp2 import read  # noqa: E402


def stats(v):
    ext = np.sort(v.max(axis=0) - v.min(axis=0))
    d = np.linalg.norm(np.diff(v, axis=0), axis=1)
    med = float(np.median(d))
    good = float(np.mean((d > 1e-6) & (d < max(0.2, med * 4))))
    return ext, med, good


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    cmds, buf = read(sys.argv[1])
    cid = int(sys.argv[2])
    t, sz, ptr = cmds[cid]
    d = buf[ptr:ptr + sz]
    print(f"cmd[{cid}] type={t} sz={sz} ptr=0x{ptr:06x}")

    cands = []
    for stride in range(12, 65, 2):
        if sz % stride:
            continue
        n = sz // stride
        if n < 16:
            continue
        for off in range(0, stride - 12 + 1, 4):
            v = np.frombuffer(d, dtype="<f4", count=n * 3,
                              offset=off).reshape(n, 3).astype(np.float64)
            ok = np.isfinite(v).all() and np.abs(v).max() < 100
            if not ok:
                continue
            ext, med, good = stats(v)
            if ext[2] < 0.2 or med <= 0 or med > 1.0 or good < 0.6:
                continue
            cands.append((stride, off, n, ext, med, good))

    cands.sort(key=lambda c: (-c[5], c[4]))
    print(f"{len(cands)} plausible float layouts")
    print(f"{'stride':>6} {'off':>3} {'n':>5}  {'dims (sorted, m)':<26} {'medstep':>7} {'good':>5}")
    for stride, off, n, ext, med, good in cands[:12]:
        print(f"{stride:>6} {off:>3} {n:>5}  {ext[2]:6.2f} x {ext[1]:5.2f} x {ext[0]:5.2f}"
              f"      {med:7.3f} {good:5.2f}")


if __name__ == "__main__":
    main()
