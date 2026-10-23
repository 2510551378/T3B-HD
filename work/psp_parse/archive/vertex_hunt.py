"""Step 10: vertex hunt using spatial coherence (neighbouring vertices are close)."""
import math
import os
import statistics
import struct
import sys

DIR = os.path.join(os.path.dirname(__file__), "extract", "packs")


def load(fn):
    with open(os.path.join(DIR, fn), "rb") as f:
        return f.read()


def triples(blob, o, stride, n, fmt):
    out = []
    for i in range(n):
        p = o + i * stride
        if p + (12 if fmt == "f" else 6) > len(blob):
            break
        if fmt == "f":
            t = struct.unpack_from("<3f", blob, p)
            if any((v != v) or abs(v) > 1e4 for v in t):
                return out if out else []
            out.append(t)
        else:
            out.append(struct.unpack_from("<3h", blob, p))
    return out


def coherence(tris):
    if len(tris) < 32:
        return None, None
    d = []
    for a, b in zip(tris, tris[1:]):
        d.append(math.dist(a, b))
    med = statistics.median(d)
    xs = [t[0] for t in tris]
    ys = [t[1] for t in tris]
    zs = [t[2] for t in tris]
    diag = math.dist((min(xs), min(ys), min(zs)), (max(xs), max(ys), max(zs)))
    if diag <= 0:
        return None, None
    return med / diag, diag


def hunt(blob, label, minlen=200):
    n = len(blob)
    results = []
    for fmt, bpp in (("f", 4), ("h", 2)):
        step = 4 if fmt == "f" else 2
        for S in range(8, 65, 4):
            for P in range(0, min(S, 32), step):
                tris = triples(blob, P, S, 4000, fmt)
                if len(tris) < minlen:
                    continue
                ratio, diag = coherence(tris)
                if ratio is None:
                    continue
                if ratio < 0.05 and diag > 0:
                    results.append((ratio, diag, S, P, fmt, len(tris)))
    results.sort()
    print(f"\n{label}: {len(blob):,} bytes")
    for ratio, diag, S, P, fmt, cnt in results[:8]:
        print(f"  {fmt} stride={S:>2} phase={P:>2} coh={ratio:.4f} diag={diag:.3g} n={cnt}")
    if not results:
        print("  no coherent vertex run found")


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    t8 = load("t8_a_0x444e5000.pack")
    t12 = load("t12_a_0x4c685800.pack")
    hunt(t8[0x80:0x80 + 0x37250], "t8 section0 (225,872 B)")
    hunt(t12[0x130:0x130 + 0xA4860], "t12 FEP chunk (673,888 B)")


if __name__ == "__main__":
    main()
