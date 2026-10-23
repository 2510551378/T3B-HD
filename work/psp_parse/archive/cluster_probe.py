"""cluster_probe.py -- cluster a candidate animated vertex buffer and look for human-sized
clusters.

The differential scan of the savestate showed 0x016a7000..0x016ab000 being rewritten every
frame with clean s16 structure.  If a character is CPU-skinned into that buffer, she shows up
as a dense cluster roughly 1.6-1.8 m tall standing on the floor plane.
"""
import struct
import sys

import numpy as np

SC = 3.125 / 32768.0


def cluster(P, cell=0.25):
    """Grid-based single-linkage clustering (fast, good enough for a point cloud)."""
    key = np.floor(P / cell).astype(np.int64)
    groups = {}
    for i, k in enumerate(map(tuple, key)):
        groups.setdefault(k, []).append(i)
    # union adjacent occupied cells
    parent = {k: k for k in groups}

    def find(a):
        while parent[a] != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a

    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[rb] = ra

    for k in list(groups):
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                for dz in (-1, 0, 1):
                    n = (k[0] + dx, k[1] + dy, k[2] + dz)
                    if n in groups:
                        union(k, n)
    out = {}
    for k, idx in groups.items():
        out.setdefault(find(k), []).extend(idx)
    return list(out.values())


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    path = sys.argv[1]
    off = int(sys.argv[2], 0)
    size = int(sys.argv[3], 0)
    stride = int(sys.argv[4]) if len(sys.argv) > 4 else 12
    blob = open(path, "rb").read()
    d = blob[off:off + size]
    n = len(d) // stride
    P = np.array([struct.unpack_from("<3h", d, k * stride) for k in range(n)],
                 dtype=np.float64) * SC
    print(f"{path} @0x{off:08x} {size} B: {n} points")
    ext = np.sort(P.max(axis=0) - P.min(axis=0))
    print(f"whole cloud {ext[2]:.2f} x {ext[1]:.2f} x {ext[0]:.2f} m")

    for cell in (0.15, 0.25, 0.4):
        cl = cluster(P, cell)
        cl.sort(key=len, reverse=True)
        print(f"\ncell {cell}: {len(cl)} clusters")
        for c in cl[:8]:
            Q = P[c]
            e = np.sort(Q.max(axis=0) - Q.min(axis=0))
            tip = ""
            if 1.2 <= e[2] <= 2.2 and e[1] >= 0.12 and e[0] <= 1.2 and e[2] >= 1.5 * e[1]:
                tip = "  <== human-ish"
            print(f"   {len(c):>5} pts  {e[2]:5.2f} x {e[1]:5.2f} x {e[0]:5.2f} m{tip}")


if __name__ == "__main__":
    main()
