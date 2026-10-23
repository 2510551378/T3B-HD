"""find_ge_stream.py -- locate the GE command stream inside a frame dump.

Any real display list sets BASE (0x0F) then VTYPE (0x12) before a draw, so we scan for that
adjacent pair and then dump the commands around each hit.
"""
import struct
import sys


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    blob = open(sys.argv[1], "rb").read()
    n = len(blob) // 4
    w = struct.unpack_from(f"<{n}I", blob, 0)
    print(f"{blob and sys.argv[1]}: {len(blob):,} bytes, {n:,} words")

    pairs = [i for i in range(n - 1)
             if (w[i] >> 24) == 0x0F and (w[i + 1] >> 24) == 0x12]
    print(f"BASE->VTYPE pairs: {len(pairs)}")
    for i in pairs[:6]:
        lo = max(0, i - 2)
        seg = w[lo: lo + 24]
        print(f"  @word {i} file 0x{i * 4:08x}")
        for k, v in enumerate(seg):
            op = (v >> 24) & 0xFF
            print(f"     [{lo + k:>7}] {v:08x}  op=0x{op:02x} arg=0x{v & 0xFFFFFF:06x}")

    # how many vtype-looking args are there at all
    vt = [w[i] & 0xFFFFFF for i in range(n) if (w[i] >> 24) == 0x12]
    import collections
    print(f"\nVTYPE-opcode words: {len(vt)}")
    for a, c in collections.Counter(vt).most_common(8):
        print(f"   vtype 0x{a:06x} x{c}")


if __name__ == "__main__":
    main()
