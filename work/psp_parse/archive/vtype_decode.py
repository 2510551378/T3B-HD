"""vtype_decode.py -- decode VERTICES blocks using the recorded vertex format.

The recording stores the GE state before each draw, so the vtype in force is known exactly.
Component sizes and the memory order come from PPSSPP's VertexDecoderCommon.cpp:

    order: weights -> texcoords -> colour -> normal -> position
    tc   = fmt & 3          tcsize   = {0,2,4,8}      tcalign  = {0,1,2,4}
    col  = (fmt >> 2) & 7   colsize  = {0,0,0,0,2,2,2,4}
    nrm  = (fmt >> 5) & 3   nrmsize  = {0,3,6,12}     nrmalign = {0,1,2,4}
    pos  = (fmt >> 7) & 3   possize  = {3,3,6,12}     posalign = {0,1,2,4}
    wt   = (fmt >> 9) & 3   wtsize   = {0,1,2,4}      nweights = ((fmt >> 14) & 7) + 1
"""
import collections
import struct
import sys

import numpy as np

sys.path.insert(0, r"work\psp_parse\archive")
from ppdmp2 import read  # noqa: E402

SC = 3.125 / 32768.0
TCS = (0, 2, 4, 8)
TCA = (0, 1, 2, 4)
COLS = (0, 0, 0, 0, 2, 2, 2, 4)
COLA = (0, 0, 0, 0, 2, 2, 2, 4)
NRMS = (0, 3, 6, 12)
NRMA = (0, 1, 2, 4)
POSS = (3, 3, 6, 12)
POSA = (0, 1, 2, 4)
WTS = (0, 1, 2, 4)
WTA = (0, 1, 2, 4)


def layout(fmt):
    tc = fmt & 3
    col = (fmt >> 2) & 7
    nrm = (fmt >> 5) & 3
    pos = (fmt >> 7) & 3
    wt = (fmt >> 9) & 3
    nw = ((fmt >> 14) & 7) + 1
    size = 0
    offs = {}
    align = 1
    if wt:
        size = (size + WTA[wt] - 1) // WTA[wt] * WTA[wt]
        offs["wt"] = (size, WTS[wt] * nw)
        size += WTS[wt] * nw
        align = max(align, WTA[wt])
    if tc:
        size = (size + TCA[tc] - 1) // TCA[tc] * TCA[tc]
        offs["uv"] = (size, TCS[tc])
        size += TCS[tc]
        align = max(align, TCA[tc])
    if col:
        a = COLA[col] or 1
        size = (size + a - 1) // a * a
        offs["col"] = (size, COLS[col])
        size += COLS[col]
        align = max(align, a)
    if nrm:
        a = NRMA[nrm] or 1
        size = (size + a - 1) // a * a
        offs["nrm"] = (size, NRMS[nrm])
        size += NRMS[nrm]
        align = max(align, a)
    if pos:
        a = POSA[pos] or 1
        size = (size + a - 1) // a * a
        offs["pos"] = (size, POSS[pos])
        size += POSS[pos]
        align = max(align, a)
    stride = (size + align - 1) // align * align
    return stride, offs


def positions(blk, stride, posoff, possize):
    if stride <= 0:
        return None
    if possize == 12:
        step = stride // 4
        if step < 3:
            return None
        total = len(blk) // 4
        base = posoff // 4
        n = (total - base) // step
        if n < 3:
            return None
        raw = np.frombuffer(blk[:total * 4], dtype="<f4")
        P = raw[base:base + n * step].reshape(n, step)[:, :3].astype(np.float64)
    elif possize == 6:
        step = stride // 2
        if step < 3:
            return None
        total = len(blk) // 2
        base = posoff // 2
        n = (total - base) // step
        if n < 3:
            return None
        raw = np.frombuffer(blk[:total * 2], dtype="<i2")
        P = raw[base:base + n * step].reshape(n, step)[:, :3].astype(np.float64) * SC
    else:
        step = stride
        n = (len(blk) - posoff) // step
        if n < 3:
            return None
        raw = np.frombuffer(blk[:n * step + posoff], dtype=np.int8)
        P = raw[posoff:posoff + n * step].reshape(n, step)[:, :3].astype(np.float64) / 127.0
    return P


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    cmds, buf = read(sys.argv[1])
    cur = None
    blocks = []
    for i, (t, sz, ptr) in enumerate(cmds):
        if ptr + sz > len(buf):
            continue
        if t == 1:
            for x in struct.unpack_from("<%dI" % (sz // 4), buf, ptr):
                if (x >> 24) == 0x12:
                    cur = x & 0xFFFFFF
        elif t == 2:
            blocks.append((i, sz, ptr, cur))

    print(f"{len(blocks)} vertex blocks, "
          f"{len(set(b[3] for b in blocks))} distinct vtypes")
    hits = []
    stats = collections.Counter()
    for i, sz, ptr, vt in blocks:
        if vt is None:
            continue
        stride, offs = layout(vt)
        if "pos" not in offs or stride == 0:
            continue
        stats[(vt, stride)] += 1
        posoff, possize = offs["pos"]
        P = positions(buf[ptr:ptr + sz], stride, posoff, possize)
        if P is None or len(P) < 24:
            continue
        if not np.isfinite(P).all() or np.abs(P).max() > 500:
            continue
        lo, hi = P.min(axis=0), P.max(axis=0)
        dx, dy, dz = hi - lo
        if 1.2 <= dy <= 2.2 and 0.10 <= max(dx, dz) <= 1.2:
            hits.append((i, len(P), dx, dy, dz, vt, stride, P))

    print("\nvtype usage (vtype, stride, blocks):")
    for (vt, st), n in stats.most_common(10):
        print(f"   vtype 0x{vt:06x} stride {st:>3}  x{n}")

    print(f"\nblocks with human proportions under their TRUE vtype: {len(hits)}")
    hits.sort(key=lambda h: -h[1])
    for i, n, dx, dy, dz, vt, stride, P in hits[:12]:
        print(f"   cmd[{i}] {n} verts  {dx:.2f} x {dy:.2f} x {dz:.2f} m  "
              f"vtype 0x{vt:06x} stride {stride}")

    if len(sys.argv) > 2:
        import os
        out = sys.argv[2]
        os.makedirs(out, exist_ok=True)
        for k, (i, n, dx, dy, dz, vt, stride, P) in enumerate(hits):
            with open(os.path.join(out, f"cmd{i:04d}_{n}v_v{vt:06x}.obj"), "w",
                      encoding="utf-8") as fh:
                fh.write(f"# vtype 0x{vt:06x} stride {stride}\n")
                for p in P:
                    fh.write("v %.4f %.4f %.4f\n" % tuple(p))
                for q in range(0, n - 2, 3):
                    fh.write(f"f {q+1} {q+2} {q+3}\n")
        print("exported ->", out)


if __name__ == "__main__":
    main()
