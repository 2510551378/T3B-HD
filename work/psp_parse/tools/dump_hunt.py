"""dump_hunt.py -- find PSP vertex arrays inside an arbitrary binary (RAM dump, savestate blob,
GE frame dump) and export the best candidates as OBJ.

    python tools/dump_hunt.py ram.bin out_dir [--top 8] [--scale 9.5367e-05]

Method: PSP vertex data is either s16 (÷32768) or f32.  For a real vertex array the
consecutive vertices of a triangle list are close, so we slide a window and score
"median step / bbox diagonal" per 64 KiB block, then refine the winning blocks.
"""
import math
import os
import struct
import sys

import numpy as np

SCALE = 3.125 / 32768.0
BLOCK = 1 << 16


def triples(buf, stride, phase, dtype):
    size = 2 if dtype == "h" else 4
    fmt = "<3h" if dtype == "h" else "<3f"
    n = (len(buf) - phase) // stride
    if n < 8:
        return None
    idx = phase + np.arange(n) * stride
    a = np.empty((n, 3), dtype=np.float64)
    raw = np.frombuffer(buf, dtype="<" + ("i2" if dtype == "h" else "f4"))
    for j in range(3):
        off = idx // size + j
        off = off[off < len(raw)]
        m = len(off)
        with np.errstate(invalid="ignore"):
            a[:m, j] = raw[off]
        if m < n:
            a[m:, j] = np.nan
    if dtype == "h":
        a *= SCALE
    bad = ~np.isfinite(a).all(axis=1) | (np.abs(a) > 500).any(axis=1)
    a[bad] = np.nan
    return a, bad


def score_block(a, bad, w=48):
    """fraction of consecutive triples that are close, and how much of the block is usable."""
    n = len(a)
    if n < w + 1:
        return 0.0, 0.0
    d = np.linalg.norm(np.diff(a, axis=0), axis=1)
    ok = (~bad[1:]) & (~bad[:-1])
    if ok.sum() < w:
        return 0.0, 0.0
    med = np.median(d[ok])
    good = float(((d[ok] < max(0.35, med * 3)) & (d[ok] > 1e-6)).mean())
    span = float(np.linalg.norm(np.nanmax(a, axis=0) - np.nanmin(a, axis=0)))
    usable = 1.0 - float(bad.mean())
    if span < 0.3 or span > 60:
        good = 0.0
    return good * usable, med / span if span else 9.0


def scan(buf, strides, dtypes=("h", "f"), w=48):
    hits = []
    for base in range(0, len(buf) - BLOCK, BLOCK):
        blk = buf[base:base + BLOCK]
        for dtype in dtypes:
            for stride in strides:
                for phase in range(0, min(stride, 16), 2 if dtype == "h" else 4):
                    r = triples(blk, stride, phase, dtype)
                    if not r:
                        continue
                    a, bad = r
                    good, ratio = score_block(a, bad, w)
                    if good > 0.40 and ratio < 0.06:
                        hits.append((good, ratio, base, stride, phase, dtype))
    hits.sort(key=lambda h: (h[1], -h[0]))
    return hits

def export(buf, hit, outdir, name, max_v=200000):
    good, ratio, base, stride, phase, dtype = hit
    size = 2 if dtype == "h" else 4
    fmt = "<3h" if dtype == "h" else "<3f"
    # grow from the block both ways while the data stays sane
    start = base
    verts = []
    o = start + phase
    while o + stride <= len(buf) and len(verts) < max_v:
        t = struct.unpack_from(fmt, buf, o)
        if dtype == "f" and (any(abs(v) > 500 or v != v for v in t)):
            break
        verts.append(tuple(v * SCALE if dtype == "h" else v for v in t))
        o += stride
    if len(verts) < 3:
        return None
    path = os.path.join(outdir, f"{name}.obj")
    with open(path, "w", encoding="utf-8") as f:
        f.write(f"# dump hit @0x{base:x} stride={stride} phase={phase} dtype={dtype} "
                f"score={good:.3f} ratio={ratio:.3f}\n")
        for v in verts:
            f.write("v %.4f %.4f %.4f\n" % v)
        for k in range(0, len(verts) - 2, 3):
            f.write(f"f {k + 1} {k + 2} {k + 3}\n")
    xs = [v[0] for v in verts]
    ys = [v[1] for v in verts]
    zs = [v[2] for v in verts]
    return path, len(verts), (max(xs) - min(xs), max(ys) - min(ys), max(zs) - min(zs))


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if len(sys.argv) < 3:
        print(__doc__)
        return
    src, outdir = sys.argv[1], sys.argv[2]
    top = 8
    if "--top" in sys.argv:
        top = int(sys.argv[sys.argv.index("--top") + 1])
    os.makedirs(outdir, exist_ok=True)
    buf = open(src, "rb").read()
    print(f"{src}: {len(buf):,} bytes")
    strides = [12, 16, 20, 24, 28, 32, 36, 40, 44, 48]
    hits = scan(buf, strides)
    print(f"{len(hits)} candidate blocks")
    seen = []
    for h in hits:
        if any(abs(h[2] - s) < BLOCK * 2 and h[3] == st for s, st in seen):
            continue
        seen.append((h[2], h[3]))
        r = export(buf, h, outdir, f"hit_{len(seen):02d}_0x{h[2]:08x}_s{h[3]}_{h[5]}")
        if r:
            path, nv, bb = r
            print(f"  {os.path.basename(path)}  {nv:,} verts  bbox {bb[0]:.2f}×{bb[1]:.2f}×{bb[2]:.2f}")
        if len(seen) >= top:
            break


if __name__ == "__main__":
    main()
