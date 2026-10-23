"""merge_skinned.py -- put every skinned block at the origin and merge them into one mesh.

If the recorded vertices are in mesh (bind pose) space, overlapping them reconstructs the
character with no matrices at all.  If they are in bone space, the result is a jumble -- which
is itself informative.
"""
import os
import struct
import sys

import numpy as np

sys.path.insert(0, r"work\psp_parse\archive")
from ppdmp2 import read  # noqa: E402
from vtype_decode import layout, positions  # noqa: E402

SKIN = (0x4522, 0x8522, 0xC522)


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    cmds, buf = read(sys.argv[1])
    out = sys.argv[2]
    cur = None
    verts = []
    faces = []
    n = 0
    for i, (t, sz, ptr) in enumerate(cmds):
        if ptr + sz > len(buf):
            continue
        if t == 1:
            for x in struct.unpack_from("<%dI" % (sz // 4), buf, ptr):
                if (x >> 24) == 0x12:
                    cur = x & 0xFFFFFF
        elif t == 2 and cur in SKIN:
            stride, offs = layout(cur)
            po, ps = offs["pos"]
            P = positions(buf[ptr:ptr + sz], stride, po, ps)
            if P is None or len(P) < 10:
                continue
            base = len(verts)
            verts.extend(P)
            for q in range(0, len(P) - 2, 3):
                faces.append((base + q, base + q + 1, base + q + 2))
            n += 1
    V = np.array(verts)
    lo, hi = V.min(axis=0), V.max(axis=0)
    print(f"merged {n} blocks, {len(verts)} vertices")
    print(f"bbox {hi[0]-lo[0]:.2f} x {hi[1]-lo[1]:.2f} x {hi[2]-lo[2]:.2f} m")
    print(f"centre ({(lo[0]+hi[0])/2:.2f}, {(lo[1]+hi[1])/2:.2f}, {(lo[2]+hi[2])/2:.2f})")
    with open(out, "w", encoding="utf-8") as fh:
        fh.write("# merged skinned blocks, all at origin\n")
        for p in verts:
            fh.write("v %.4f %.4f %.4f\n" % tuple(p))
        for a, b, c in faces:
            fh.write(f"f {a+1} {b+1} {c+1}\n")
    print("->", out)


if __name__ == "__main__":
    main()
