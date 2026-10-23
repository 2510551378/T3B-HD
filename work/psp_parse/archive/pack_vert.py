"""Step 5: stronger vertex-stride detector over an arbitrary buffer (float32 focus)."""
import math
import os
import struct
import sys

DIR = os.path.join(os.path.dirname(__file__), "extract", "packs")


def load(tag):
    for fn in os.listdir(DIR):
        if fn.startswith(tag):
            return fn, open(os.path.join(DIR, fn), "rb").read()
    raise SystemExit("missing " + tag)


def f32(b, o):
    return struct.unpack_from("<f", b, o)[0]


def tri_stats(b, o, n):
    xs = []
    ok = 0
    total = 0
    for i in range(n):
        p = o + i * S_  # placeholder, replaced in caller
    return None


def score_stride(body, S, P, samples=1500):
    n = len(body)
    good = 0
    cnt = 0
    vals = []
    for i in range(samples):
        o = P + i * S
        if o + 12 > n:
            break
        cnt += 1
        try:
            x, y, z = f32(body, o), f32(body, o + 4), f32(body, o + 8)
        except Exception:
            continue
        if any(math.isnan(v) or math.isinf(v) for v in (x, y, z)):
            continue
        if abs(x) > 1e5 or abs(y) > 1e5 or abs(z) > 1e5:
            continue
        if abs(x) < 1e-6 and abs(y) < 1e-6 and abs(z) < 1e-6:
            continue
        good += 1
        vals.append((x, y, z))
    if cnt < 100:
        return None
    frac = good / cnt
    if frac < 0.55:
        return None
    # require spatial spread (real mesh) and distinct values
    uniq = len(set((round(x, 3), round(y, 3), round(z, 3)) for x, y, z in vals[:400]))
    spread = 0.0
    if vals:
        xs = [v[0] for v in vals]
        ys = [v[1] for v in vals]
        zs = [v[2] for v in vals]
        spread = max(max(xs) - min(xs), max(ys) - min(ys), max(zs) - min(zs))
    return frac, uniq, spread, vals[:3]


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    tag = sys.argv[1] if len(sys.argv) > 1 else "t12_a"
    name, blob = load(tag)
    start = int(sys.argv[2], 0) if len(sys.argv) > 2 else 0
    length = int(sys.argv[3], 0) if len(sys.argv) > 3 else len(blob) - start
    body = blob[start:start + length]
    print(f"{name}: scanning {len(body):,} bytes from 0x{start:x}")
    results = []
    for S in range(8, 81, 4):
        for P in range(0, min(S, 40), 4):
            r = score_stride(body, S, P)
            if r:
                frac, uniq, spread, sample = r
                results.append((frac, spread, uniq, S, P, sample))
    results.sort(key=lambda x: (-x[0], -x[1]))
    for frac, spread, uniq, S, P, sample in results[:10]:
        print(f"  stride={S:>2} phase={P:>2} ok={frac:.3f} spread={spread:.3g} "
              f"uniq={uniq}/400 first={tuple(round(v,3) for v in sample[0])}")


if __name__ == "__main__":
    main()
