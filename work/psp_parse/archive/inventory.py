"""Final inventory + artifact extraction for PSP/The_3rd_birthday_cn_full_v101.iso."""
import csv
import os
import struct
import sys

ROOT = r"C:\Users\25105\Documents\寄生前夜第四日"
ISO = os.path.join(ROOT, r"PSP\The_3rd_birthday_cn_full_v101.iso")
OUT = os.path.join(os.path.dirname(__file__), "extract")
SEC = 2048
PKG_LBA, PKG_SIZE = 59600, 1344292864

ISO_MEMBERS = {
    "PARAM.SFO": (59344, 560),
    "ICON0.PNG": (59360, 5825),
    "PIC1.PNG": (59376, 51717),
    "SND0.AT3": (59440, 265104),
    "UMD_DATA.BIN": (27, 48),
    "SYSDIR_EBOOT.BIN": (544, 5660624),
}


def scan(f, sig, base_lba=PKG_LBA, size=PKG_SIZE):
    f.seek(base_lba * SEC)
    pos, left, hits = 0, size, []
    CH = 1 << 23
    while left > 0:
        buf = f.read(min(CH, left))
        if not buf:
            break
        left -= len(buf)
        i = 0
        while True:
            i = buf.find(sig, i)
            if i < 0:
                break
            hits.append(pos + i)
            i += 1
        pos += len(buf)
    return hits


def align_up(v, a=0x800):
    return (v + a - 1) // a * a


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    os.makedirs(OUT, exist_ok=True)
    with open(ISO, "rb") as f:
        for name, (lba, size) in ISO_MEMBERS.items():
            f.seek(lba * SEC)
            blob = f.read(size)
            with open(os.path.join(OUT, name), "wb") as o:
                o.write(blob)
            print(f"  iso member {name:18} {size:>9,} bytes  head={blob[:8].hex(' ')}")

        # PSMF with big-endian header fields
        vids = []
        for h in scan(f, b"PSMF"):
            f.seek(PKG_LBA * SEC + h)
            d = f.read(0x20)
            ver = d[4:8].decode("latin1")
            hdr = struct.unpack_from(">I", d, 8)[0]
            stream = struct.unpack_from(">I", d, 12)[0]
            vids.append((h, ver, hdr, stream))
        print(f"\nPSMF: {len(vids)} entries (big-endian sizes)")
        ok = 0
        rows = []
        for i, (h, ver, hdr, stream) in enumerate(vids):
            end = h + hdr + stream
            nxt = vids[i + 1][0] if i + 1 < len(vids) else None
            contiguous = (nxt is not None and align_up(end) == nxt)
            ok += bool(contiguous)
            rows.append((i, f"0x{h:08x}", hdr, stream, hdr + stream, f"0x{align_up(end):08x}", contiguous))
        for r in rows[:6]:
            print(f"  [{r[0]:>2}] off={r[1]} hdr={r[2]:#x} stream={r[3]:>12,} total={r[4]:>12,} "
                  f"next_aligned={r[5]} contiguous={r[6]}")
        print(f"  contiguous to next PSMF: {ok}/{len(vids) - 1}")
        tot = sum(r[4] for r in rows)
        print(f"  total video bytes ~ {tot:,} ({tot / 1024 ** 2:.1f} MiB)")
        with open(os.path.join(OUT, "pkg_videos.csv"), "w", newline="", encoding="utf-8") as o:
            w = csv.writer(o)
            w.writerow(["idx", "pkg_offset", "hdr_size", "stream_size", "total", "next_aligned", "contiguous"])
            for r in rows:
                w.writerow([r[0], r[1], r[2], r[3], r[4], r[5], r[6]])
        print("  -> extract/pkg_videos.csv")

        # extract the smallest video as a sample
        small = min(rows, key=lambda r: r[4])
        h = int(small[1], 16)
        total = small[4]
        f.seek(PKG_LBA * SEC + h)
        blob = f.read(total)
        p = os.path.join(OUT, f"small_{small[1]}.psmf")
        with open(p, "wb") as o:
            o.write(blob)
        after = blob[0x800:0x810]
        print(f"  sample video {small[1]} total={total:,} -> {os.path.basename(p)}")
        print(f"    first MPEG bytes after 0x800 header: {after.hex(' ')} "
              f"(00 00 01 BA = MPEG pack header)")

        # SEDB with size field
        sedb = [h for h in scan(f, b"SEDBSSCF") if h % 0x800 == 0]
        print(f"\nSEDB (aligned): {len(sedb)}")
        sedb_ok = 0
        sedb_rows = []
        for i, h in enumerate(sedb):
            f.seek(PKG_LBA * SEC + h)
            d = f.read(0x20)
            ver = struct.unpack_from("<I", d, 8)[0]
            size = struct.unpack_from("<I", d, 16)[0]
            end = h + size
            nxt = sedb[i + 1] if i + 1 < len(sedb) else None
            cont = nxt is not None and align_up(end) == nxt
            sedb_ok += bool(cont)
            sedb_rows.append((i, h, size, align_up(end), cont))
        print(f"  size field at +16 makes them contiguous: {sedb_ok}/{len(sedb) - 1}")
        for r in sedb_rows[:6]:
            print(f"  [{r[0]:>3}] off=0x{r[1]:08x} size={r[2]:>9,} end_aligned=0x{r[3]:08x} cont={r[4]}")
        print(f"  total script bytes ~ {sum(r[2] for r in sedb_rows):,}")


if __name__ == "__main__":
    main()
