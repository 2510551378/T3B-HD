"""render_obj.py -- tiny software renderer (no deps beyond numpy/Pillow).

usage:
    python render_obj.py <file.obj> <out.png> [--view iso|front|top|side] [--size 900]
                         [--max-tris N]
"""
import math
import os
import sys

import numpy as np
from PIL import Image

VIEWS = {
    "front": (0.0, 0.0),
    "side": (90.0, 0.0),
    "top": (0.0, 89.9),
    "iso": (35.0, 25.0),
    "iso2": (-40.0, 20.0),
}


def load_obj(path, max_tris=None):
    verts = []
    faces = []
    with open(path, "r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            if line.startswith("v "):
                p = line.split()
                verts.append((float(p[1]), float(p[2]), float(p[3])))
            elif line.startswith("f "):
                idx = [int(t.split("/")[0]) - 1 for t in line.split()[1:]]
                for k in range(1, len(idx) - 1):
                    faces.append((idx[0], idx[k], idx[k + 1]))
                if max_tris and len(faces) >= max_tris:
                    break
    return np.asarray(verts, dtype=np.float64), np.asarray(faces, dtype=np.int64)


def main(argv):
    src = argv[1]
    dst = argv[2]
    view = "iso"
    size = 900
    max_tris = None
    for i, a in enumerate(argv):
        if a == "--view":
            view = argv[i + 1]
        elif a == "--size":
            size = int(argv[i + 1])
        elif a == "--max-tris":
            max_tris = int(argv[i + 1])
    V, F = load_obj(src, max_tris)
    if len(F) == 0:
        raise SystemExit("no faces")
    c = (V.max(axis=0) + V.min(axis=0)) / 2
    ext = float((V.max(axis=0) - V.min(axis=0)).max()) or 1.0
    P = (V - c) / ext

    yaw, pitch = VIEWS.get(view, VIEWS["iso"])
    ay, ap = math.radians(yaw), math.radians(pitch)
    Ry = np.array([[math.cos(ay), 0, math.sin(ay)], [0, 1, 0], [-math.sin(ay), 0, math.cos(ay)]])
    Rx = np.array([[1, 0, 0], [0, math.cos(ap), -math.sin(ap)], [0, math.sin(ap), math.cos(ap)]])
    P = P @ Ry.T @ Rx.T

    # camera looks down -Z after rotation; shift so it is in front
    P[:, 2] -= 2.6
    focal = 2.4
    sx = P[:, 0] * focal / (-P[:, 2]) * size * 0.5 + size * 0.5
    sy = -P[:, 1] * focal / (-P[:, 2]) * size * 0.5 + size * 0.5
    depth = -P[:, 2]
    # auto-fit: rescale about the image centre so the projected bbox fills the frame
    lo = np.array([sx.min(), sy.min()])
    hi = np.array([sx.max(), sy.max()])
    span = float(max(hi - lo).max()) if max(hi - lo) > 1e-9 else 1.0
    k = size * 0.86 / span
    mid = (lo + hi) / 2
    sx = (sx - mid[0]) * k + size * 0.5
    sy = (sy - mid[1]) * k + size * 0.5

    norm = np.cross(P[F[:, 1]] - P[F[:, 0]], P[F[:, 2]] - P[F[:, 0]])
    ln = np.linalg.norm(norm, axis=1)
    ln[ln == 0] = 1
    norm = norm / ln[:, None]
    light = np.array([0.35, 0.55, 0.75])
    light = light / np.linalg.norm(light)
    shade = np.abs(norm @ light)
    shade = 0.18 + 0.82 * shade

    img = np.zeros((size, size), dtype=np.float64)
    zbuf = np.full((size, size), 1e9, dtype=np.float64)
    order = np.argsort(-depth[F].mean(axis=1))
    for fi in order:
        a, b, cc = F[fi]
        xs = np.array([sx[a], sx[b], sx[cc]])
        ys = np.array([sy[a], sy[b], sy[cc]])
        zs = np.array([depth[a], depth[b], depth[cc]])
        x0, x1 = int(max(0, np.floor(xs.min()))), int(min(size - 1, np.ceil(xs.max())))
        y0, y1 = int(max(0, np.floor(ys.min()))), int(min(size - 1, np.ceil(ys.max())))
        if x1 < x0 or y1 < y0:
            continue
        d = (ys[1] - ys[2]) * (xs[0] - xs[2]) + (xs[2] - xs[1]) * (ys[0] - ys[2])
        if abs(d) < 1e-9:
            continue
        gx, gy = np.meshgrid(np.arange(x0, x1 + 1), np.arange(y0, y1 + 1))
        w0 = ((ys[1] - ys[2]) * (gx - xs[2]) + (xs[2] - xs[1]) * (gy - ys[2])) / d
        w1 = ((ys[2] - ys[0]) * (gx - xs[2]) + (xs[0] - xs[2]) * (gy - ys[2])) / d
        w2 = 1.0 - w0 - w1
        inside = (w0 >= -1e-6) & (w1 >= -1e-6) & (w2 >= -1e-6)
        if not inside.any():
            continue
        z = w0 * zs[0] + w1 * zs[1] + w2 * zs[2]
        sub_z = zbuf[y0:y1 + 1, x0:x1 + 1]
        closer = inside & (z < sub_z)
        if not closer.any():
            continue
        sub_z[closer] = z[closer]
        img[y0:y1 + 1, x0:x1 + 1][closer] = shade[fi]

    img = np.clip(img, 0, 1) ** (1 / 1.6)
    out = (img * 255).astype(np.uint8)
    Image.fromarray(out, mode="L").save(dst)
    print(f"{os.path.basename(src)}: {len(V)} verts, {len(F)} tris -> {dst} ({view})")


if __name__ == "__main__":
    main(sys.argv)
