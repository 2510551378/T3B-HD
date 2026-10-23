"""gpu_verts.py -- find GE-format vertex buffers in a RAM image.

The frame dump proved the GPU layout is

    uv f32 x2 @0   colour RGBA @8   position s16 x3 @12   pad CC CC @18

so a vertex buffer shows the 0xCCCC marker at +18, not at +10 like the on-disc format.
"""
import struct
import sys

import numpy as np

SC = 3.125 / 32768.0


def find_runs(blob, min_len=20):
    marks = [o for o in range(0, len(blob) - 20, 2)
             if blob[o + 18:o + 20] == b"\xcc\xcc"]
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
    return [r for r in out if len(r) >= min_len]


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    blob = open(sys.argv[1], "rb").read()
    runs = find_runs(blob)
    total = sum(len(r) for r in runs)
    print(f"{sys.argv[1]}: {len(blob):,} bytes -> {len(runs)} GPU-format runs, "
          f"{total} vertices")
    if not runs:
        return
    runs.sort(key=len, reverse=True)
    print(f"{'#':>3} {'verts':>6}  {'dims (sorted, m)':<24} {'medstep':>8}  colour")
    people = []
    for i, r in enumerate(runs[:20]):
        P = np.array([struct.unpack_from("<3h", blob, o + 12) for o in r],
                     dtype=np.float64) * SC
        C = [tuple(blob[o + 8:o + 12]) for o in r]
        ext = np.sort(P.max(axis=0) - P.min(axis=0))
        d = np.linalg.norm(np.diff(P, axis=0), axis=1) if len(P) > 1 else np.array([0])
        med = float(np.median(d))
        r0 = sorted(c[0] for c in C)[len(C) // 2]
        g0 = sorted(c[1] for c in C)[len(C) // 2]
        b0 = sorted(c[2] for c in C)[len(C) // 2]
        person = (1.2 <= ext[2] <= 2.2 and ext[1] >= 0.12 and ext[0] <= 1.2
                  and ext[2] >= 1.5 * ext[1])
        if person:
            people.append((len(r), r, P, ext))
        print(f"{i:>3} {len(r):>6}  {ext[2]:5.2f} x {ext[1]:5.2f} x {ext[0]:5.2f}      "
              f"{med:8.3f}  ({r0},{g0},{b0}){'  <== person?' if person else ''}")
    print(f"\nperson-shaped runs: {len(people)}")


if __name__ == "__main__":
    main()
