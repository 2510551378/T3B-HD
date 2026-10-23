"""human_scan.py -- brute-force search for human-shaped s16 vertex arrays in the packs.

Independent of the 0xCCCC filler: for each sizeable section we try a range of record strides
and position offsets on a sample of records and keep any cloud that is 1.4-2.0 m tall with
both horizontal extents at least 0.15 m.

    python human_scan.py [--types 8,12]
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
STRIDES = (14, 16, 18, 20, 22, 24, 26, 28, 32, 36, 40)


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


def probe(buf):
    best = None
    n = len(buf)
    sample = min(n, 12000)
    a = np.frombuffer(buf[:sample], dtype="<i2")
    total = len(a)
    for stride in STRIDES:
        step = stride // 2
        if step < 3:
            continue
        cnt = (total - 2) // step
        if cnt < 80:
            continue
        for posoff in range(0, stride - 6 + 1, 2):
            base = posoff // 2
            m = (total - base) // step
            if m < 80:
                continue
            w = a[base:base + m * step].reshape(m, step)[:, :3].astype(np.float64) * SC
            lo, hi = w.min(axis=0), w.max(axis=0)
            d = hi - lo
            if not (1.4 <= d[1] <= 2.0 and min(d[0], d[2]) >= 0.15
                    and max(d[0], d[2]) <= 1.0):
                continue
            dv = np.linalg.norm(np.diff(w, axis=0), axis=1)
            med = float(np.median(dv))
            if med > 0.35:
                continue
            score = med
            if best is None or score < best[0]:
                best = (score, stride, posoff, cnt, tuple(d))
    return best


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    types = {8, 12}
    for i, a in enumerate(sys.argv):
        if a == "--types":
            types = {int(x) for x in sys.argv[i + 1].split(",")}

    with open(ISO, "rb") as f:
        mm = mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ)
        packs = parse_packs(mm)
        print(f"{len(packs)} containers; scanning types {sorted(types)}", flush=True)
        hits = []
        for pi, (off, ptype, secs) in enumerate(packs):
            if ptype not in types:
                continue
            for idx, (sz, so) in enumerate(secs):
                if sz < 8192:
                    continue
                buf = bytes(mm[off + so:off + so + sz])
                r = probe(buf)
                if r:
                    hits.append((off, ptype, idx, sz, r))
            if pi % 50 == 0:
                print(f"  ... {pi}/{len(packs)}", flush=True)
        mm.close()

    print(f"\nhuman-shaped sections: {len(hits)}")
    print(f"{'pack':>10} {'type':>5} {'sect':>5} {'size':>9} {'stride':>6} {'off':>4} "
          f"{'sample':>7}  dims")
    for off, ptype, idx, sz, r in hits[:24]:
        score, stride, posoff, cnt, d = r
        print(f"0x{off:08x} {ptype:>5} {idx:>5} {sz:>9} {stride:>6} {posoff:>4} "
              f"{cnt:>7}  {d[0]:.2f} x {d[1]:.2f} x {d[2]:.2f}")


if __name__ == "__main__":
    main()
