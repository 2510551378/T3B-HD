"""cloud_render.py -- orthographic point-cloud projections of decoded vertex blocks.

Rendering triangles assumes we know the index/strip order, which we do not.  A point cloud
needs no topology: if a block is a character, the front and side silhouettes show a body.

    python cloud_render.py <dump.ppdmp> <out.png> [--cmds 121,218]
"""
import os
import struct
import sys

import numpy as np
from PIL import Image, ImageDraw

sys.path.insert(0, r"work\psp_parse\archive")
from ppdmp2 import read  # noqa: E402
from dump_all import best_layout  # noqa: E402

SC = 3.125 / 32768.0


def draw_cloud(dr, P, box, size, colour):
    lo, hi = box
    span = max(hi - lo)
    if span <= 0:
        return
    scale = (size - 8) / span
    ox, oy = lo[0], lo[1]
    for p in P:
        px = int((p[0] - ox) * scale) + 4
        py = size - int((p[1] - oy) * scale) - 4
        if 0 <= px < size and 0 <= py < size:
            dr.point((px, py), fill=colour)


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    src, out = sys.argv[1], sys.argv[2]
    only = None
    for i, a in enumerate(sys.argv):
        if a == "--cmds":
            only = {int(x) for x in sys.argv[i + 1].split(",")}

    cmds, buf = read(src)
    tiles = []
    for i, (t, sz, ptr) in enumerate(cmds):
        if t != 2 or sz < 96 or ptr + sz > len(buf):
            continue
        if only and i not in only:
            continue
        blk = buf[ptr:ptr + sz]
        r = best_layout(blk)
        if not r:
            continue
        rank, stride, dt, off, cnt, med, ext, P = r
        tiles.append((i, cnt, ext, P))
    if only:
        # keep the requested order
        order = {c: k for k, c in enumerate(sorted(only))}
        tiles.sort(key=lambda t: order.get(t[0], 999))

    if not tiles:
        print("no blocks")
        return

    size = 300
    cols = min(4, len(tiles))
    rows = (len(tiles) + cols - 1) // cols
    sheet = Image.new("RGB", (size * cols, size * rows + 22), (12, 12, 14))
    dr = ImageDraw.Draw(sheet)
    dr.text((6, 5), "orthographic point clouds: X/Y (front) then X/Z (top) overlay", fill=(230, 230, 230))
    for k, (i, cnt, ext, P) in enumerate(tiles):
        x = (k % cols) * size
        y = 22 + (k // cols) * size
        # front: X horizontal, Y vertical
        dr.rectangle([x, y, x + size - 1, y + size - 1], outline=(40, 40, 44))
        for P2, col in ((P, (255, 120, 120)),):
            lo = P2.min(axis=0)
            hi = P2.max(axis=0)
            dr_lo = lo[[0, 1]]
            dr_hi = hi[[0, 1]]
            span = max(dr_hi - dr_lo)
            if span <= 0:
                continue
            s = (size - 10) / span
            for p in P2:
                px = int((p[0] - dr_lo[0]) * s) + 5
                py = size - int((p[1] - dr_lo[1]) * s) - 5
                if 0 <= px < size and 0 <= py < size:
                    dr.point((x + px, y + py), fill=col)
        dr.text((x + 4, y + 4), f"cmd{i} {cnt}v {ext[2]:.2f}m", fill=(210, 210, 210))
    sheet.save(out)
    print("->", out, sheet.size, f"({len(tiles)} tiles)")


if __name__ == "__main__":
    main()
