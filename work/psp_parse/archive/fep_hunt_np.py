"""Step 27: vectorised vertex hunt in FEP using spatial-coherence (numpy)."""
import os
import sys

import numpy as np

DIR = os.path.join(os.path.dirname(__file__), "extract", "packs")
SCALE = 3.125 / 32768.0


def load(fn):
    with open(os.path.join(DIR, fn), "rb") as f:
        return f.read()


def hunt(fep, L=96, step=16, topk=25):
    n = len(fep)
    best = []
    for dtype, size, k in (("i2", 2, SCALE), ("f4", 4, 1.0)):
        raw = np.frombuffer(fep, dtype="<" + dtype)
        if dtype == "i2":
            usable = (len(raw) // 3) * 3
            pass
        for stride in (6, 8, 10, 12, 14, 16, 18, 20, 24, 28, 32, 36, 40):
            if stride % size:
                continue
            sp = stride // size
            need = 3
            if dtype == "i2":
                if stride < 6:
                    continue
            else:
                if stride < 12:
                    continue
            for phase in range(0, stride - (3 * size) + 1, size):
                ph = phase // size
                total = (len(raw) - ph) // sp
                if total < L + 2:
                    continue
                idx = ph + np.arange(total) * sp
                m = idx + 2
                m = m[m < len(raw)]
                cnt = len(m)
                if cnt < L + 2:
                    continue
                pts = np.stack([raw[m], raw[m + 0], raw[m + 0]], axis=0)  # placeholder
                # build (cnt,3) view
                a = np.empty((cnt, 3), dtype=np.float64)
                base = idx[:cnt]
                for j in range(3):
                    a[:, j] = raw[base + j]
                a *= k
                # sliding windows
                from numpy.lib.stride_tricks import sliding_window_view
                win = sliding_window_view(a, (L, 3))[::step, 0]
                if len(win) == 0:
                    continue
                mn = win.min(axis=1)
                mx = win.max(axis=1)
                diag = np.linalg.norm(mx - mn, axis=1)
                ok = diag > 1e-6
                if not ok.any():
                    continue
                d = np.linalg.norm(np.diff(win, axis=1), axis=2)
                med = np.median(d, axis=1)
                ratio = np.where(ok, med / np.where(ok, diag, 1.0), 9.0)
                w = np.arange(len(win)) * step * sp * size
                order = np.argsort(ratio)[:topk]
                for oi in order:
                    best.append((float(ratio[oi]), dtype, stride, phase,
                                 int(w[oi]), float(diag[oi])))
    best.sort()
    return best


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    t12 = load("t12_a_0x4c685800.pack")
    fep = t12[0x130:0x130 + 0xA4860]
    res = hunt(fep)
    print(f"{'coh':>7} {'dtype':>4} {'stride':>6} {'phase':>5} {'start':>9} {'diag_m':>8}")
    seen = []
    for coh, dtype, stride, phase, start, diag in res:
        if coh > 0.06:
            continue
        if any(abs(start - s) < 320 and stride == st for s, st in seen):
            continue
        seen.append((start, stride))
        print(f"{coh:>7.4f} {dtype:>4} {stride:>6} {phase:>5} 0x{start:06x} {diag:>8.2f}")
        if len(seen) >= 12:
            break


if __name__ == "__main__":
    main()
