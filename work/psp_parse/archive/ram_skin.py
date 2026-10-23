"""ram_skin.py -- find a skinned-vertex layout in a RAM blob.

A PSP skinned vertex usually carries, in one record: position (s16x3), normal (s8/s16x3),
texcoord, skin weights (u8, summing to 255) and bone indices (u8, small).  We look for a
record size/alignment whose byte columns contain (a) a column of small, varying values
(bones) and (b) a run of 2-4 columns summing to ~255 (weights).  Then we check whether the
record also yields a human-sized point cloud.
"""
import sys

import numpy as np

SANITY = 60.0


def column_stats(mat):
    return mat.min(axis=0), mat.max(axis=0), mat.std(axis=0)


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    blob = open(sys.argv[1], "rb").read()
    print(f"{sys.argv[1]}: {len(blob):,} bytes")
    cands = []
    for stride in range(16, 68, 2):
        n = (len(blob) - stride) // stride
        if n < 400:
            continue
        for align in range(0, min(stride, 16)):
            start = align
            m = (len(blob) - start) // stride
            if m < 400:
                continue
            mat = np.frombuffer(blob, dtype=np.uint8, count=m * stride, offset=start).reshape(m, stride)
            lo, hi, sd = column_stats(mat)
            # bone-index columns: small positives that actually vary
            bone = (hi < 72) & (sd > 6) & (hi > 8)
            if not bone.any():
                continue
            for w0 in range(0, stride - 3):
                cols = mat[:, w0:w0 + 4].astype(np.int32)
                s = cols.sum(axis=1)
                frac = float(np.mean((s > 200) & (s < 300)))
                if frac < 0.75:
                    continue
                # where are the positions? scan s16 triples in the record
                for p in range(0, stride - 5, 2):
                    if p + 6 > stride:
                        break
                    v = np.frombuffer(blob, dtype="<i2", count=m * 3, offset=start + p).reshape(m, 3)[:m - 1]
                    if len(v) < 300:
                        continue
                    vf = v.astype(np.float64) * 9.5367431640625e-05
                    ok = np.abs(vf).max(axis=1) < SANITY
                    if ok.mean() < 0.6:
                        continue
                    vv = vf[ok]
                    lo3, hi3 = vv.min(axis=0), vv.max(axis=0)
                    dx, dy, dz = hi3 - lo3
                    if not (1.30 <= dy <= 2.10 and 0.12 <= dx <= 1.10 and 0.12 <= dz <= 1.10):
                        continue
                    cands.append((stride, start % stride, p, w0, len(vv), dx, dy, dz, 1.0 - ok.mean()))
    cands.sort(key=lambda c: (c[0], -c[4]))
    print(f"skinned-layout candidates: {len(cands)}")
    seen = set()
    for stride, al, p, w0, nv, dx, dy, dz, miss in cands[:20]:
        key = (stride, p)
        if key in seen:
            continue
        seen.add(key)
        print(f"  stride={stride:>2} pos@{p:>2} weights@{w0:>2} bones-> {nv:>5} verts  "
              f"{dx:.2f} x {dy:.2f} x {dz:.2f} m")


if __name__ == "__main__":
    main()
