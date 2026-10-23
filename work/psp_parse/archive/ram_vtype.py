"""ram_vtype.py -- look for PSP GE vertex-format words (vtype) in a RAM blob and print
the words around them, so the display-list command pattern becomes visible.
"""
import collections
import struct
import sys

VTYPES = [0x3002, 0x3000, 0x111E, 0x1111, 0x3012, 0x3A02, 0x2A02, 0x1202]


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    blob = open(sys.argv[1], "rb").read()
    print(f"{sys.argv[1]}: {len(blob):,} bytes")

    # 1) how often does each vtype word appear, aligned and unaligned?
    for v in VTYPES:
        pat_le = struct.pack("<I", v)
        pat_be = struct.pack(">I", v)
        print(f"  vtype {v:#06x}: LE={blob.count(pat_le)}  BE={blob.count(pat_be)}")

    # 2) take the most common one and show its neighbourhood
    best = max(VTYPES, key=lambda v: blob.count(struct.pack("<I", v)))
    pat = struct.pack("<I", best)
    print(f"\ncontexts of {best:#06x} (first 10, ±8 words):")
    i = 0
    n = 0
    while n < 10:
        i = blob.find(pat, i)
        if i < 0:
            break
        lo = max(0, i - 8 * 4)
        words = struct.unpack_from(f"<{(i - lo)//4 + 8}I", blob, lo)
        print(f"  @0x{i:08x}: " + " ".join(f"{w:08x}" for w in words))
        i += 4
        n += 1

    # 3) histogram of u32 values in the 0x3000..0x3fff band (possible vtypes)
    band = collections.Counter()
    for off in range(0, len(blob) - 4, 4):
        w = struct.unpack_from("<I", blob, off)[0]
        if 0x3000 <= w <= 0x3FFF:
            band[w] += 1
    print(f"\ntop 12 words in 0x3000..0x3fff ({sum(band.values())} total):")
    for w, c in band.most_common(12):
        print(f"  {w:#06x} x{c}")


if __name__ == "__main__":
    main()
