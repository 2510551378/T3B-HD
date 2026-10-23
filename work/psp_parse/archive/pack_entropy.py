"""Entropy + head bytes of a few 'pack' containers (compressed?) and the SEDB entity records."""
import collections
import glob
import math
import os
import struct
import sys

ROOT = r"C:\Users\25105\Documents\寄生前夜第四日"
ISO = os.path.join(ROOT, r"PSP\The_3rd_birthday_cn_full_v101.iso")
SEC = 2048
PKG_LBA = 59600


def ent(b):
    c = collections.Counter(b)
    n = len(b)
    return -sum((v / n) * math.log2(v / n) for v in c.values())


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    with open(ISO, "rb") as f:
        for off, size in ((0x58800, 0x52820), (0x109000, 0x6154), (0x4ffac000, 0x976c)):
            f.seek(PKG_LBA * SEC + off)
            blob = f.read(size)
            c = collections.Counter(blob)
            print(f"pack @0x{off:08x} size={size:,} entropy={ent(blob):.2f} distinct={len(c)}")
            print("   head:", blob[:48].hex(" "))
            print("   top:", [(hex(k), v) for k, v in c.most_common(4)])

    # SEDB entity record sample (sedb0 at 0x4c0, 18-byte stride)
    p = glob.glob(os.path.join(os.path.dirname(__file__), "extract", "sedb", "sedb_000_*.bin"))[0]
    d = open(p, "rb").read()
    print(f"\nSEDB entity records from 0x4c0 ({os.path.basename(p)}):")
    for i in range(6):
        o = 0x4C0 + i * 18
        rec = d[o:o + 18]
        w = struct.unpack_from("<9H", rec)
        print(f"  @0x{o:06x}  {rec.hex(' ')}  u16={w}")


if __name__ == "__main__":
    main()
