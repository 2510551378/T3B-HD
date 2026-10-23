"""pad_runs2.py -- vectorised discovery of 0xCCCC-padded vertex arrays across the whole pkg.

Instead of looping stride x offset in Python, find every 0xCCCC occurrence once and group the
gaps: a long run of equal gaps is a record array, the gap is the stride and (position % stride)
is the filler offset.  Positions sit right before the filler.
"""
import mmap
import os
import struct
import sys

import numpy as np

ROOT = r"C:\Users\25105\Documents\寄生前夜第四日"
ISO = os.path.join(ROOT, r"PSP\The_3rd_birthday_cn_full_v101.iso")
PKG_LBA, PKG_SIZE, SEC = 59600, 1344292864, 2048
SC = 3.125 / 32768.0


def parse_packs(mm):
    base = PKG_LBA * SEC
    end = base + PKG_SIZE
    packs, pos, CH = [], base, 1 << 22
    carry, carry_off = b"", base
    while pos < end:
        chunk = mm[pos:min(end, pos + CH)]
        data = carry + chunk
        s = 0
        while True:
            k = data.find(b"pack", s)
            if k < 0:
                break
            off = carry_off + k
            ptype = struct.unpack_from("<I", mm, off + 4)[0]
            hdr = struct.unpack_from("<I", mm, off + 12)[0]
            if ptype <= 0x100 and 16 <= hdr <= 0x2000 and hdr % 4 == 0:
                cnt = (hdr - 8) // 8
                if 1 <= cnt <= 512:
                    secs, ok = [], True
                    for i in range(cnt):
                        sz, so = struct.unpack_from("<II", mm, off + 8 + i * 8)
                        if sz and so:
                            if so < hdr or so + sz > PKG_SIZE:
                                ok = False
                                break
                            secs.append((sz, so))
                    if ok and secs:
                        packs.append((off, ptype, secs))
            s = k + 4
        carry, carry_off = data[-4:], pos + len(chunk) - 4
        pos += len(chunk)
    seen, out = set(), []
    for p in packs:
        if p[0] not in seen:
            seen.add(p[0])
            out.append(p)
    return sorted(out)


def arrays_in(buf, min_run=60):
    """Yield (stride, pad_off, first_index) for long equal-gap runs of 0xCCCC."""
    a = np.frombuffer(buf, dtype=np.uint8)
    if len(a) < 4:
        return []
    cc = (a[:-1] == 0xCC) & (a[1:] == 0xCC)
    pads = np.flatnonzero(cc)
    if len(pads) < min_run:
        return []
    d = np.diff(pads)
    out = []
    for stride in np.unique(d):
        if not (10 <= stride <= 70):
            continue
        idx = np.flatnonzero(d == stride)
        if len(idx) + 1 < min_run:
            continue
        # split into contiguous runs
        breaks = np.flatnonzero(np.diff(idx) != 1)
        starts = np.concatenate(([0], breaks + 1))
        ends = np.concatenate((breaks + 1, [len(idx)]))
        for s, e in zip(starts, ends):
            run = e - s + 1
            if run < min_run:
                continue
            first = int(pads[idx[s]])
            out.append((int(stride), first % int(stride), first, run))
    out.sort(key=lambda r: -r[3])
    return out


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    min_run = 60
    for i, a in enumerate(sys.argv):
        if a == "--min-run":
            min_run = int(sys.argv[i + 1])

    with open(ISO, "rb") as f:
        mm = mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ)
        packs = parse_packs(mm)
        print(f"{len(packs)} containers", flush=True)
        results = []
        for pi, (off, ptype, secs) in enumerate(packs):
            for idx, (sz, so) in enumerate(secs):
                if sz < 2048:
                    continue
                buf = bytes(mm[off + so:off + so + sz])
                for stride, pad, first, run in arrays_in(buf, min_run)[:2]:
                    posoff = pad - 6
                    if posoff < 0:
                        posoff = min(stride - 6, pad + 2)
                    n = min(run, 3000)
                    try:
                        P = np.array([struct.unpack_from("<3h", buf, first + k * stride + posoff)
                                      for k in range(n)], dtype=np.float64) * SC
                    except struct.error:
                        continue
                    if len(P) < 40:
                        continue
                    lo, hi = P.min(axis=0), P.max(axis=0)
                    d = hi - lo
                    results.append((off, ptype, idx, sz, stride, pad, run, tuple(d)))
            if pi % 100 == 0:
                print(f"  ... {pi}/{len(packs)}", flush=True)
        mm.close()

    print(f"\narrays found: {len(results)}")
    with open(os.path.join(ROOT, "work", "psp_parse", "out", "pad_arrays.csv"), "w",
              encoding="utf-8") as fh:
        fh.write("pack,type,section,size,stride,pad,run,dx,dy,dz\n")
        for off, ptype, idx, sz, stride, pad, run, d in results:
            fh.write(f"0x{off:08x},{ptype},{idx},{sz},{stride},{pad},{run},"
                     f"{d[0]:.4f},{d[1]:.4f},{d[2]:.4f}\n")
    print("csv -> out/pad_arrays.csv")
    hum = [r for r in results
           if 1.4 <= r[7][1] <= 2.0 and min(r[7][0], r[7][2]) >= 0.15
           and max(r[7][0], r[7][2]) <= 1.0]
    print(f"human-shaped arrays (dy 1.4-2.0, both widths >= 0.15): {len(hum)}")
    print(f"{'pack':>10} {'type':>5} {'sect':>5} {'stride':>6} {'pad':>4} {'run':>6}  dims")
    for r in sorted(hum, key=lambda r: -r[6])[:24]:
        off, ptype, idx, sz, stride, pad, run, d = r
        print(f"0x{off:08x} {ptype:>5} {idx:>5} {stride:>6} {pad:>4} {run:>6}  "
              f"{d[0]:.2f} x {d[1]:.2f} x {d[2]:.2f}")


if __name__ == "__main__":
    main()
