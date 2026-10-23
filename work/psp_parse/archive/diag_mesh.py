"""Diagnose why the exported meshes look wrong.

Checks
  1. is there a 16-bit or 32-bit index buffer anywhere in the vertex section?
  2. how good is the current "3 consecutive vertices = 1 triangle" grouping
     (edge lengths, aspect ratios, surface area vs bbox)
  3. how do alternative groupings compare (strip, quad, random shuffle baseline)
"""
import math
import os
import struct
import sys

ROOT = r"C:\Users\25105\Documents\寄生前夜第四日"
ISO = os.path.join(ROOT, r"PSP\The_3rd_birthday_cn_full_v101.iso")
SEC = 2048
PKG_LBA, PKG_SIZE = 59600, 1344292864
DIR = os.path.join(os.path.dirname(__file__), "..", "raw", "packs")
SCALE = 3.125 / 32768.0


def load(fn):
    with open(os.path.join(DIR, fn), "rb") as f:
        return f.read()


def tri_stats(pts, faces):
    edges = []
    area = 0.0
    thin = 0
    for a, b, c in faces:
        A, B, C = pts[a], pts[b], pts[c]
        e = [math.dist(A, B), math.dist(B, C), math.dist(C, A)]
        edges.extend(e)
        s = sum(e) / 2
        ar = s * (s - e[0]) * (s - e[1]) * (s - e[2])
        area += math.sqrt(ar) if ar > 0 else 0.0
        if min(e) > 0 and max(e) / min(e) > 20:
            thin += 1
    edges.sort()
    n = len(edges)
    return {
        "n": len(faces),
        "min": edges[0], "p50": edges[n // 2], "p95": edges[int(n * 0.95)], "max": edges[-1],
        "thin_pct": 100.0 * thin / max(1, len(faces)),
        "area": area,
    }


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    t8 = load("t8_a_0x444e5000.pack")
    sec = t8[0x80:0x80 + 0x37250]
    geo = sec[0x30:0x225E8]
    verts = [o for o in range(0, len(geo) - 20, 2) if geo[o + 10:o + 12] == b"\xcc\xcc"]
    runs = []
    cur = [verts[0]]
    for o in verts[1:]:
        if o - cur[-1] == 20:
            cur.append(o)
        else:
            runs.append(cur)
            cur = [o]
    runs.append(cur)
    runs.sort(key=len, reverse=True)
    print(f"records {len(verts)}, runs {len(runs)}, biggest run {len(runs[0])}")

    # ---- 1. index buffers anywhere?
    print("\n[1] index-buffer search over the whole section")
    for width, fmt in ((2, "H"), (4, "I")):
        best = []
        step = 32
        win = 512
        for off in range(0, len(sec) - win * width, step):
            vals = struct.unpack_from(f"<{win}{fmt}", sec, off)
            mx = max(vals)
            if mx == 0 or mx > 12000:
                continue
            uniq = len(set(vals))
            if uniq < win * 0.2:
                continue
            best.append((uniq / win, off, mx))
        best.sort(reverse=True)
        print(f"  u{width*8}: {len(best)} windows with max<=12000 and >=20% distinct")
        for frac, off, mx in best[:4]:
            print(f"     @0x{off:06x} distinct={frac:.2f} max={mx}")

    # ---- 2/3. grouping quality
    print("\n[2] current grouping (3 consecutive) on the biggest run")
    r = runs[0]
    pts = []
    for off in r:
        x, y, z = struct.unpack_from("<3h", geo, off + 4)
        pts.append((x * SCALE, y * SCALE, z * SCALE))
    n3 = len(pts) // 3 * 3
    faces = [(i, i + 1, i + 2) for i in range(0, n3, 3)]
    s = tri_stats(pts, faces)
    print(f"  tris={s['n']} edge p50={s['p50']:.3f} p95={s['p95']:.3f} max={s['max']:.3f} m")
    print(f"  needle tris (>20:1) = {s['thin_pct']:.1f}%   area={s['area']:.1f} m2")

    print("\n[3] alternatives on the same run")
    variants = {}
    variants["strip"] = [(i, i + 1, i + 2) for i in range(0, n3 - 2)]
    variants["quad-ish"] = [(i, i + 1, i + 2) for i in range(0, n3, 4)]
    import random
    random.seed(1)
    idx = list(range(n3))
    random.shuffle(idx)
    variants["shuffled"] = [(idx[i], idx[i + 1], idx[i + 2]) for i in range(0, n3 - 2, 3)]
    for name, f in variants.items():
        s = tri_stats(pts, f)
        print(f"  {name:<9} tris={s['n']:>5} p50={s['p50']:.3f} max={s['max']:>7.2f} "
              f"needle={s['thin_pct']:>5.1f}% area={s['area']:>9.1f}")


if __name__ == "__main__":
    main()
