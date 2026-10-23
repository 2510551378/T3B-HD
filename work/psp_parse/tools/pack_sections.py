"""pack_sections.py -- classify every section of every pack container in 3rd.pkg.

For each container we parse the header, take each section, and fingerprint its first bytes
and overall content (geometry pool, animation, texture table, sound, script, ...).  The
result is a complete map of what the 436 containers actually hold.

Usage:
    python pack_sections.py                     # summary
    python pack_sections.py --csv out.csv       # per-section rows
"""
import collections
import mmap
import os
import struct
import sys

ROOT = r"C:\Users\25105\Documents\寄生前夜第四日"
ISO = os.path.join(ROOT, r"PSP\The_3rd_birthday_cn_full_v101.iso")
SEC = 2048
PKG_LBA, PKG_SIZE = 59600, 1344292864
ALIGN = 0x800

MAGICS = [
    (b"FEP\0", "FEP"),
    (b"ANM\0", "ANM"),
    (b"SEB", "SEB"),
    (b"PSMF", "PSMF"),
    (b"SEDBSSCF", "SEDBSSCF"),
    (b"\x89PNG", "PNG"),
    (b"RIFF", "RIFF"),
    (b"pack", "pack"),
    (b"\x7fELF", "ELF"),
    (b"~PSP", "~PSP"),
]


def looks_like_geometry(buf, start, size):
    """Decode up to 200 stride-20 records and require a coherent point cloud."""
    n = min(size // 20, 200)
    if n < 8:
        return False
    pts = []
    for k in range(n):
        o = start + k * 20 + 4
        x, y, z = struct.unpack_from("<3h", buf, o)
        pts.append((x * 3.125 / 32768.0, y * 3.125 / 32768.0, z * 3.125 / 32768.0))
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    zs = [p[2] for p in pts]
    ext = sorted((max(xs) - min(xs), max(ys) - min(ys), max(zs) - min(zs)))
    if ext[2] < 0.05 or ext[2] > 200:
        return False
    steps = sorted(abs(pts[i + 1][0] - pts[i][0]) + abs(pts[i + 1][1] - pts[i][1])
                   + abs(pts[i + 1][2] - pts[i][2]) for i in range(n - 1))
    med = steps[len(steps) // 2]
    return 0.0005 < med < 2.0


def classify(buf, start, size):
    """Return a short content tag for one section."""
    if size <= 0:
        return "empty"
    head = bytes(buf[start:start + 32])
    for m, name in MAGICS:
        if head.startswith(m):
            return name
    # vertex pool: stride-20 records carrying the 0xCCCC marker AND a coherent cloud
    probe = bytes(buf[start:start + min(size, 1 << 16)])
    if probe.count(b"\xcc\xcc") >= 32:
        pads = [o for o in range(0, len(probe) - 20, 2) if probe[o + 10:o + 12] == b"\xcc\xcc"]
        if len(pads) >= 24 and any(pads[i + 1] - pads[i] == 20 for i in range(len(pads) - 1)):
            if looks_like_geometry(buf, start, size):
                return "vertex pool"
    # texture table: u16 w, u16 h with plausible power-ish sizes
    if size >= 16:
        w, h = struct.unpack_from("<HH", buf, start)
        bpp = struct.unpack_from("<I", buf, start + 4)[0]
        if 0 < w <= 512 and 0 < h <= 512 and bpp in (4, 8, 16, 32) and size % 16 == 0:
            return "texture table"
    # mostly-zero block
    if size and probe.count(0) > len(probe) * 0.9:
        return "zeros"
    return "data"


def parse_pack(buf, off):
    if bytes(buf[off:off + 4]) != b"pack":
        return None
    ptype = struct.unpack_from("<I", buf, off + 4)[0]
    if ptype > 0x100:
        return None
    hdr = struct.unpack_from("<I", buf, off + 12)[0]
    if hdr < 16 or hdr > 0x2000 or hdr % 4:
        return None
    count = (hdr - 8) // 8
    if not (1 <= count <= 512):
        return None
    secs = []
    for i in range(count):
        sz, so = struct.unpack_from("<II", buf, off + 8 + i * 8)
        if sz == 0 or so == 0:
            continue
        if so < hdr or so + sz > PKG_SIZE:
            return None
        secs.append((sz, so))
    if not secs:
        return None
    return ptype, hdr, secs


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
        carry = b""
        carry_off = base
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
                    ptype, hdr, secs = r
                    packs.append((abs_off, ptype, hdr, secs))
                start = k + 4
            carry = data[-4:]
            carry_off = pos + len(chunk) - 4
            pos += len(chunk)

        # de-duplicate (a pack may be found twice when straddling a chunk)
        seen = set()
        uniq = []
        for p in packs:
            if p[0] in seen:
                continue
            seen.add(p[0])
            uniq.append(p)
        packs = sorted(uniq)
        print(f"{len(packs)} pack containers")

        rows = []
        by_type = collections.defaultdict(lambda: collections.Counter())
        type_secs = collections.Counter()
        for off, ptype, hdr, secs in packs:
            type_secs[ptype] += len(secs)
            for idx, (sz, so) in enumerate(secs):
                tag = classify(mm, off + so, sz)
                by_type[ptype][tag] += 1
                rows.append((off, ptype, idx, sz, so, tag))
        mm.close()

    print(f"\n{'type':>5} {'packs':>6} {'sections':>9}  section content mix")
    per_type_packs = collections.Counter(p[1] for p in packs)
    for ptype in sorted(by_type):
        mix = by_type[ptype]
        total = sum(mix.values())
        top = ", ".join(f"{k}×{v}" for k, v in mix.most_common(4))
        print(f"{ptype:>5} {per_type_packs[ptype]:>6} {total:>9}  {top}")

    all_mix = collections.Counter(r[5] for r in rows)
    print(f"\ntotal sections {len(rows)}")
    for k, v in all_mix.most_common():
        print(f"  {k:<16}{v:>6}")

    if csv_path:
        with open(csv_path, "w", encoding="utf-8") as fh:
            fh.write("pack_offset,type,section,size,rel_offset,content\n")
            for off, ptype, idx, sz, so, tag in rows:
                fh.write(f"0x{off:08x},{ptype},{idx},{sz},0x{so:08x},{tag}\n")
        print("csv ->", csv_path)


if __name__ == "__main__":
    main()
