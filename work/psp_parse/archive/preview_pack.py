"""Render a pack directly from the ISO using baked vertex colours (RGBA in the record)."""
import math
import os
import struct
import sys

import numpy as np
from PIL import Image

ROOT = r"C:\Users\25105\Documents\寄生前夜第四日"
ISO = os.path.join(ROOT, r"PSP\The_3rd_birthday_cn_full_v101.iso")
SEC = 2048
PKG_LBA, PKG_SIZE = 59600, 1344292864
SCALE = 3.125 / 32768.0
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tools"))
from psp_pack import parse_pack, iter_pack_offsets, open_pack  # noqa: E402
from pack_export import find_runs  # noqa: E402


def load_pack(pack_off):
    with open(ISO, "rb") as f:
        offs = iter_pack_offsets(f)
        i = offs.index(pack_off)
        span = (offs[i + 1] if i + 1 < len(offs) else PKG_SIZE) - pack_off
        buf = open_pack(f, pack_off, span)
        p = parse_pack(buf, pack_off, span)
        big = max(p.sections, key=lambda s: s[0])
        return buf[big[1]:big[1] + big[0]]


def extract(blob):
    runs = [r for r in find_runs(blob) if len(r) >= 3 and len(r) % 3 == 0]
    V = []
    C = []
    F = []
    for r in runs:
        base = len(V)
        for off in r:
            x, y, z = struct.unpack_from("<3h", blob, off + 4)
            V.append((x * SCALE, y * SCALE, z * SCALE))
            C.append(tuple(blob[off:off + 3]))
        for k in range(0, len(r), 3):
            F.append((base + k, base + k + 1, base + k + 2))
    return np.array(V), np.array(C, dtype=np.float64) / 255.0, np.array(F)


def render(V, C, F, size=800, yaw=35.0, pitch=22.0, path="out.png"):
    c = (V.max(axis=0) + V.min(axis=0)) / 2
    ext = float((V.max(axis=0) - V.min(axis=0)).max()) or 1.0
    P = (V - c) / ext
    ay, ap = math.radians(yaw), math.radians(pitch)
    Ry = np.array([[math.cos(ay), 0, math.sin(ay)], [0, 1, 0], [-math.sin(ay), 0, math.cos(ay)]])
    Rx = np.array([[1, 0, 0], [0, math.cos(ap), -math.sin(ap)], [0, math.sin(ap), math.cos(ap)]])
    P = P @ Ry.T @ Rx.T
    P[:, 2] -= 3.0
    focal = 3.0
    sx = P[:, 0] * focal / (-P[:, 2]) * size * 0.5 + size * 0.5
    sy = -P[:, 1] * focal / (-P[:, 2]) * size * 0.5 + size * 0.5
    depth = -P[:, 2]
    lo, hi = np.array([sx.min(), sy.min()]), np.array([sx.max(), sy.max()])
    k = size * 0.88 / max(float((hi - lo).max()), 1e-9)
    mid = (lo + hi) / 2
    sx = (sx - mid[0]) * k + size * 0.5
    sy = (sy - mid[1]) * k + size * 0.5

    n = np.cross(P[F[:, 1]] - P[F[:, 0]], P[F[:, 2]] - P[F[:, 0]])
    ln = np.linalg.norm(n, axis=1)
    ln[ln == 0] = 1
    n = n / ln[:, None]
    light = np.array([0.3, 0.6, 0.75])
    light /= np.linalg.norm(light)
    lam = np.abs(n @ light)
    shade = 0.35 + 0.65 * lam

    img = np.zeros((size, size, 3))
    zbuf = np.full((size, size), 1e9)
    for fi in np.argsort(-depth[F].mean(axis=1)):
        a, b, cc = F[fi]
        xs = np.array([sx[a], sx[b], sx[cc]])
        ys = np.array([sy[a], sy[b], sy[cc]])
        zs = np.array([depth[a], depth[b], depth[cc]])
        x0, x1 = int(max(0, xs.min())), int(min(size - 1, xs.max()))
        y0, y1 = int(max(0, ys.min())), int(min(size - 1, ys.max()))
        if x1 <= x0 or y1 <= y0:
            continue
        d = (ys[1] - ys[2]) * (xs[0] - xs[2]) + (xs[2] - xs[1]) * (ys[0] - ys[2])
        if abs(d) < 1e-9:
            continue
        gx, gy = np.meshgrid(np.arange(x0, x1 + 1), np.arange(y0, y1 + 1))
        w0 = ((ys[1] - ys[2]) * (gx - xs[2]) + (xs[2] - xs[1]) * (gy - ys[2])) / d
        w1 = ((ys[2] - ys[0]) * (gx - xs[2]) + (xs[0] - xs[2]) * (gy - ys[2])) / d
        w2 = 1 - w0 - w1
        inside = (w0 >= -1e-6) & (w1 >= -1e-6) & (w2 >= -1e-6)
        if not inside.any():
            continue
        z = w0 * zs[0] + w1 * zs[1] + w2 * zs[2]
        sub = zbuf[y0:y1 + 1, x0:x1 + 1]
        closer = inside & (z < sub)
        if not closer.any():
            continue
        sub[closer] = z[closer]
        col = (w0[..., None] * C[a] + w1[..., None] * C[b] + w2[..., None] * C[cc]) * shade[fi]
        img[y0:y1 + 1, x0:x1 + 1][closer] = np.clip(col, 0, 1)[closer]

    out = (np.clip(img, 0, 1) ** (1 / 1.6) * 255).astype(np.uint8)
    Image.fromarray(out, mode="RGB").save(path)
    return path


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    pack = int(sys.argv[1], 0) if len(sys.argv) > 1 else 0x444e5000
    out = sys.argv[2] if len(sys.argv) > 2 else "preview.png"
    blob = load_pack(pack)
    V, C, F = extract(blob)
    print(f"pack 0x{pack:08x}: {len(V)} verts, {len(F)} tris")
    render(V, C, F, path=out)
    print("->", out)


if __name__ == "__main__":
    main()
