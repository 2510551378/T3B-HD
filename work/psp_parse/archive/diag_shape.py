"""Are the runs disks, spheres, boxes, or room shells?  Test corner-vs-centre occupancy."""
import math
import os
import struct
import sys

DIR = os.path.join(os.path.dirname(__file__), "..", "raw", "packs")


def load(fn):
    with open(os.path.join(DIR, fn), "rb") as f:
        return f.read()


def pca_plane(P):
    n = len(P)
    mean = [sum(p[i] for p in P) / n for i in range(3)]
    C = [[sum((p[i] - mean[i]) * (p[j] - mean[j]) for p in P) / n for j in range(3)] for i in range(3)]
    # power iteration for the largest eigenvector, then deflate
    def matvec(M, v):
        return [sum(M[i][j] * v[j] for j in range(3)) for i in range(3)]

    def power(M, it=200):
        v = [0.577, 0.577, 0.577]
        for _ in range(it):
            w = matvec(M, v)
            ln = math.sqrt(sum(x * x for x in w)) or 1
            v = [x / ln for x in w]
        lam = sum(v[i] * matvec(M, v)[i] for i in range(3))
        return lam, v

    l1, v1 = power(C)
    D = [[C[i][j] - l1 * v1[i] * v1[j] for j in range(3)] for i in range(3)]
    l2, v2 = power(D)
    v3 = [v1[1] * v2[2] - v1[2] * v2[1], v1[2] * v2[0] - v1[0] * v2[2], v1[0] * v2[1] - v1[1] * v2[0]]
    return mean, v1, v2, v3, math.sqrt(max(l1, 0)), math.sqrt(max(l2, 0))


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

    for ri in range(4):
        r = runs[ri]
        P = [struct.unpack_from("<3h", geo, o + 4) for o in r]
        mean, v1, v2, v3, s1, s2 = pca_plane(P)
        U = [sum((p[i] - mean[i]) * v1[i] for i in range(3)) for p in P]
        V = [sum((p[i] - mean[i]) * v2[i] for i in range(3)) for p in P]
        W = [sum((p[i] - mean[i]) * v3[i] for i in range(3)) for p in P]
        um, uM = min(U), max(U)
        vm, vM = min(V), max(V)
        # corner occupancy: 4 corner quadrants of the (U,V) bbox
        corners = [0, 0, 0, 0]
        inside_circle = 0
        rmax = 0
        for u, v in zip(U, V):
            cu = 0 if (u - um) < (uM - um) / 2 else 1
            cv = 0 if (v - vm) < (vM - vm) / 2 else 1
            corners[cv * 2 + cu] += 1
            rmax = max(rmax, math.hypot(u, v))
        for u, v in zip(U, V):
            if math.hypot(u, v) < 0.707 * rmax:
                inside_circle += 1
        n = len(P)
        print(f"run {ri}: n={n}")
        print(f"   axes  U(range {uM-um:.0f}) V({vM-vm:.0f}) W({max(W)-min(W):.0f})  "
              f"depth/extent={ (max(W)-min(W))/max(uM-um,vM-vm,1):.3f}")
        print(f"   corner quadrants {corners}  (square => all similar, disk => centre-heavy)")
        print(f"   points inside 0.707*rmax = {100.0*inside_circle/n:.1f}%  (disk ~50%, ring ~0%)")
        # radial histogram
        bins = [0] * 5
        for u, v in zip(U, V):
            t = math.hypot(u, v) / (rmax or 1)
            bins[min(4, int(t * 5))] += 1
        print(f"   radial bins (0-1) {[round(100.0*b/n) for b in bins]}")


if __name__ == "__main__":
    main()
