"""ram_matrices.py -- find the display list's matrix commands inside guest RAM.

The GE display list built by the game contains
    (0x0A << 24) | n   BONEMATRIXNUMBER
    (0x0B << 24) | f24 BONEMATRIXDATA   (12 values per matrix, 8 matrices)
and the same pattern for WORLD (0x0C / 0x0D).

So a run of 12 consecutive words whose top byte is 0x0B is one bone matrix; 0x0D is the world
matrix.  Values are float24 = float32 >> 8.
"""
import struct
import sys

import numpy as np


def f24(bits):
    return struct.unpack("<f", struct.pack("<I", (bits & 0xFFFFFF) << 8))[0]


def runs_with_byte(w, byte, min_run=12):
    mask = ((w >> 24) & 0xFF) == byte
    out = []
    i = 0
    n = len(w)
    while i < n:
        if not mask[i]:
            i += 1
            continue
        j = i
        while j < n and mask[j]:
            j += 1
        if j - i >= min_run:
            out.append((i, j - i))
        i = j
    return out


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    blob = open(sys.argv[1], "rb").read()
    n = len(blob) // 4
    w = np.frombuffer(blob[:n * 4], dtype="<u4").astype(np.uint64)
    print(f"{sys.argv[1]}: {len(blob):,} bytes, {n:,} words")

    for byte, name, per in ((0x0D, "world", 12), (0x0B, "bone", 12), (0x0F, "view", 12),
                            (0x11, "proj", 16)):
        r = runs_with_byte(w, byte)
        print(f"\n  top byte 0x{byte:02x} ({name}): {len(r)} runs")
        for start, ln in r[:6]:
            vals = [f24(int(x)) for x in w[start:start + per]]
            print(f"    @word {start} (file 0x{start * 4:08x}) len {ln}")
            print("      " + " ".join(f"{v:8.3f}" for v in vals))


if __name__ == "__main__":
    main()
