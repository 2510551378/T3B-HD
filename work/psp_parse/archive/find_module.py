"""find_module.py -- locate the game's code image inside a RAM blob.

The symbol map says the main module sits at 0x08804000 and is 0x4AF000 bytes.  MIPS code has
a very recognisable density of plausible opcodes, so we score 4 KiB blocks and look for a
long contiguous run whose length is close to the module size.
"""
import sys

import numpy as np

MODULE_BASE = 0x08804000
MODULE_SIZE = 0x004AF000

COMMON = {
    0x00, 0x01, 0x02, 0x03, 0x04, 0x05, 0x06, 0x07, 0x08, 0x09, 0x0A, 0x0B, 0x0C, 0x0D,
    0x0F, 0x10, 0x11, 0x12, 0x14, 0x15, 0x17, 0x18, 0x19, 0x1A, 0x1B, 0x1C, 0x1D,
    0x20, 0x21, 0x23, 0x24, 0x25, 0x27, 0x28, 0x29, 0x2A, 0x2B, 0x2F,
    0x30, 0x31, 0x34, 0x35, 0x38, 0x39, 0x3C, 0x3D,
}


def score(buf):
    n = len(buf) // 4 * 4
    w = np.frombuffer(buf[:n], dtype="<u4")
    op = (w >> 26) & 0x3F
    ok = np.isin(op, list(COMMON))
    # exclude the degenerate all-zero / all-ff words that also look "valid"
    ok &= (w != 0) & (w != 0xFFFFFFFF)
    blocks = len(w) // 1024
    dens = ok[: blocks * 1024].reshape(blocks, 1024).mean(axis=1)
    return dens, blocks


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    buf = open(sys.argv[1], "rb").read()
    dens, blocks = score(buf)
    print(f"{sys.argv[1]}: {len(buf):,} bytes, {blocks} x 4 KiB blocks")
    hi = dens > 0.55
    print(f"blocks with MIPS density > 0.55: {int(hi.sum())}")

    # longest contiguous run
    best = (0, 0, 0)
    start = None
    for i, h in enumerate(hi):
        if h and start is None:
            start = i
        elif not h and start is not None:
            if i - start > best[0]:
                best = (i - start, start, i)
            start = None
    if start is not None and blocks - start > best[0]:
        best = (blocks - start, start, blocks)
    ln, a, b = best
    print(f"longest run: {ln} blocks = {ln * 4096:,} bytes, "
          f"file 0x{a * 4096:08x}..0x{b * 4096:08x}")
    if ln:
        # where would the module base land?
        implied = a * 4096 - 0
        print(f"if guest 0x{MODULE_BASE:08x} sits at file 0x{implied:08x}, then guest = "
              f"0x{MODULE_BASE:08x} + (file - 0x{implied:08x})")
    # top 5 runs
    runs = []
    start = None
    for i, h in enumerate(hi):
        if h and start is None:
            start = i
        elif not h and start is not None:
            runs.append((i - start, start))
            start = None
    if start is not None:
        runs.append((blocks - start, start))
    runs.sort(reverse=True)
    print("\ntop runs (blocks, start file offset, size):")
    for ln2, s in runs[:6]:
        print(f"  {ln2:>5} blocks  file 0x{s * 4096:08x}  {ln2 * 4096:>9,} bytes")


if __name__ == "__main__":
    main()
