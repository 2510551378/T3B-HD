"""dump_scan.py -- find structured vertex-like segments in a frame dump, with a real
density requirement so degenerate tables are rejected.

We require: >=150 consecutive records, median step 3 mm..0.25 m, bounding box 0.8..2.5 m in
the longest axis and at least 0.1 m in the others.
"""
import sys

import numpy as np

SCALE = 9.5367431640625e-05


def scan(buf, strides, dtypes, min_n=150):
    hits = []
    for stride in strides:
        for dt in dtypes:
            size = 2 if dt == "h" else 4
            step = stride // size
            if step < 3:
                continue
            total = (len(buf) - 3 * size) // (step * size)
            for ph in range(0, min(stride, 16), size):
                base = ph // size
                n = (len(buf) // size - base - 3) // step
                if n < min_n:
                    continue
                raw = np.frombuffer(buf[: (len(buf) // size) * size],
                                    dtype="<i2" if dt == "h" else "<f4")
                v = np.empty((n, 3), dtype=np.float64)
                for j in range(3):
                    v[:, j] = raw[base + j: base + j + n * step: step]
                if dt == "h":
                    v *= SCALE
                ok = np.isfinite(v).all(axis=1) & (np.abs(v) < 60).all(axis=1)
                if ok.mean() < 0.5:
                    continue
                d = np.linalg.norm(np.diff(v, axis=0), axis=1)
                close = ok[1:] & ok[:-1] & (d > 0.002) & (d < 0.25)
                idx = np.flatnonzero(~close)
                bounds = np.concatenate(([-1], idx, [len(close)]))
                for a, b in zip(bounds[:-1], bounds[1:]):
                    ln = b - a
                    if ln < min_n:
                        continue
                    seg = v[a + 1: b + 1]
                    if len(seg) < min_n:
                        continue
                    lo, hi = seg.min(axis=0), seg.max(axis=0)
                    ext = np.sort(hi - lo)
                    if 0.8 <= ext[2] <= 2.5 and ext[1] >= 0.10 and ext[0] <= 1.2:
                        off = (base + (a + 1) * step) * size
                        hits.append((int(ln), stride, dt, ph, int(off),
                                     float(ext[2]), float(ext[1]), float(ext[0])))
    hits.sort(key=lambda h: -h[0])
    return hits


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    buf = open(sys.argv[1], "rb").read()
    print(f"{sys.argv[1]}: {len(buf):,} bytes")
    hits = scan(buf, (12, 16, 20, 24, 28, 32, 36, 40, 44, 48), ("h", "f"))
    seen = []
    print(f"{len(hits)} raw hits; top non-overlapping:")
    for ln, stride, dt, ph, off, a, b, c in hits:
        if any(abs(off - o) < 256 for o in seen):
            continue
        seen.append(off)
        print(f"  @0x{off:08x} {ln:>5}v stride={stride:>2}{dt} phase={ph:>2}  "
              f"{a:.2f} x {b:.2f} x {c:.2f} m")
        if len(seen) >= 10:
            break
    if not seen:
        print("  none")


if __name__ == "__main__":
    main()
