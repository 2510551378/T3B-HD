"""Contact sheet: one thumbnail per pack so a human can say what these actually are."""
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

TW, TH = 240, 180


def render(V, F, C, size=(TW, TH), yaw=38.0, pitch=26.0):
    W, H = size
    c = (V.max(axis=0) + V.min(axis=0)) / 2
    ext = float((V.max(axis=0) - V.min(axis=0)).max()) or 1.0
    P = (V - c) / ext
    ay, ap = math.radians(yaw), math.radians(pitch)
    Ry = np.array([[math.cos(ay), 0, math.sin(ay)], [0, 1, 0], [-math.sin(ay), 0, math.cos(ay)]])
    Rx = np.array([[1, 0, 0], [0, math.cos(ap), -math.sin(ap)], [0, math.sin(ap), math.cos(ap)]])
    P = P @ Ry.T @ Rx.T
    P[:, 2] -= 3.0
    f = 3.0
    sx = P[:, 0] * f / (-P[:, 2]) * W * 0.5 + W * 0.5
    sy = -P[:, 1] * f / (-P[:, 2]) * H * 0.5 + H * 0.5
    d = -P[:, 2]
    lo, hi = np.array([sx.min(), sy.min()]), np.array([sx.max(), sy.max()])
    k = min(W, H) * 0.88 / max(float((hi - lo).max()), 1e-9)
    mid = (lo + hi) / 2
    sx = (sx - mid[0]) * k + W * 0.5
    sy = (sy - mid[1]) * k + H * 0.5

    n = np.cross(P[F[:, 1]] - P[F[:, 0]], P[F[:, 2]] - P[F[:, 0]])
    ln = np.linalg.norm(n, axis=1)
    ln[ln == 0] = 1
    n = n / ln[:, None]
    light = np.array([0.3, 0.6, 0.75])
    light /= np.linalg.norm(light)
    shade = 0.3 + 0.7 * np.abs(n @ light)

    img = np.zeros((H, W, 3))
    zb = np.full((H, W), 1e9)
    for fi in np.argsort(-d[F].mean(axis=1)):
        a, b, cc = F[fi]
        xs = np.array([sx[a], sx[b], sx[cc]])
        ys = np.array([sy[a], sy[b], sy[cc]])
        zs = np.array([d[a], d[b], d[cc]])
        x0, x1 = int(max(0, xs.min())), int(min(W - 1, xs.max()))
        y0, y1 = int(max(0, ys.min())), int(min(H - 1, ys.max()))
        if x1 <= x0 or y1 <= y0:
            continue
        den = (ys[1] - ys[2]) * (xs[0] - xs[2]) + (xs[2] - xs[1]) * (ys[0] - ys[2])
        if abs(den) < 1e-9:
            continue
        gx, gy = np.meshgrid(np.arange(x0, x1 + 1), np.arange(y0, y1 + 1))
        w0 = ((ys[1] - ys[2]) * (gx - xs[2]) + (xs[2] - xs[1]) * (gy - ys[2])) / den
        w1 = ((ys[2] - ys[0]) * (gx - xs[2]) + (xs[0] - xs[2]) * (gy - ys[2])) / den
        w2 = 1 - w0 - w1
        ins = (w0 >= -1e-6) & (w1 >= -1e-6) & (w2 >= -1e-6)
        if not ins.any():
            continue
        z = w0 * zs[0] + w1 * zs[1] + w2 * zs[2]
        sub = zb[y0:y1 + 1, x0:x1 + 1]
        cl = ins & (z < sub)
        if not cl.any():
            continue
        sub[cl] = z[cl]
        col = (w0[..., None] * C[a] + w1[..., None] * C[b] + w2[..., None] * C[cc]) * shade[fi]
        img[y0:y1 + 1, x0:x1 + 1][cl] = np.clip(col, 0, 1)[cl]
    return (np.clip(img, 0, 1) ** (1 / 1.5) * 255).astype(np.uint8)


def pack_geom(f, off, offs):
    i = offs.index(off)
    span = (offs[i + 1] if i + 1 < len(offs) else PKG_SIZE) - off
    buf = open_pack(f, off, span)
    p = parse_pack(buf, off, span)
    if not p.sections:
        return None
    big = max(p.sections, key=lambda s: s[0])
    blob = buf[big[1]:big[1] + big[0]]
    if struct.unpack_from("<I", blob, 4)[0] != 0x3002:
        return None
    runs = [r for r in find_runs(blob) if len(r) >= 3 and len(r) % 3 == 0]
    if not runs:
        return None
    V, C, F = [], [], []
    for r in runs:
        base = len(V)
        for o in r:
            x, y, z = struct.unpack_from("<3h", blob, o + 4)
            V.append((x * SCALE, y * SCALE, z * SCALE))
            C.append((blob[o] / 255.0, blob[o + 1] / 255.0, blob[o + 2] / 255.0))
        for k in range(0, len(r), 3):
            F.append((base + k, base + k + 1, base + k + 2))
    return np.array(V), np.array(F), np.array(C)


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    out = sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, "work", "psp_parse", "out", "preview", "sheet.png")
    cols = 10
    tiles = []
    with open(ISO, "rb") as f:
        offs = iter_pack_offsets(f)
        for off in offs:
            g = pack_geom(f, off, offs)
            if not g:
                continue
            V, F, C = g
            im = render(V, F, C)
            img = Image.fromarray(im, mode="RGB")
            dr = ImageDraw.Draw(img)
            dr.text((4, 3), f"0x{off:08x}", fill=(220, 220, 220))
            dr.text((4, TH - 13), f"{len(F)} tris", fill=(160, 160, 160))
            tiles.append(img)
            print(f"  {off:#010x} rendered ({len(F)} tris)", flush=True)

    rows = math.ceil(len(tiles) / cols)
    sheet = Image.new("RGB", (cols * TW, rows * TH), (14, 15, 18))
    for k, t in enumerate(tiles):
        sheet.paste(t, ((k % cols) * TW, (k // cols) * TH))
    for x in range(1, cols):
        for y in range(rows * TH):
            sheet.putpixel((x * TW, y), (40, 42, 48))
    sheet.save(out)
    print(f"{len(tiles)} packs -> {out} ({sheet.width}x{sheet.height})")


if __name__ == "__main__":
    main()
