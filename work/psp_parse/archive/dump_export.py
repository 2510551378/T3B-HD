"""dump_export.py -- export frame-dump geometry using the verified layouts.

Layouts derived from PPSSPP's VertexDecoderCommon.cpp tables:

    0x11F  stride 20   uv f32x2 @0   col RGBA @8   pos s16x3 @12   pad @18
    0x4522 stride 20   wt u16x2 @0   uv u16x2 @4   nrm s8x3 @8   pos s16x3 @12
    0x8522 stride 20   wt u16x3 @0   uv u16x2 @6   nrm s8x3 @10  pos s16x3 @14

The 0xCCCC marker sits at stride-2 in the first layout, which is how a block is recognised.
"""
import os
import struct
import sys

import numpy as np

sys.path.insert(0, r"work\psp_parse\archive")
from ppdmp2 import read  # noqa: E402

POS_SCALE = 3.125 / 32768.0


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    cmds, buf = read(sys.argv[1])
    outdir = sys.argv[2]
    os.makedirs(outdir, exist_ok=True)

    env_runs = []
    for i, (t, sz, ptr) in enumerate(cmds):
        if t != 2 or sz < 40 or sz % 20 or ptr + sz > len(buf):
            continue
        d = buf[ptr:ptr + sz]
        if d[18:20] != b"\xcc\xcc" and d[38:40] != b"\xcc\xcc":
            continue
        n = sz // 20
        P = np.empty((n, 3))
        C = np.empty((n, 4), dtype=np.uint8)
        U = np.empty((n, 2))
        for k in range(n):
            r = d[k * 20:(k + 1) * 20]
            U[k] = struct.unpack_from("<2f", r, 0)
            C[k] = tuple(r[8:12])
            x, y, z = struct.unpack_from("<3h", r, 12)
            P[k] = (x * POS_SCALE, y * POS_SCALE, z * POS_SCALE)
        env_runs.append((i, n, P, C, U))

    total = sum(r[1] for r in env_runs)
    print(f"{len(env_runs)} runs in the 0x11F layout, {total} vertices")
    path = os.path.join(outdir, "env_all.obj")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("# frame dump environment geometry (layout 0x11F)\n")
        base = 1
        for i, n, P, C, U in env_runs:
            fh.write(f"o run_{i}\n")
            for p in P:
                fh.write("v %.4f %.4f %.4f\n" % tuple(p))
            for k in range(0, n - 2, 3):
                fh.write(f"f {base+k} {base+k+1} {base+k+2}\n")
            base += n
    print("->", path)
    for i, n, P, C, U in sorted(env_runs, key=lambda r: -r[1])[:5]:
        ext = P.max(axis=0) - P.min(axis=0)
        print(f"  cmd[{i:>4}] {n:>5} verts  {ext[0]:.2f} x {ext[1]:.2f} x {ext[2]:.2f} m")


if __name__ == "__main__":
    main()
