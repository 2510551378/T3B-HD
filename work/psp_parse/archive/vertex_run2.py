"""Step 14: run-based vertex finder for both float32 and s16 position streams."""
import math
import os
import statistics
import struct
import sys

DIR = os.path.join(os.path.dirname(__file__), "extract", "packs")


def load(fn):
    with open(os.path.join(DIR, fn), "rb") as f:
        return f.read()


def read_tri(b, o, fmt):
    if fmt == "f":
        if o + 12 > len(b):
            return None
        t = struct.unpack_from("<3f", b, o)
        if any(v != v or abs(v) > 1e4 for v in t):
            return None
        return t
    if o + 6 > len(b):
        return None
    return struct.unpack_from("<3h", b, o)


def scan(b, stride, phase, fmt, maxn=6000, jump=None):
    n = len(b)
    best = (0, 0, None)
    run = []
    start = None
    i = 0
    limit = jump if jump is not None else (50.0 if fmt == "f" else 3000.0)
    while i < maxn:
        o = phase + i * stride
        if o + (12 if fmt == "f" else 6) > n:
            break
        t = read_tri(b, o, fmt)
        if t is None:
            if len(run) > best[0]:
                best = (len(run), start, run[:3])
            run, start = [], None
            i += 1
            continue
        if start is None:
            start = i
        if run and math.dist(run[-1], t) > limit:
            if len(run) > best[0]:
                best = (len(run), start, run[:3])
            run, start = [], i
        run.append(t)
        i += 1
    if len(run) > best[0]:
        best = (len(run), start, run[:3])
    return best


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    t8 = load("t8_a_0x444e5000.pack")
    t12 = load("t12_a_0x4c685800.pack")
    cases = [
        ("t8 section0 full", t8[0x80:0x80 + 0x37250]),
        ("t8 pre-texture", t8[0x80 + 0x30:0x80 + 0x22640]),
        ("t8 section1", t8[0x37300:0x37300 + 0x291c]),
        ("t12 FEP", t12[0x130:0x130 + 0xA4860]),
    ]
    for name, region in cases:
        print(f"\n== {name}  {len(region):,} B")
        out = []
        for fmt in ("f", "h"):
            for stride in range(6, 49, 2 if fmt == "h" else 4):
                for phase in range(0, min(stride, 24), 2 if fmt == "h" else 4):
                    n, start, sample = scan(region, stride, phase, fmt)
                    if n >= 200:
                        out.append((n, fmt, stride, phase, start, sample))
        out.sort(reverse=True)
        for n, fmt, stride, phase, start, sample in out[:6]:
            print(f"  run={n:>5} {fmt} stride={stride:>2} phase={phase:>2} start={start:<5} "
                  f"first={[round(v, 1) for v in sample[0]] if sample else None}")
        if not out:
            print("  none")


if __name__ == "__main__":
    main()
