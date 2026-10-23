"""Per-component size/shape of the welded mesh -- is it a coherent room or scattered debris?"""
import collections
import math
import os
import struct
import sys

DIR = os.path.join(os.path.dirname(__file__), "..", "raw", "packs")
SCALE = 3.125 / 32768.0


def load(fn):
    with open(os.path.join(DIR, fn), "rb") as f:
        return f.read()


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

    weld = {}
    pos = []
    tris = []
    for r in runs:
        if len(r) % 3:
            continue
        for k in range(0, len(r), 3):
            ids = []
            for i in range(3):
                p = struct.unpack_from("<3h", geo, r[k + i] + 4)
                if p not in weld:
                    weld[p] = len(pos)
                    pos.append(p)
                ids.append(weld[p])
            if len(set(ids)) == 3:
                tris.append(tuple(ids))

    parent = list(range(len(pos)))

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(x, y):
        x, y = find(x), find(y)
        if x != y:
            parent[x] = y

    for a, b, c in tris:
        union(a, b)
        union(b, c)
    groups = collections.defaultdict(list)
    for a, b, c in tris:
        groups[find(a)].append((a, b, c))
    print(f"{len(pos)} welded verts, {len(tris)} tris, {len(groups)} components")
    rows = []
    for root, ts in groups.items():
        vs = set()
        for t in ts:
            vs.update(t)
        xs = [pos[v][0] * SCALE for v in vs]
        ys = [pos[v][1] * SCALE for v in vs]
        zs = [pos[v][2] * SCALE for v in vs]
        rows.append((len(ts), len(vs),
                     max(xs) - min(xs), max(ys) - min(ys), max(zs) - min(zs),
                     min(xs), max(xs), min(ys), max(ys)))
    rows.sort(reverse=True)
    print(f"{'tris':>6} {'verts':>6} {'dx':>7} {'dy':>7} {'dz':>7}   x-range        y-range")
    for r in rows[:12]:
        print(f"{r[0]:>6} {r[1]:>6} {r[2]:>7.2f} {r[3]:>7.2f} {r[4]:>7.2f}   "
              f"{r[5]:6.2f}..{r[6]:6.2f}  {r[7]:6.2f}..{r[8]:6.2f}")
    big = sum(r[0] for r in rows[:3])
    print(f"\ntop-3 components hold {100.0*big/len(tris):.1f}% of triangles")


if __name__ == "__main__":
    main()
