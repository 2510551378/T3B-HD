"""ram_body.py -- hunt person-shaped vertex segments in a RAM blob, format-agnostic.

We do not assume the static-mesh layout.  For each plausible (stride, phase, dtype) we read
triples, split them wherever consecutive vertices jump or leave the world, and keep the
segments whose bounding box looks like a standing human (tall, narrow, 1.3-2.1 m).
"""
import os
import sys

import numpy as np

SANITY = 80.0
MAX_STEP = 0.7
MIN_V, MAX_V = 100, 20000


def segments(v, ok):
    """split indices wherever ok is False or the step is too large"""
    d = np.linalg.norm(np.diff(v, axis=0), axis=1)
    brk = np.zeros(len(v), dtype=bool)
    brk[0] = True
    brk[1:] = (~ok[1:]) | (~ok[:-1]) | ~(d < MAX_STEP)
    idx = np.flatnonzero(brk)
    return np.concatenate((idx, [len(v)]))


def scan(buf, name):
    hits = []
    combos = []
    for stride in (12, 16, 20, 24, 28, 32, 36, 40):
        if stride % 4:
            combos.append((stride, 0, "h"))
            combos.append((stride, 2, "h"))
            combos.append((stride, 4, "h"))
        else:
            for ph in (0, 4, 8):
                combos.append((stride, ph, "f"))
            for ph in (0, 2, 4):
                combos.append((stride, ph, "h"))
    for stride, phase, dt in combos:
        size = 2 if dt == "h" else 4
        raw = np.frombuffer(buf[: len(buf) // size * size], dtype="<i2" if dt == "h" else "<f4")
        n = (len(raw) - phase // size - 2 * stride // size) // (stride // size)
        if n < MIN_V:
            continue
        base = phase // size
        step = stride // size
        v = np.empty((n, 3), dtype=np.float64)
        for j in range(3):
            v[:, j] = raw[base + j: base + j + n * step: step]
        if dt == "h":
            v *= 9.5367431640625e-05
        ok = np.isfinite(v).all(axis=1) & (np.abs(v) < SANITY).all(axis=1)
        if ok.mean() < 0.2:
            continue
        vv = np.where(ok[:, None], v, np.nan)
        bounds = segments(v, ok)
        for a, b in zip(bounds[:-1], bounds[1:]):
            ln = b - a
            if ln < MIN_V or ln > MAX_V:
                continue
            seg = vv[a:b]
            lo, hi = np.nanmin(seg, axis=0), np.nanmax(seg, axis=0)
            dx, dy, dz = hi - lo
            if not (1.30 <= dy <= 2.10):
                continue
            if not (0.12 <= dx <= 1.10 and 0.12 <= dz <= 1.10):
                continue
            if dy < 1.45 * max(dx, dz):
                continue
            hits.append((ln, stride, phase, dt, int(a * step * size),
                         float(dx), float(dy), float(dz)))
    hits.sort(key=lambda h: -h[0])
    return hits


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    src = sys.argv[1]
    outdir = sys.argv[2] if len(sys.argv) > 2 else "out/dump"
    os.makedirs(outdir, exist_ok=True)
    buf = open(src, "rb").read()
    print(f"{src}: {len(buf):,} bytes")
    hits = scan(buf, src)
    print(f"person-shaped segments: {len(hits)}")
    for ln, stride, phase, dt, off, dx, dy, dz in hits[:15]:
        print(f"  {ln:>5}v stride={stride:>2}/{dt} phase={phase} @0x{off:08x}  "
              f"{dx:.2f} x {dy:.2f} x {dz:.2f} m")
    # export the top ones
    made = 0
    for i, (ln, stride, phase, dt, off, dx, dy, dz) in enumerate(hits[:20]):
        size = 2 if dt == "h" else 4
        raw = np.frombuffer(buf[: len(buf) // size * size], dtype="<i2" if dt == "h" else "<f4")
        step = stride // size
        start = off // size + phase // size
        v = np.empty((ln, 3), dtype=np.float64)
        for j in range(3):
            v[:, j] = raw[start + j: start + j + ln * step: step]
        if dt == "h":
            v *= 9.5367431640625e-05
        path = os.path.join(outdir, f"body_{i:02d}_0x{off:08x}_s{stride}{dt}.obj")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(f"# {ln} verts stride {stride} phase {phase} dtype {dt}\n")
            for p in v:
                fh.write("v %.4f %.4f %.4f\n" % tuple(p))
            for k in range(0, ln - 2, 3):
                fh.write(f"f {k+1} {k+2} {k+3}\n")
        made += 1
    print(f"wrote {made} OBJs -> {outdir}")


if __name__ == "__main__":
    main()
