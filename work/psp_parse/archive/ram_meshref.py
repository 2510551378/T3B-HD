"""ram_meshref.py -- find mesh descriptors that point at a known vertex array.

We know where a vertex array lives (file offset -> guest 0x08000000 + offset).  A mesh
descriptor in the game's heap holds that pointer plus counts and usually the vertex format,
so we search for the pointer value and dump the surrounding fields.
"""
import struct
import sys

GUEST_BASE = 0x08000000

ARRAYS = [
    0x01239fd4,   # 1719v
    0x010413cc,   # 1275v
    0x012465c8,   # 588v
    0x0104b1e8,   # 549v
    0x01211540,   # 594v room wall
    0x0101b5c0,
]


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    blob = open(sys.argv[1], "rb").read()
    print(f"{sys.argv[1]}: {len(blob):,} bytes")

    for off in ARRAYS:
        g = GUEST_BASE + off
        pat = struct.pack("<I", g)
        hits = []
        i = 0
        while True:
            i = blob.find(pat, i)
            if i < 0:
                break
            hits.append(i)
            i += 1
        print(f"\n== vertex array file 0x{off:08x} guest 0x{g:08x}: {len(hits)} pointer hits")
        for h in hits[:4]:
            lo = max(0, h - 0x40)
            words = struct.unpack_from(f"<{(h - lo) // 4 + 16}I", blob, lo)
            print(f"  ref @file 0x{h:08x}")
            for k in range(0, len(words), 4):
                addr = lo + k * 4
                vals = " ".join(f"{w:08x}" for w in words[k:k + 4])
                mark = " <== " if lo + (k * 4) == h else "     "
                print(f"    file 0x{addr:08x} guest 0x{GUEST_BASE + addr:08x}  {vals}{mark}")


if __name__ == "__main__":
    main()
