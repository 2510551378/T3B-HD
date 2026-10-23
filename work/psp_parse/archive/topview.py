"""Top-down scatter of the vertex pool, coloured by run -- shows whether the pieces tile or scatter."""
import math
import os
import struct
import sys

import numpy as np
from PIL import Image, ImageDraw

ROOT = r"C:\Users\25105\Documents\寄生前夜第四日"
ISO = os.path.join(ROOT, r"PSP\The_3rd_birthday_cn_full_v101.iso")
SEC = 2048
PKG_LBA, PKG_SIZE = 59600, 1344292864
SCALE = 3.125 / 32768.0
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tools"))
from psp_pack import parse_pack, iter_pack_offsets, open_pack  # noqa: E402
from pack_export import find_runs  # noqa: E402


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    pack = int(sys.argv[1], 0) if len(sys.argv) > 1 else 0x444e5000
    out = sys.argv[2] if len(sys.argv) > 2 else "xz.png"
    with open(ISO, "rb") as f:
        offs = iter_pack_offsets(f)
        i = offs.index(pack)
        span = (offs[i + 1] if i + 1 < len(offs) else PKG_SIZE) - pack
        buf = open_pack(f, pack, span)
        p = parse_pack(buf, pack, span)
        big = max(p.sections, key=lambda s: s[0])
        blob = buf[big[1]:big[1] + big[0]]
    runs = [r for r in find_runs(blob) if len(r) >= 3]
    pts = []
    for ri, r in enumerate(runs):
        for o in r:
            x, y, z = struct.unpack_from("<3h", blob, o + 4)
            pts.append((x * SCALE, y * SCALE, z * SCALE, ri))
    A = np.array(pts)
    print(f"pack 0x{pack:08x}: {len(A)} verts, {len(runs)} runs")
    S = 1400
    xz = A[:, [0, 2]]
    lo, hi = xz.min(axis=0), xz.max(axis=0)
    span_ = (hi - lo).max() or 1
    img = np.zeros((S, S, 3), dtype=np.uint8)
    img[:] = (16, 17, 20)
    px = ((xz[:, 0] - lo[0]) / span_ * (S - 1)).astype(int)
    py = ((xz[:, 1] - lo[1]) / span_ * (S - 1)).astype(int)
    rng = np.random.default_rng(7)
    palette = (rng.random((len(runs), 3)) * 0.75 + 0.25)
    col = (palette[A[:, 3].astype(int)] * 255).astype(np.uint8)
    img[py, px] = col
    im = Image.fromarray(img)
    dr = ImageDraw.Draw(im)
    dr.text((8, 8), f"pack 0x{pack:08x}  top view (X-Z)  {len(A)} verts  {len(runs)} runs",
            fill=(230, 230, 230))
    dr.text((8, S - 18), f"X {lo[0]:.2f}..{hi[0]:.2f} m   Z {lo[1]:.2f}..{hi[1]:.2f} m",
            fill=(200, 200, 200))
    im.save(out)
    print("->", out)


if __name__ == "__main__":
    main()
