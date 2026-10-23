"""ppdmp_mesh.py -- decode each recorded VERTICES block as one draw.

Because the dump stores one vertex block per draw, the stride must divide the block size
exactly.  For every block we try the plausible strides and both component types, score the
resulting cloud, and print the best interpretation.  Human-shaped ones are exported.
"""
import os
import struct
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from ppdmp2 import read  # noqa: E402

SCALE = 9.5367431640625e-05
STRIDES = (12, 16, 20, 24, 28, 32, 36, 40, 44, 48, 52, 56, 64)


def score(v):
    if len(v) < 8:
        return None
    if not np.isfinite(v).all():
        return None
    if np.abs(v).max() > 200:
        return None
    d = np.linalg.norm(np.diff(v, axis=0), axis=1)
    med = float(np.median(d))
    if not (0.0005 <= med <= 0.5):
        return None
    span = np.linalg.norm(v.max(axis=0) - v.min(axis=0))
    if span <= 0:
        return None
    good = float(np.mean((d > 1e-6) & (d < max(0.3, med * 4))))
    return good, med / span, med, span


def try_block(buf):
    """The game's vtype has float32 positions, so search float triples first."""
    best = None
    n = len(buf)
    for dt in ("f", "h"):
        size = 4 if dt == "f" else 2
        for stride in STRIDES:
            if stride % size:
                continue
            for ph in range(0, stride - 3 * size + 1, size):
                count = (n - ph) // stride
                if count < 8:
                    continue
                if dt == "f":
                    v = np.frombuffer(buf, dtype="<f4", count=count * 3,
                                      offset=ph).reshape(count, 3).astype(np.float64)
                else:
                    v = np.frombuffer(buf, dtype="<i2", count=count * 3,
                                      offset=ph).reshape(count, 3).astype(np.float64)
                    v *= SCALE
                sc = score(v)
                if not sc:
                    continue
                good, ratio, med, span = sc
                if good < 0.6 or ratio > 0.12:
                    continue
                rank = (good, -ratio)
                if best is None or rank > best[0]:
                    best = (rank, stride, dt, ph, count, med, span, v)
    return best


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    cmds, buf = read(sys.argv[1])
    outdir = sys.argv[2] if len(sys.argv) > 2 else "out/dump/draws"
    os.makedirs(outdir, exist_ok=True)

    results = []
    for i, (t, sz, ptr) in enumerate(cmds):
        if t != 2 or ptr + sz > len(buf) or sz < 60:
            continue
        blk = buf[ptr:ptr + sz]
        r = try_block(blk)
        if not r:
            continue
        rank, stride, dt, ph, count, med, span, v = r
        results.append((i, sz, stride, dt, ph, count, med, span, rank, v))

    print(f"{len(results)} VERTICES blocks decoded")
    # human-shaped first
    def person(e):
        v = e[-1]
        ext = np.sort(v.max(axis=0) - v.min(axis=0))
        return 1.2 <= ext[2] <= 2.2 and ext[1] >= 0.12 and ext[0] <= 1.2 and ext[2] >= 1.5 * ext[1]

    people = [e for e in results if person(e)]
    print(f"person-shaped draws: {len(people)}")
    for e in people[:12]:
        i, sz, stride, dt, ph, count, med, span, rank, v = e
        ext = np.sort(v.max(axis=0) - v.min(axis=0))
        print(f"  cmd[{i:>4}] {sz:>6}B stride={stride:>2}{dt} off={ph:>2} count={count:>5} "
              f"{ext[2]:.2f} x {ext[1]:.2f} x {ext[0]:.2f} m medstep={med:.3f}")

    for k, e in enumerate(people[:8]):
        i, sz, stride, dt, ph, count, med, span, rank, v = e
        path = os.path.join(outdir, f"draw{i:03d}_{count}v_s{stride}{dt}.obj")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(f"# cmd {i} {sz}B stride {stride} off {ph}\n")
            for p in v:
                fh.write("v %.4f %.4f %.4f\n" % tuple(p))
            for k2 in range(0, count - 2, 3):
                fh.write(f"f {k2+1} {k2+2} {k2+3}\n")
    print(f"exported {len(people[:8])} -> {outdir}")


if __name__ == "__main__":
    main()
