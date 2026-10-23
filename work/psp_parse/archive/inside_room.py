"""inside_room.py -- which decoded blocks actually sit inside the room volume.

The 166 stride-20 blocks merge into one coherent room: bbox 5.87 x 1.78 x 5.88 m with the
floor at y = -0.10.  Anything that is part of this scene must fall inside that box, so a block
whose cloud lies inside it is world-space and belongs to the visible set -- which is where the
character has to be.
"""
import sys

import numpy as np

sys.path.insert(0, r"work\psp_parse\archive")
from ppdmp2 import read  # noqa: E402
from dump_all import best_layout  # noqa: E402

ROOM_LO = np.array([-2.85, -0.20, -2.93])
ROOM_HI = np.array([3.22, 1.78, 3.14])


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    cmds, buf = read(sys.argv[1])
    inside = []
    outside = 0
    for i, (t, sz, ptr) in enumerate(cmds):
        if t != 2 or sz < 96 or ptr + sz > len(buf):
            continue
        r = best_layout(buf[ptr:ptr + sz])
        if not r:
            continue
        rank, stride, dt, off, cnt, med, ext, P = r
        lo, hi = P.min(axis=0), P.max(axis=0)
        if np.all(lo >= ROOM_LO) and np.all(hi <= ROOM_HI):
            inside.append((i, cnt, ext, lo, hi, P, stride, dt))
        else:
            outside += 1
    print(f"{len(inside)} blocks wholly inside the room volume, {outside} outside")
    inside.sort(key=lambda r: -r[1])
    print(f"{'cmd':>5} {'verts':>6}  dims                 centre (x,y,z)")
    for i, cnt, ext, lo, hi, P, stride, dt in inside[:20]:
        c = (lo + hi) / 2
        print(f"{i:>5} {cnt:>6}  {ext[2]:5.2f} x {ext[1]:5.2f} x {ext[0]:5.2f}"
              f"   ({c[0]:6.2f},{c[1]:6.2f},{c[2]:6.2f})")


if __name__ == "__main__":
    main()
