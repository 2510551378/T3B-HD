"""Step 22: segment the FEP chunk into zones by 4 KiB statistics, then probe each zone."""
import collections
import math
import os
import struct
import sys

DIR = os.path.join(os.path.dirname(__file__), "extract", "packs")


def load(fn):
    with open(os.path.join(DIR, fn), "rb") as f:
        return f.read()


def ent(b):
    c = collections.Counter(b)
    n = len(b)
    return -sum((v / n) * math.log2(v / n) for v in c.values())


def zero_frac(b):
    return b.count(0) / len(b)


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    t12 = load("t12_a_0x4c685800.pack")
    fep = t12[0x130:0x130 + 0xA4860]
    W = 4096
    print(f"FEP {len(fep):,} B, {len(fep)//W} windows of 4 KiB")
    prev = None
    for i in range(0, len(fep) - W + 1, W):
        w = fep[i:i + W]
        e = ent(w)
        z = zero_frac(w)
        tag = ""
        head = w[:8]
        if head.startswith(b"FEP"):
            tag = "FEP magic"
        sig = f"{e:.2f}/{z:.2f}"
        if prev != sig:
            print(f"  0x{i:06x}  entropy/zero={sig}  head={head.hex(' ')} {tag}")
            prev = sig


if __name__ == "__main__":
    main()
