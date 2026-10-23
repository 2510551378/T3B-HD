"""Dump UTF-16LE text from a SEDB file with offsets, plus the byte layout of the first strings."""
import glob
import os
import re
import struct
import sys

SEQ = os.path.join(os.path.dirname(__file__), "extract", "sedb")


def load(n):
    p = glob.glob(os.path.join(SEQ, f"sedb_{n:03d}_*.bin"))[0]
    with open(p, "rb") as f:
        return os.path.basename(p), f.read()


def dump(n=28, limit=60):
    name, blob = load(n)
    print(f"== {name}  size={len(blob):,}")
    # find candidate UTF-16LE string regions: sequences of code points in CJK/ASCII/punct
    ok = lambda ch: (0x4E00 <= ch <= 0x9FFF) or (0x3000 <= ch <= 0x303F) or (0x30A0 <= ch <= 0x30FF) \
        or (0xFF00 <= ch <= 0xFFEF) or (0x20 <= ch <= 0x7E) or ch in (0x2026, 0x2014, 0x201C, 0x201D)
    runs = []
    i = 0
    while i + 1 < len(blob):
        ch = blob[i] | (blob[i + 1] << 8)
        if ok(ch):
            j = i
            chars = []
            while j + 1 < len(blob):
                c = blob[j] | (blob[j + 1] << 8)
                if not ok(c):
                    break
                chars.append(c)
                j += 2
            if len(chars) >= 4:
                runs.append((i, j - i, "".join(map(chr, chars))))
            i = j + 2 if j > i else i + 2
        else:
            i += 2
    print(f"candidate UTF-16 runs: {len(runs)}")
    for off, nb, s in runs[:limit]:
        print(f"  @0x{off:06x} len={nb:>4}  {s[:80]}")
    return blob, runs


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    dump(28, 40)
