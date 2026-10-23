"""dump_all.py -- brute-force decode every VERTICES block of a frame dump.

For each block we try every stride and every position offset for both s16 and f32 components,
score the resulting point cloud, keep the best interpretation, and report/export the ones that
look like real geometry.

    python dump_all.py <dump.ppdmp> <out_dir> [--min-score 0.6]
"""
import os
import struct
import sys

import numpy as np

sys.path.insert(0, r"work\psp_parse\archive")
from ppdmp2 import read  # noqa: E402

SC = 3.125 / 32768.0


def score(P):
    if len(P) < 24:
        return None
    if not np.isfinite(P).all() or np.abs(P).max() > 100:
        return None
    d = np.linalg.norm(np.diff(P, axis=0), axis=1)
    med = float(np.median(d))
    if not (0.0005 <= med <= 0.45):
        return None
    ext = np.sort(P.max(axis=0) - P.min(axis=0))
    if ext[2] < 0.2:
        return None
    good = float(np.mean((d > 1e-6) & (d < max(0.2, med * 5))))
    if good < 0.6:
        return None
    return good, med, ext


def best_layout(blk):
    best = None
    n = len(blk)
    for dt, size in (("h", 2), ("f", 4)):
        usable = (len(blk) // size) * size
        raw = np.frombuffer(blk[:usable], dtype="<i2" if dt == "h" else "<f4")
        total = len(raw)
        for stride in range(8, 65):
            if stride % size:
                continue
            step = stride // size
            for off in range(0, stride - 3 * size + 1, size):
                base = off // size
                cnt = (total - base) // step
                if cnt < 24:
                    continue
                w = raw[base:base + cnt * step].reshape(cnt, step)[:, :3]
                P = w.astype(np.float64)
                if dt == "h":
                    P *= SC
                sc = score(P)
                if not sc:
                    continue
                good, med, ext = sc
                rank = (good, -med)
                if best is None or rank > best[0]:
                    best = (rank, stride, dt, off, cnt, med, ext, P)
    return best


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    cmds, buf = read(sys.argv[1])
    outdir = sys.argv[2]
    os.makedirs(outdir, exist_ok=True)
    for f in os.listdir(outdir):
        if f.endswith(".obj"):
            os.remove(os.path.join(outdir, f))

    results = []
    for i, (t, sz, ptr) in enumerate(cmds):
        if t != 2 or sz < 96 or ptr + sz > len(buf):
            continue
        blk = buf[ptr:ptr + sz]
        r = best_layout(blk)
        if r:
            results.append((i, sz) + r[1:])
    print(f"{len(results)} of {sum(1 for t, s, p in cmds if t == 2)} vertex blocks decoded")

    results.sort(key=lambda r: -r[5])
    print(f"{'cmd':>5} {'bytes':>7} {'stride':>6} {'off':>4} {'n':>5}  "
          f"dims (sorted)        med    person?")
    people = []
    for i, sz, stride, dt, off, n, med, ext, P in results:
        person = (1.2 <= ext[2] <= 2.2 and ext[1] >= 0.12 and ext[0] <= 1.2
                  and ext[2] >= 1.5 * ext[1])
        if person:
            people.append((i, sz, stride, dt, off, n, med, ext, P))
    for i, sz, stride, dt, off, n, med, ext, P in people[:16]:
        print(f"{i:>5} {sz:>7} {stride:>6} {off:>4} {n:>5}  "
              f"{ext[2]:5.2f} x {ext[1]:5.2f} x {ext[0]:5.2f}  {med:.3f}   YES")
    print(f"person-shaped: {len(people)}")

    for i, sz, stride, dt, off, n, med, ext, P in people:
        path = os.path.join(outdir, f"cmd{i:04d}_{n}v_s{stride}{dt}.obj")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(f"# cmd {i} {sz}B stride {stride} {dt} off {off}\n")
            for p in P:
                fh.write("v %.4f %.4f %.4f\n" % tuple(p))
            for k in range(0, n - 2, 3):
                fh.write(f"f {k+1} {k+2} {k+3}\n")
    print(f"exported {len(people)} -> {outdir}")


if __name__ == "__main__":
    main()
