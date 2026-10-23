"""Weld by position, then check manifoldness / winding consistency of the exported grouping."""
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


def analyse(geo, tag):
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
    for off in geo_runs(runs):
        p = struct.unpack_from("<3h", geo, off + 4)
        if p not in weld:
            weld[p] = len(pos)
            pos.append(p)
    tris = []
    for r in runs:
        if len(r) % 3:
            continue
        for k in range(0, len(r), 3):
            a, b, c = [weld[struct.unpack_from("<3h", geo, r[k + i] + 4)] for i in range(3)]
            if a != b and b != c and a != c:
                tris.append((a, b, c))
    print(f"\n{tag}: {len(pos)} welded verts, {len(tris)} tris")
    edge = collections.Counter()
    for a, b, c in tris:
        for u, v in ((a, b), (b, c), (c, a)):
            edge[(min(u, v), max(u, v))] += 1
    cnt = collections.Counter(edge.values())
    print("  edge use counts:", dict(sorted(cnt.items())))
    closed = sum(1 for v in edge.values() if v == 2)
    print(f"  edges used twice: {closed}/{len(edge)} = {100.0*closed/len(edge):.1f}%")
    # winding: adjacent faces should traverse the shared edge in opposite directions
    dirn = collections.defaultdict(int)
    bad = good = 0
    for a, b, c in tris:
        for u, v in ((a, b), (b, c), (c, a)):
            k = (min(u, v), max(u, v))
            dirn[(k, u, v)] += 1
    for a, b, c in tris:
        for u, v in ((a, b), (b, c), (c, a)):
            k = (min(u, v), max(u, v))
            if edge[k] == 2:
                if dirn[(k, v, u)] > 0:
                    good += 1
                else:
                    bad += 1
    tot = good + bad
    print(f"  consistent-winding edges: {100.0*good/max(1,tot):.1f}% ({good}/{tot})")
    # components
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
    comps = collections.Counter(find(i) for i in range(len(pos)))
    used = [i for i in range(len(pos)) if any(i in t for t in ())]
    print(f"  connected components (by shared welded vertex): {len(comps)}")


def geo_runs(runs):
    for r in runs:
        for off in r:
            yield off


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    t8 = load("t8_a_0x444e5000.pack")
    sec = t8[0x80:0x80 + 0x37250]
    analyse(sec[0x30:0x225E8], "t8_a whole pool")


if __name__ == "__main__":
    main()
