"""ram_f32.py -- find long, plausible float32 vertex runs in a RAM dump.

PPSSPP keeps guest RAM readable, but the GPU-side buffers the game uploads are float32.
So we look for long stretches where consecutive vertices are metres apart and the whole
run stays in a sane world range.
"""
import os
import sys

import numpy as np

SANITY = 60.0     # metres; anything beyond is not a vertex position
MIN_RUN = 200     # vertices
MAX_STEP = 1.5    # metres between consecutive vertices


def scan(buf, strides=(12, 16, 20, 24, 28, 32, 36, 40, 44, 48), min_run=MIN_RUN):
    buf = buf[: len(buf) // 4 * 4]
    f = np.frombuffer(buf, dtype="<f4")
    n = len(f)
    out = []
    for stride in strides:
        step = stride // 4
        for phase in range(step):
            m = (n - phase) // step
            if m < min_run + 2:
                continue
            v = f[phase:phase + m * step].reshape(m, step)[:, :3]
            ok = np.isfinite(v).all(axis=1) & (np.abs(v) < SANITY).all(axis=1)
            if ok.mean() < 0.3:
                continue
            d = np.linalg.norm(np.diff(np.where(ok[:, None], v, np.nan), axis=0), axis=1)
            close = np.isfinite(d) & (d > 1e-5) & (d < MAX_STEP)
            # longest run of close steps
            idx = np.flatnonzero(~close)
            bounds = np.concatenate(([-1], idx, [len(close)]))
            lengths = np.diff(bounds) - 1
            if len(lengths) == 0:
                continue
            k = int(np.argmax(lengths))
            if lengths[k] < min_run:
                continue
            s = bounds[k] + 1
            e = bounds[k + 1]
            seg = v[s:e + 1]
            lo, hi = seg.min(axis=0), seg.max(axis=0)
            span = float(np.linalg.norm(hi - lo))
            out.append((int(lengths[k]), stride, phase * 4, int(s), span, lo, hi))
    out.sort(reverse=True)
    return out


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    src = sys.argv[1]
    outdir = sys.argv[2] if len(sys.argv) > 2 else "."
    top = int(sys.argv[sys.argv.index("--top") + 1]) if "--top" in sys.argv else 10
    buf = open(src, "rb").read()
    print(f"{src}: {len(buf):,} bytes")
    res = scan(buf)
    print(f"{len(res)} float32 runs >= {MIN_RUN} verts")
    os.makedirs(outdir, exist_ok=True)
    for i, (ln, stride, poff, start, span, lo, hi) in enumerate(res[:top]):
        print(f"  run{i:02d} verts={ln:>7,} stride={stride:>2} start=0x{start * 4:08x} "
              f"span={span:6.2f} m  x{lo[0]:7.2f}..{hi[0]:7.2f} "
              f"y{lo[1]:7.2f}..{hi[1]:7.2f} z{lo[2]:7.2f}..{hi[2]:7.2f}")
        # dump this run as OBJ
        f = np.frombuffer(buf, dtype="<f4")
        step = stride // 4
        v = f[start * step:start * step + (ln + 1) * step].reshape(ln + 1, step)[:, :3]
        path = os.path.join(outdir, f"f32_{i:02d}_0x{start*4:08x}_s{stride}.obj")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(f"# {ln} verts stride {stride}\n")
            for p in v:
                fh.write("v %.4f %.4f %.4f\n" % tuple(p))
            for k in range(0, len(v) - 2, 3):
                fh.write(f"f {k+1} {k+2} {k+3}\n")
    print("objs ->", outdir)


if __name__ == "__main__":
    main()
