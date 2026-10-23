"""Step 26: constrained vertex hunt in FEP -- arrays sized by the index maximum, human-scale bbox."""
import math
import os
import struct
import sys

DIR = os.path.join(os.path.dirname(__file__), "extract", "packs")
SCALE = 3.125 / 32768.0


def load(fn):
    with open(os.path.join(DIR, fn), "rb") as f:
        return f.read()


def probe(fep, start, n, stride, phase, dtype="h"):
    fmt = "<3h" if dtype == "h" else "<3f"
    sz = 6 if dtype == "h" else 12
    pts = []
    for i in range(n):
        o = start + phase + i * stride
        if o + sz > len(fep):
            return None
        t = struct.unpack_from(fmt, fep, o)
        if dtype == "f" and any(abs(v) > 1e4 or v != v for v in t):
            return None
        pts.append(t)
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    zs = [p[2] for p in pts]
    if dtype == "h":
        k = SCALE
    else:
        k = 1.0
    dx = (max(xs) - min(xs)) * k
    dy = (max(ys) - min(ys)) * k
    dz = (max(zs) - min(zs)) * k
    diag = math.sqrt(dx * dx + dy * dy + dz * dz)
    if diag <= 0:
        return None
    # coherence on a sample
    step = max(1, n // 300)
    ds = []
    for i in range(0, n - step, step):
        ds.append(math.dist(pts[i], pts[i + step]) * k)
    med = sorted(ds)[len(ds) // 2] if ds else 0
    return dx, dy, dz, diag, med


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    t12 = load("t12_a_0x4c685800.pack")
    fep = t12[0x130:0x130 + 0xA4860]
    zones = [(0x21000, 3594), (0x2D000, 3855), (0x56000, 3856), (0x83000, 3856)]
    hits = []
    for Z, N in zones:
        for stride in (6, 8, 10, 12, 14, 16, 18, 20, 24, 28, 32):
            for phase in range(0, min(stride, 10), 2):
                for slack in range(0, 0x120, 8):
                    start = Z - slack - N * stride
                    if start < 0:
                        continue
                    r = probe(fep, start, N, stride, phase, "h")
                    if not r:
                        continue
                    dx, dy, dz, diag, med = r
                    if 1.0 < dy < 2.6 and dx < 2.2 and dz < 2.2 and 0.6 < max(dx, dz) < 2.2:
                        hits.append((med / diag if diag else 9, dx, dy, dz, stride, phase,
                                     start, slack, Z, "s16"))
                    r2 = probe(fep, start, N, stride, phase, "f")
                    if r2:
                        dx2, dy2, dz2, diag2, med2 = r2
                        if 1.0 < dy2 < 2.6 and dx2 < 2.2 and dz2 < 2.2 and 0.6 < max(dx2, dz2) < 2.2:
                            hits.append((med2 / diag2 if diag2 else 9, dx2, dy2, dz2, stride,
                                         phase, start, slack, Z, "f32"))
    hits.sort()
    print(f"candidates: {len(hits)}")
    for h in hits[:15]:
        coh, dx, dy, dz, stride, phase, start, slack, Z, dt = h
        print(f"  coh={coh:.3f} bbox={dx:.2f}x{dy:.2f}x{dz:.2f} m  stride={stride:>2} "
              f"phase={phase:>2} start=0x{start:06x} slack=0x{slack:x} zone=0x{Z:x} {dt}")


if __name__ == "__main__":
    main()
