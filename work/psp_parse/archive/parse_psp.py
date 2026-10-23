"""PSP artifact parser: PBP -> PARAM.SFO, and ISO9660 (UMD image) directory tree.

Read-only. Writes a UTF-8 report to stdout.
"""
import os
import struct
import sys

ROOT = r"C:\Users\25105\Documents\寄生前夜第四日"
PBP_ORIG = os.path.join(ROOT, r"PSP\game\game\EBOOT.PBP")
PBP_PROJ = os.path.join(ROOT, r"work\psp_game\EBOOT.PBP")
ISO = os.path.join(ROOT, r"PSP\The_3rd_birthday_cn_full_v101.iso")

PBP_NAMES = ["PARAM.SFO", "ICON0.PNG", "ICON1.PMF", "PIC0.PNG",
             "PIC1.PNG", "SND0.AT3", "DATA.PSP", "DATA.PSAR"]

SFO_TYPES = {0x0004: "utf8", 0x0204: "utf8n", 0x0404: "int32"}


def u32(b, o):
    return struct.unpack_from("<I", b, o)[0]


def sfo(data):
    if data[:4] != b"\x00PSF":
        return None
    ver, key_start, val_start, count = struct.unpack_from("<IIII", data, 4)
    out = []
    for i in range(count):
        ko, fmt, ln, mx, do = struct.unpack_from("<HHIII", data, 20 + i * 16)
        key = data[key_start + ko:].split(b"\0", 1)[0].decode("utf-8", "replace")
        raw = data[val_start + do: val_start + do + ln]
        kind = SFO_TYPES.get(fmt)
        if kind == "int32":
            val = struct.unpack("<I", raw)[0]
        else:
            val = raw.split(b"\0", 1)[0].decode("utf-8", "replace")
        out.append((key, val, fmt))
    return {"version": ver, "count": count, "entries": out}


def parse_pbp(path):
    print("=" * 78)
    print("PBP:", os.path.relpath(path, ROOT))
    print("=" * 78)
    size = os.path.getsize(path)
    with open(path, "rb") as f:
        head = f.read(40)
        if head[:4] != b"\x00PBP":
            print("  !! not a PBP, magic =", head[:4].hex())
            return
        ver = u32(head, 4)
        offs = list(struct.unpack_from("<8I", head, 8))
        print(f"  magic='\\0PBP'  version=0x{ver:08x}  file_size={size:,}")
        bounds = offs + [size]
        for i, name in enumerate(PBP_NAMES):
            o, e = bounds[i], bounds[i + 1]
            n = max(0, e - o)
            print(f"    {name:12} @ 0x{o:08x} ({o:>10,})  size={n:>12,}")
        f.seek(offs[0])
        s = sfo(f.read(max(0, offs[1] - offs[0])))
        if s:
            print(f"  PARAM.SFO  version=0x{s['version']:08x}  entries={s['count']}")
            for k, v, f_ in s["entries"]:
                print(f"    {k:24} = {v!r}  (0x{f_:04x})")
        print()


def iso_dir_records(f, lba, length, sec=2048):
    """Yield (name, flags, lba, size) for one directory extent."""
    f.seek(lba * sec)
    data = f.read(length)
    i = 0
    while i < len(data):
        rl = data[i]
        if rl == 0:
            i = (i // sec + 1) * sec
            continue
        rec = data[i:i + rl]
        if len(rec) < 33:
            break
        elba = struct.unpack_from("<I", rec, 2)[0]
        esz = struct.unpack_from("<I", rec, 10)[0]
        flags = rec[25]
        nlen = rec[32]
        name = rec[33:33 + nlen]
        i += rl
        if name in (b"\x00", b"\x01"):
            continue
        name = name.decode("ascii", "replace")
        if name.endswith(";1"):
            name = name[:-2]
        yield name, flags, elba, esz


def walk(f, lba, size, prefix="", depth=0, out=None, stats=None):
    entries = sorted(iso_dir_records(f, lba, size), key=lambda e: (e[1] & 2 == 0, e[0]))
    for name, flags, elba, esz in entries:
        is_dir = bool(flags & 2)
        path = f"{prefix}/{name}" if prefix else name
        if is_dir:
            print(f"{'  ' * depth}{name}/")
            walk(f, elba, esz, path, depth + 1, out, stats)
        else:
            ext = os.path.splitext(name)[1].lower()
            if stats is not None:
                stats.setdefault(ext, [0, 0])
                stats[ext][0] += 1
                stats[ext][1] += esz
            if depth <= 2 or esz > 1024 * 1024:
                print(f"{'  ' * depth}{name:52} {esz:>12,} LBA {elba}")
            if out is not None:
                out.append((path, elba, esz))


def parse_iso(path):
    print("=" * 78)
    print("ISO:", os.path.relpath(path, ROOT))
    print("=" * 78)
    size = os.path.getsize(path)
    print(f"  file_size={size:,}  ({size / 1024 ** 3:.3f} GiB)")
    with open(path, "rb") as f:
        # volume descriptors from sector 16
        pvd = None
        for i in range(16, 32):
            f.seek(i * 2048)
            d = f.read(2048)
            if len(d) < 2048:
                break
            if d[1:6] != b"CD001":
                print(f"  sector {i}: no CD001 (type {d[0]}, id {d[1:6]!r})")
                break
            print(f"  sector {i}: type={d[0]} id={d[1:6].decode()} ver={d[6]} "
                  f"system='{d[8:40].split(b'\0')[0].decode('ascii','replace')}' "
                  f"volume='{d[40:72].split(b'\0')[0].decode('ascii','replace')}'")
            if d[0] == 1 and pvd is None:
                pvd = d
            if d[0] == 255:
                break
        if pvd is None:
            print("  !! no primary volume descriptor")
            return
        root = pvd[156:156 + 34]
        rlba = struct.unpack_from("<I", root, 2)[0]
        rsz = struct.unpack_from("<I", root, 10)[0]
        print(f"  root dir: LBA {rlba} size {rsz}")
        stats = {}
        files = []
        print("  --- tree ---")
        walk(f, rlba, rsz, "", 0, files, stats)
        print(f"  --- {len(files)} files ---")
        for ext, (n, sz) in sorted(stats.items(), key=lambda kv: -kv[1][1]):
            print(f"    {ext or '(none)':10} {n:>6} files  {sz:>14,} bytes")
        biggest = sorted(files, key=lambda x: -x[2])[:15]
        print("  --- largest files ---")
        for p, lba, sz in biggest:
            print(f"    {sz:>14,}  LBA {lba:>10}  {p}")
        # dump full listing next to the script
        with open(os.path.join(os.path.dirname(__file__), "iso_listing.txt"),
                  "w", encoding="utf-8") as o:
            for p, lba, sz in sorted(files, key=lambda x: x[0]):
                o.write(f"{lba:>10} {sz:>12} {p}\n")
        print("  full listing -> work/psp_parse/iso_listing.txt")
    print()


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parse_pbp(PBP_PROJ)
    parse_pbp(PBP_ORIG)
    parse_iso(ISO)
