"""Render one pack under three up-axis conventions, side by side, so a human can pick."""
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


def render(V, F, C, W=520, H=420, yaw=40.0, pitch=24.0):
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
    k = min(W, H) * 0.9 / max(float((hi - lo).max()), 1e-9)
    mid = (lo + hi) / 2
    sx = (sx - mid[0]) * k + W * 0.5
    sy = (sy - mid[1]) * k + H * 0.5

    n = np.cross(P[F[:, 1]] - P[F[:, 0]], P[F[:, 2]] - P[F[:, 0]])
    ln = np.linalg.norm(n, axis=1)
    ln[ln == 0] = 1
    n = n / ln[:, None]
    light = np.array([0.35, 0.55, 0.75])
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


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    pack = int(sys.argv[1], 0) if len(sys.argv) > 1 else 0x4c199000
    out = sys.argv[2] if len(sys.argv) > 2 else os.path.join(ROOT, "work", "psp_parse", "out", "preview", "axes.png")
    with open(ISO, "rb") as f:
        offs = iter_pack_offsets(f)
        i = offs.index(pack)
        span = (offs[i + 1] if i + 1 < len(offs) else PKG_SIZE) - pack
        buf = open_pack(f, pack, span)
        p = parse_pack(buf, pack, span)
        big = max(p.sections, key=lambda s: s[0])
        blob = buf[big[1]:big[1] + big[0]]
    runs = [r for r in find_runs(blob) if len(r) >= 3 and len(r) % 3 == 0]
    V, C, F = [], [], []
    for r in runs:
        base = len(V)
        for o in r:
            x, y, z = struct.unpack_from("<3h", blob, o + 4)
            V.append((x * SCALE, y * SCALE, z * SCALE))
            C.append((blob[o] / 255.0, blob[o + 1] / 255.0, blob[o + 2] / 255.0))
        for k in range(0, len(r), 3):
            F.append((base + k, base + k + 1, base + k + 2))
    V = np.array(V)
    F = np.array(F)
    C = np.array(C)
    print(f"pack 0x{pack:08x}: {len(V)} verts {len(F)} tris, "
          f"bbox {V.max(axis=0)-V.min(axis=0)}")

    variants = [
        ("Y-up (current: x,y,z)", V.copy()),
        ("Z-up (x,z,y)", V[:, [0, 2, 1]].copy()),
        ("X-up (y,z,x)", V[:, [1, 2, 0]].copy()),
    ]
    W, H = 520, 420
    sheet = Image.new("RGB", (W * len(variants), H + 26), (16, 17, 20))
    dr = ImageDraw.Draw(sheet)
    for k, (name, vv) in enumerate(variants):
        im = Image.fromarray(render(vv, F, C, W, H), mode="RGB")
        sheet.paste(im, (k * W, 26))
        dr.text((k * W + 8, 8), name, fill=(230, 230, 230))
    sheet.save(out)
    print("->", out)


if __name__ == "__main__":
    main()
