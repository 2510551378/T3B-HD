"""run_colors.py -- describe each vertex run in a dump/RAM blob: colours and UV ranges.

Walls are grey/beige with tiling UVs (0..4); character parts carry skin / cloth colours and
usually stay inside a single UV tile.
"""
import os
import struct
import sys

SCALE = 3.125 / 32768.0


def runs(blob):
    marks = [o for o in range(0, len(blob) - 20, 2) if blob[o + 10:o + 12] == b"\xcc\xcc"]
    out = []
    if not marks:
        return out
    cur = [marks[0]]
    for o in marks[1:]:
        if o - cur[-1] == 20:
            cur.append(o)
        else:
            out.append(cur)
            cur = [o]
    out.append(cur)
    return [r for r in out if len(r) >= 3]


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    blob = open(sys.argv[1], "rb").read()
    rs = sorted(runs(blob), key=len, reverse=True)
    print(f"{len(rs)} runs")
    print(f"{'#':>3} {'verts':>6}  {'dominant colour':>18}  {'sat':>5}  UV u        v")
    for i, r in enumerate(rs[:16]):
        cols = [(blob[o], blob[o + 1], blob[o + 2]) for o in r[:400]]
        # dominant colour = median
        rr = sorted(c[0] for c in cols)[len(cols) // 2]
        gg = sorted(c[1] for c in cols)[len(cols) // 2]
        bb = sorted(c[2] for c in cols)[len(cols) // 2]
        mx, mn = max(rr, gg, bb), min(rr, gg, bb)
        sat = 0 if mx == 0 else (mx - mn) / mx
        U = [struct.unpack_from("<f", blob, o + 12)[0] for o in r]
        V = [struct.unpack_from("<f", blob, o + 16)[0] for o in r]
        print(f"{i:>3} {len(r):>6}  ({rr:3d},{gg:3d},{bb:3d})         {sat:5.2f}  "
              f"{min(U):5.2f}..{max(U):5.2f}  {min(V):5.2f}..{max(V):5.2f}")


if __name__ == "__main__":
    main()
