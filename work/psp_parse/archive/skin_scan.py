"""skin_scan.py -- find skinned vertex data inside the pack containers.

A skinned vertex carries a bone index, which shows up as a byte column whose values are all
small (0..15) and varied.  Scanning every section for such a column at a fixed stride finds
the containers that hold character meshes.

    python skin_scan.py            # scan, print hits
    python skin_scan.py --csv out  # also write every hit
"""
import collections
import mmap
import os
import struct
import sys

ROOT = r"C:\Users\25105\Documents\寄生前夜第四日"
ISO = os.path.join(ROOT, r"PSP\The_3rd_birthday_cn_full_v101.iso")
PKG_LBA, PKG_SIZE, SEC = 59600, 1344292864, 2048
ALIGN = 0x800


def parse_pack(mm, off):
    if bytes(mm[off:off + 4]) != b"pack":
        return None
    ptype = struct.unpack_from("<I", mm, off + 4)[0]
    if ptype > 0x100:
        return None
    hdr = struct.unpack_from("<I", mm, off + 12)[0]
    if hdr < 16 or hdr > 0x2000 or hdr % 4:
        return None
    count = (hdr - 8) // 8
    if not (1 <= count <= 512):
        return None
    secs = []
    for i in range(count):
        sz, so = struct.unpack_from("<II", mm, off + 8 + i * 8)
        if sz == 0 or so == 0 or so < hdr or so + sz > PKG_SIZE:
            return None
        secs.append((sz, so))
    return (ptype, secs) if secs else None


def scan_section(buf):
    """Return (stride, column, score) for the best bone-index column, or None."""
    n = len(buf)
    if n < 512:
        return None
    best = None
    for stride in range(10, 33):
        cnt = n // stride
        if cnt < 40:
            continue
        sample = min(cnt, 400)
        for col in range(stride):
            vals = [buf[k * stride + col] for k in range(sample)]
            small = sum(1 for v in vals if v < 16)
            distinct = len(set(vals))
            if small >= sample * 0.92 and 3 <= distinct <= 16:
                score = (small / sample, distinct, cnt)
                if best is None or score[0] * min(score[1], 8) > best[0] * min(best[1], 8):
                    best = (score[0], score[1], cnt, stride, col)
    return best


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    csv_path = None
    for i, a in enumerate(sys.argv):
        if a == "--csv":
            csv_path = sys.argv[i + 1]

    with open(ISO, "rb") as f:
        mm = mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ)
        base = PKG_LBA * SEC
        end = base + PKG_SIZE
        packs = []
        pos = base
        CH = 1 << 22
        carry, carry_off = b"", base
        while pos < end:
            chunk = mm[pos:min(end, pos + CH)]
            data = carry + chunk
            start = 0
            while True:
                k = data.find(b"pack", start)
                if k < 0:
                    break
                abs_off = carry_off + k
                r = parse_pack(mm, abs_off)
                if r:
                    packs.append((abs_off, r[0], r[1]))
                start = k + 4
            carry, carry_off = data[-4:], pos + len(chunk) - 4
            pos += len(chunk)

        seen, uniq = set(), []
        for p in packs:
            if p[0] in seen:
                continue
            seen.add(p[0])
            uniq.append(p)
        packs = sorted(uniq)
        print(f"{len(packs)} containers")

        rows = []
        for off, ptype, secs in packs:
            for idx, (sz, so) in enumerate(secs):
                if sz < 4096:
                    continue
                a = off + so
                buf = bytes(mm[a:a + min(sz, 1 << 18)])
                r = scan_section(buf)
                if r:
                    rows.append((off, ptype, idx, sz, so, r))
        mm.close()

    rows.sort(key=lambda r: -r[5][2])
    print(f"\nsections carrying a bone-index column: {len(rows)}")
    print(f"{'pack':>10} {'type':>5} {'sect':>5} {'size':>9} {'stride':>7} {'col':>4} "
          f"{'verts':>7} {'distinct':>8}")
    for off, ptype, idx, sz, so, r in rows[:16]:
        score, distinct, cnt, stride, col = r
        print(f"0x{off:08x} {ptype:>5} {idx:>5} {sz:>9} {stride:>7} {col:>4} "
              f"{cnt:>7} {distinct:>8}")

    if csv_path:
        with open(csv_path, "w", encoding="utf-8") as fh:
            fh.write("pack,type,section,size,rel_offset,stride,bone_col,verts,distinct\n")
            for off, ptype, idx, sz, so, r in rows:
                score, distinct, cnt, stride, col = r
                fh.write(f"0x{off:08x},{ptype},{idx},{sz},0x{so:08x},{stride},{col},{cnt},{distinct}\n")
        print("csv ->", csv_path)


if __name__ == "__main__":
    main()
