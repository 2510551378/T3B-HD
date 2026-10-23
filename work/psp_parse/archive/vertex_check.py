"""Step 18: pull all 20-byte vertex records, check the bbox, and test against section-1 indices."""
import math
import os
import struct
import sys

DIR = os.path.join(os.path.dirname(__file__), "extract", "packs")


def load(fn):
    with open(os.path.join(DIR, fn), "rb") as f:
        return f.read()


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    t8 = load("t8_a_0x444e5000.pack")
    sec = t8[0x80:0x80 + 0x37250]
    sec1 = t8[0x37300:0x37300 + 0x291c]
    geo = sec[0x30:0x225E8]

    # vertices: record base where base+10 == 0xcccc
    verts = []
    for o in range(0, len(geo) - 20, 2):
        if geo[o + 10:o + 12] == b"\xcc\xcc":
            verts.append(o)
    print(f"records with 0xcccc at +10: {len(verts)}")

    xs = []
    ys = []
    zs = []
    for o in verts:
        x, y, z = struct.unpack_from("<3h", geo, o + 4)
        xs.append(x)
        ys.append(y)
        zs.append(z)
    print(f"pos(s16@+4) x {min(xs)}..{max(xs)}  y {min(ys)}..{max(ys)}  z {min(zs)}..{max(zs)}")
    print(f"unscaled size: {max(xs)-min(xs)} x {max(ys)-min(ys)} x {max(zs)-min(zs)}")

    us = [struct.unpack_from("<f", geo, o + 12)[0] for o in verts]
    vs = [struct.unpack_from("<f", geo, o + 16)[0] for o in verts]
    print(f"uv(u) {min(us):.3f}..{max(us):.3f}   uv(v) {min(vs):.3f}..{max(vs):.3f}")

    # normal bytes
    nb = [geo[o:o + 3] for o in verts[:8]]
    print("normal bytes sample:", [b.hex() for b in nb])

    # section 1 header
    print("\nsection1 header dwords:", [hex(x) for x in struct.unpack_from("<8I", sec1, 0)])
    print("section1 bbox floats:", [round(x, 2) for x in struct.unpack_from("<6f", sec1, 0x20)])
    # index-like area
    for off in (0x1C00, 0x1E00, 0x2400):
        vals = struct.unpack_from("<256H", sec1, off)
        print(f"  s1+0x{off:x}: max={max(vals)} first={vals[:12]}")
    # scan s1 for u16 triples whose max < len(verts)
    best = []
    for off in range(0, len(sec1) - 6, 2):
        vals = struct.unpack_from("<3H", sec1, off)
        if max(vals) < len(verts):
            best.append((off, vals))
    print(f"  u16 triples fully below vertex count: {len(best)}")
    if best:
        print("   first:", [(hex(o), v) for o, v in best[:5]])


if __name__ == "__main__":
    main()
