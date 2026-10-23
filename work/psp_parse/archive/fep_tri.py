"""Step 29: triangle-list discriminator -- a real per-triangle vertex array has
within-triangle edges much shorter than the jump between triangles."""
import os
import sys

import numpy as np

DIR = os.path.join(os.path.dirname(__file__), "extract", "packs")
SCALE = 3.125 / 32768.0


def load(fn):
    with open(os.path.join(DIR, fn), "rb") as f:
        return f.read()


def score(fep, dtype, size, stride, phase, k, L=600):
    raw = np.frombuffer(fep, dtype="<" + dtype)
    sp = stride // size
    ph = phase // size
    total = (len(raw) - ph) // sp
    if total < 4:
        return []
    idx = ph + np.arange(total) * sp
    a = np.empty((len(idx), 3), dtype=np.float64)
    for j in range(3):
        a[:, j] = raw[idx + j]
    a *= k
    finite = np.isfinite(a).all(axis=1) & (np.abs(a) < 1e5).all(axis=1)
    if finite.sum() < L:
        return []
    # step through in chunks of 3 vertices
    n3 = len(a) // 3
    if n3 < 20:
        return []
    t = a[:n3 * 3].reshape(n3, 3, 3)
    fin3 = finite[:n3 * 3].reshape(n3, 3).all(axis=1)
    d_in = (np.linalg.norm(t[:, 1] - t[:, 0], axis=1) +
            np.linalg.norm(t[:, 2] - t[:, 1], axis=1)) / 2
    d_jump = np.linalg.norm(t[1:, 0] - t[:-1, 2], axis=1)
    ok = fin3[:-1] & fin3[1:]
    if ok.sum() < 50:
        return []
    d_in, d_jump = d_in[1:][ok], d_jump[ok]
    good = d_in > 1e-5
    if good.sum() < 50:
        return []
    ratios = d_jump[good] / d_in[good]
    med = float(np.median(ratios))
    # where is this chunk
    return [(med, float(np.median(d_jump[good])), stride, phase)]


def scan_window(fep, off, win=0x4000):
    seg = fep[off:off + win]
    out = []
    for stride in (6, 8, 10, 12, 14, 16, 18, 20, 24, 28, 32):
        for phase in range(0, min(stride, 12), 2):
            out += score(seg, "i2", 2, stride, phase, SCALE)
    for stride in (12, 16, 20, 24, 28, 32, 36):
        for phase in range(0, min(stride, 12), 4):
            out += score(seg, "f4", 4, stride, phase, 1.0)
    return out


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    t12 = load("t12_a_0x4c685800.pack")
    fep = t12[0x130:0x130 + 0xA4860]
    print(f"FEP {len(fep):,}")
    rows = []
    for off in range(0, len(fep) - 0x4000, 0x8000):
        r = scan_window(fep, off)
        if not r:
            continue
        r.sort(reverse=True)
        med, jump, stride, phase = r[0]
        rows.append((med, jump, off, stride, phase))
    rows.sort(reverse=True)
    print(f"{'jump/in':>8} {'jump_m':>8} {'window':>9} {'stride':>6} {'phase':>5}")
    for med, jump, off, stride, phase in rows[:12]:
        print(f"{med:>8.2f} {jump:>8.2f} 0x{off:06x} {stride:>6} {phase:>5}")


if __name__ == "__main__":
    main()
