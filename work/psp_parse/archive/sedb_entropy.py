"""Entropy + histogram + mid-file dumps for SEDB (compressed? encoded text?)."""
import collections
import glob
import math
import os
import sys

SEQ = os.path.join(os.path.dirname(__file__), "extract", "sedb")


def load(n):
    p = glob.glob(os.path.join(SEQ, f"sedb_{n:03d}_*.bin"))[0]
    with open(p, "rb") as f:
        return os.path.basename(p), f.read()


def ent(b):
    c = collections.Counter(b)
    n = len(b)
    return -sum((v / n) * math.log2(v / n) for v in c.values())


def hexdump(d, base, limit):
    for i in range(0, min(len(d), limit), 16):
        c = d[i:i + 16]
        hx = " ".join(f"{b:02x}" for b in c)
        asc = "".join(chr(b) if 32 <= b < 127 else "." for b in c)
        print(f"  {base + i:08x}  {hx:<47}  |{asc}|")


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    for n in (0, 1, 28, 244):
        name, blob = load(n)
        body = blob[0xC0:]
        c = collections.Counter(body)
        top = c.most_common(8)
        print(f"===== {name} size={len(blob):,} entropy(whole)={ent(blob):.2f} "
              f"entropy(body)={ent(body):.2f}")
        print("  top bytes:", [(hex(k), v) for k, v in top])
        print("  distinct bytes:", len(c))
        print("  mid-file 0x2000:")
        hexdump(blob[0x2000:], 0x2000, 0x80)
        print()


if __name__ == "__main__":
    main()
