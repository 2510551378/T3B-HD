"""pad_runs.py -- systematic vertex-array discovery across the whole pkg.

Most vertex records end with the 0xCCCC filler.  For every section we look for a fixed stride
and a fixed offset where that filler repeats for a long run; that pins down both the record
size and the position offset (positions sit right before the pad).  Then we decode the cloud
and keep anything human-shaped.

    python pad_runs.py [--min-run 100]
"""
import collections
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
                    secs = []
                    ok = True
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


def find_arrays(buf, min_run=100):
    n = len(buf)
    hits = []
    for stride in range(10, 65):
        cnt = n // stride
        if cnt < min_run:
            continue
        for pad in range(0, stride - 1):
            ok = 0
            prev = -99
            best = 0
            start = -1
            for k in range(cnt):
                o = k * stride + pad
                if buf[o:o + 2] == b"\xcc\xcc":
                    if k - prev == 1:
                        ok += 1
                        start = start if start >= 0 else k
                    else:
                        ok = 1
                        start = k
                    prev = k
                    if ok > best:
                        best = ok
                        best_start = start
            if best >= min_run:
                hits.append((best, stride, pad, best_start))
    hits.sort(reverse=True)
    return hits


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    min_run = 100
    for i, a in enumerate(sys.argv):
        if a == "--min-run":
            min_run = int(sys.argv[i + 1])

    with open(ISO, "rb") as f:
        mm = mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ)
        packs = parse_packs(mm)
        print(f"{len(packs)} containers")
        results = []
        for off, ptype, secs in packs:
            for idx, (sz, so) in enumerate(secs):
                if sz < 4096:
                    continue
                buf = bytes(mm[off + so:off + so + sz])
                for run, stride, pad, start in find_arrays(buf, min_run)[:3]:
                    posoff = pad - 6
                    if posoff < 0:
                        posoff = max(0, pad + 2)
                    m = (sz - start * stride) // stride
                    m = min(m, 4000)
                    P = np.array([struct.unpack_from("<3h", buf, (start + k) * stride + posoff)
                                  for k in range(max(0, m - 0))], dtype=np.float64) * SC
                    if len(P) < 40:
                        continue
                    lo, hi = P.min(axis=0), P.max(axis=0)
                    d = hi - lo
                    results.append((off, ptype, idx, sz, stride, pad, run, d, lo, hi))
        mm.close()

    print(f"\nsections with a padded record array: {len(results)}")
    hum = [r for r in results if 1.2 <= r[7][1] <= 2.2 and 0.10 <= max(r[7][0], r[7][2]) <= 1.2]
    print(f"arrays whose cloud is human-shaped: {len(hum)}")
    print(f"{'pack':>10} {'type':>5} {'sect':>5} {'stride':>6} {'pad':>4} {'run':>6}  dims")
    for off, ptype, idx, sz, stride, pad, run, d, lo, hi in hum[:20]:
        print(f"0x{off:08x} {ptype:>5} {idx:>5} {stride:>6} {pad:>4} {run:>6}  "
              f"{d[0]:.2f} x {d[1]:.2f} x {d[2]:.2f}")


if __name__ == "__main__":
    main()
