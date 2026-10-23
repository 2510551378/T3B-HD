"""Step 28: numpy coherence hunt, with validity masking (rejects non-finite / oversized floats)."""
import os
import sys

import numpy as np
from numpy.lib.stride_tricks import sliding_window_view

DIR = os.path.join(os.path.dirname(__file__), "extract", "packs")
SCALE = 3.125 / 32768.0


def load(fn):
    with open(os.path.join(DIR, fn), "rb") as f:
        return f.read()


def run(fep, dtype, size, stride, phase, L=96, step=8, limit_m=(0.4, 60.0), k=1.0, topk=8):
    raw = np.frombuffer(fep, dtype="<" + dtype)
    sp = stride // size
    ph = phase // size
    total = (len(raw) - ph) // sp
    if total < L + 2:
        return []
    idx = ph + np.arange(total) * sp
    a = np.empty((len(idx), 3), dtype=np.float64)
    for j in range(3):
        a[:, j] = raw[idx + j]
    a *= k
    bad = ~np.isfinite(a).all(axis=1) | (np.abs(a) > 1e4).any(axis=1)
    if bad.all():
        return []
    valid = ~bad
    # window validity: all rows valid
    vw = sliding_window_view(valid, L)[::step]
    okw = vw.all(axis=1)
    if not okw.any():
        return []
    win = sliding_window_view(a, (L, 3))[::step, 0][okw]
    starts = np.nonzero(okw)[0] * step
    mn = win.min(axis=1)
    mx = win.max(axis=1)
    diag = np.linalg.norm(mx - mn, axis=1)
    d = np.linalg.norm(np.diff(win, axis=1), axis=2)
    med = np.median(d, axis=1)
    keep = (diag > limit_m[0]) & (diag < limit_m[1])
    if not keep.any():
        return []
    ratio = med[keep] / diag[keep]
    order = np.argsort(ratio)[:topk]
    out = []
    for oi in order:
        w = int(starts[keep][oi]) * sp * size
        out.append((float(ratio[oi]), stride, phase, w, float(diag[keep][oi])))
    return out


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    t12 = load("t12_a_0x4c685800.pack")
    fep = t12[0x130:0x130 + 0xA4860]
    cands = []
    for stride in (6, 8, 10, 12, 14, 16, 18, 20, 24, 28, 32, 36, 40):
        for phase in range(0, min(stride, 24), 2):
            cands += run(fep, "i2", 2, stride, phase, k=SCALE)
    for stride in (12, 16, 20, 24, 28, 32, 36, 40):
        for phase in range(0, min(stride, 24), 4):
            cands += run(fep, "f4", 4, stride, phase, k=1.0)
    cands.sort()
    print(f"{'coh':>7} {'stride':>6} {'phase':>5} {'start':>9} {'diag_m':>8}")
    seen = []
    for coh, stride, phase, start, diag in cands:
        if coh > 0.12:
            break
        if any(abs(start - s) < 480 and st == stride for s, st in seen):
            continue
        seen.append((start, stride))
        print(f"{coh:>7.4f} {stride:>6} {phase:>5} 0x{start:06x} {diag:>8.2f}")
        if len(seen) >= 12:
            break
    if not seen:
        print("  none under 0.12")


if __name__ == "__main__":
    main()
