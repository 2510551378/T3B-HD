"""Step 34: scale-free FEP vertex search -- arrays sized by the index count, tall aspect, coherent."""
import math
import os
import struct
import sys

DIR = os.path.join(os.path.dirname(__file__), "extract", "packs")


def load(fn):
    with open(os.path.join(DIR, fn), "rb") as f:
        return f.read()


def bbox_of(fep, start, n, stride, phase, dtype="h"):
    fmt = "<3h" if dtype == "h" else "<3f"
    sz = 6 if dtype == "h" else 12
    xs = []
    ys = []
    zs = []
    pts = []
    for i in range(n):
        o = start + phase + i * stride
        if o + sz > len(fep):
            return None
        t = struct.unpack_from(fmt, fep, o)
        if dtype == "f" and any(abs(v) > 1e5 or v != v for v in t):
            return None
        pts.append(t)
        xs.append(t[0])
        ys.append(t[1])
        zs.append(t[2])
    dx = max(xs) - min(xs)
    dy = max(ys) - min(ys)
    dz = max(zs) - min(zs)
    if max(dx, dy, dz) <= 0:
        return None
    diag = math.sqrt(dx * dx + dy * dy + dz * dz)
    step = max(1, n // 400)
    ds = [math.dist(pts[i], pts[i + step]) for i in range(0, n - step, step)]
    med = sorted(ds)[len(ds) // 2] if ds else 0
    distinct = len(set(pts)) / n
    return dx, dy, dz, diag, med / diag, distinct


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    t12 = load("t12_a_0x4c685800.pack")
    fep = t12[0x130:0x130 + 0xA4860]
    zones = [(0x21000, 3594), (0x2D000, 3855), (0x56000, 3856), (0x83000, 3856)]
    hits = []
    for Z, N in zones:
        for dtype, size, strides in (("h", 2, (6, 8, 10, 12, 14, 16, 18, 20, 24, 28, 32)),
                                     ("f", 4, (12, 16, 20, 24, 28, 32))):
            for stride in strides:
                if stride % size:
                    continue
                for phase in range(0, min(stride, 12), size):
                    for slack in range(0, 0x200, 8):
                        start = Z - slack - N * stride
                        if start < 0:
                            continue
                        r = bbox_of(fep, start, N, stride, phase, dtype)
                        if not r:
                            continue
                        dx, dy, dz, diag, coh, dist = r
                        if max(dx, dy, dz) <= 0 or dist < 0.5:
                            continue
                        tall = dy / max(dx, dz)
                        flat = max(dx, dz) / max(dy, 1e-9)
                        if 1.3 < tall < 4.0 and coh < 0.35:
                            hits.append((coh, tall, dx, dy, dz, stride, phase, start, slack, Z, dtype))
    hits.sort()
    print(f"candidates {len(hits)}")
    for h in hits[:12]:
        coh, tall, dx, dy, dz, stride, phase, start, slack, Z, dt = h
        print(f"  coh={coh:.3f} tall={tall:.2f} bbox={dx:.3g}x{dy:.3g}x{dz:.3g} "
              f"stride={stride:>2} ph={phase:>2} start=0x{start:06x} slack=0x{slack:x} zone=0x{Z:x} {dt}")


if __name__ == "__main__":
    main()
