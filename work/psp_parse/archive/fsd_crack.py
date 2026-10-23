"""Crack 3rd.fsd as an asset manifest: header, tables, and whether material hashes appear in it."""
import collections
import os
import struct
import sys

ROOT = r"C:\Users\25105\Documents\寄生前夜第四日"
FSD = os.path.join(ROOT, r"work\psp_parse\raw\3rd.fsd")


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    d = open(FSD, "rb").read()
    print(f"fsd {len(d)} bytes")
    print("header dwords:", [hex(x) for x in struct.unpack_from("<8I", d, 0)])
    print("header as u32:", list(struct.unpack_from("<8I", d, 0)))
    print("\nfirst 0x60 bytes:")
    for i in range(0, 0x60, 16):
        c = d[i:i + 16]
        print(f"  {i:04x}  {' '.join('%02x' % b for b in c)}  |"
              f"{''.join(chr(b) if 32 <= b < 127 else '.' for b in c)}|")

    # region map: entropy-ish per 32 bytes
    print("\nregion scan (每 32 字节首个 u32):")
    prev = None
    for i in range(0, len(d) - 32, 32):
        v = struct.unpack_from("<I", d, i)[0]
        cls = "zero" if v == 0 else ("small" if v < 0x10000 else "big")
        if cls != prev:
            print(f"  0x{i:04x} {cls} first={v:#x}")
            prev = cls

    # table at 0x72c
    print("\ntable @0x72c (first 12 records of 8 bytes):")
    for k in range(12):
        o = 0x72C + k * 8
        a, b = struct.unpack_from("<2I", d, o)
        print(f"  [{k:>3}] {a:#010x} {b:#010x}")

    # do the 762 records share a pattern?
    recs = [struct.unpack_from("<2I", d, 0x72C + k * 8) for k in range(762)]
    print("\nsecond field value histogram:", collections.Counter(b for _, b in recs).most_common(5))
    print("first field range:", hex(min(a for a, _ in recs)), "..", hex(max(a for a, _ in recs)))

    # material hashes from pack 0x444e5000
    mats = [0x0d0c, 0x6464, 0xf4f4, 0x0d0c, 0x6c65, 0xf4f4, 0x0d0c, 0x0070,
            0xf4f4, 0x0d0c, 0x0d0c, 0x1fbc, 0xf4ec, 0x776f, 0xf4f4, 0x0d0c]
    print("\nsearching material u16 values inside the fsd:")
    for v in sorted(set(mats)):
        hits = []
        pat = struct.pack("<H", v)
        i = 0
        while True:
            i = d.find(pat, i)
            if i < 0:
                break
            hits.append(i)
            i += 1
        print(f"  {v:#06x}: {len(hits)} hits {[hex(h) for h in hits[:5]]}")


if __name__ == "__main__":
    main()
