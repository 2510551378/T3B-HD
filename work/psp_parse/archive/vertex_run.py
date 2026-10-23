"""Step 13: run-based vertex finder (longest run of valid, spatially-coherent float triples)."""
import math
import os
import statistics
import struct
import sys

DIR = os.path.join(os.path.dirname(__file__), "extract", "packs")


def load(fn):
    with open(os.path.join(DIR, fn), "rb") as f:
        return f.read()


def valid(b, o):
    try:
        t = struct.unpack_from("<3f", b, o)
    except struct.error:
        return None
    for v in t:
        if v != v or abs(v) > 1e4:
            return None
    return t


def scan(b, stride, phase, maxn=4000):
    n = len(b)
    best = (0, 0, None)
    run = []
    start = None
    i = 0
    while i < maxn:
        o = phase + i * stride
        if o + 12 > n:
            break
        t = valid(b, o)
        if t is None:
            run = []
            start = None
            i += 1
            continue
        if start is None:
            start = i
        if run:
            d = math.dist(run[-1], t)
            # coherence: reject violent jumps
            if d > 200:
                if len(run) > best[0]:
                    best = (len(run), start, run[:4])
                run = []
                start = i
        run.append(t)
        i += 1
    if len(run) > best[0]:
        best = (len(run), start, run[:4])
    return best


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    t8 = load("t8_a_0x444e5000.pack")
    sec = t8[0x80:0x80 + 0x37250]
    for name, region in (("full section", sec), ("pre-texture 0x30..0x22640", sec[0x30:0x22640])):
        print(f"\n== {name}  {len(region):,} B")
        res = []
        for stride in range(12, 65, 4):
            for phase in range(0, min(stride, 40), 4):
                n, start, sample = scan(region, stride, phase)
                if n >= 300:
                    res.append((n, stride, phase, start, sample))
        res.sort(reverse=True)
        for n, stride, phase, start, sample in res[:6]:
            xs = [round(v, 2) for v in sample[0]] if sample else []
            print(f"  run={n:>5} stride={stride:>2} phase={phase:>2} start={start:<5} first={xs}")
        if not res:
            print("  none")


if __name__ == "__main__":
    main()
