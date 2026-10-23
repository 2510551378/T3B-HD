"""Inventory the plaintext-looking payloads inside 3rd.pkg (PSMF video, SEDB, pack, RIFF)."""
import os
import struct
import sys

ROOT = r"C:\Users\25105\Documents\寄生前夜第四日"
ISO = os.path.join(ROOT, r"PSP\The_3rd_birthday_cn_full_v101.iso")
OUT = os.path.join(os.path.dirname(__file__), "extract")
SEC = 2048
PKG_LBA, PKG_SIZE = 59600, 1344292864


def scan(f, sig):
    f.seek(PKG_LBA * SEC)
    pos, left, hits = 0, PKG_SIZE, []
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


def aligned(h):
    return (h % 0x800 == 0) or (h % 0x1000 == 0)


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    with open(ISO, "rb") as f:
        print("PSMF video entries:")
        rows = []
        for h in scan(f, b"PSMF"):
            f.seek(PKG_LBA * SEC + h)
            d = f.read(0x80)
            ver = d[4:8].decode("latin1")
            hdr = struct.unpack_from("<I", d, 8)[0]
            stream = struct.unpack_from("<I", d, 12)[0]
            ts = struct.unpack_from("<I", d, 16)[0]
            rows.append((h, ver, hdr, stream, ts))
            print(f"  off={h:#010x} align={aligned(h)} ver={ver} hdr_size={hdr:#x} "
                  f"stream={stream:,} ts={ts}")
        # extract the first one to prove it
        h, ver, hdr, stream, ts = rows[0]
        total = hdr + stream
        f.seek(PKG_LBA * SEC + h)
        blob = f.read(total)
        p = os.path.join(OUT, f"video_{h:08x}.psmf")
        with open(p, "wb") as o:
            o.write(blob)
        print(f"\n  extracted first PSMF: {total:,} bytes -> {os.path.basename(p)}")
        print(f"  head: {blob[:16].hex(' ')}  tail: {blob[-16:].hex(' ')}")

        print("\nSEDB entries (aligned only):")
        sedb = [h for h in scan(f, b"SEDB") if h % 0x800 == 0]
        print(f"  aligned hits: {len(sedb)} / total {len(scan(f, b'SEDB'))}")
        for h in sedb[:8]:
            f.seek(PKG_LBA * SEC + h)
            d = f.read(0x30)
            print(f"    off={h:#010x} magic={d[:8]!r} v={struct.unpack_from('<I', d, 8)[0]} "
                  f"unk={struct.unpack_from('<I', d, 12)[0]:#x} size={struct.unpack_from('<I', d, 16)[0]:,}")

        print("\npack entries (aligned only):")
        packs = [h for h in scan(f, b"pack") if h % 0x800 == 0]
        print(f"  aligned hits: {len(packs)}")
        for h in packs[:8]:
            f.seek(PKG_LBA * SEC + h)
            d = f.read(0x30)
            print(f"    off={h:#010x} magic={d[:4]!r} v={struct.unpack_from('<I', d, 4)[0]} "
                  f"a={struct.unpack_from('<I', d, 8)[0]:#x} b={struct.unpack_from('<I', d, 12)[0]:#x} "
                  f"c={struct.unpack_from('<I', d, 16)[0]:#x}")

        print("\nRIFF (AT3) entries (aligned only):")
        riff = [h for h in scan(f, b"RIFF") if h % 0x800 == 0]
        print(f"  aligned hits: {len(riff)}")
        for h in riff[:6]:
            f.seek(PKG_LBA * SEC + h)
            d = f.read(0x40)
            print(f"    off={h:#010x} size={struct.unpack_from('<I', d, 4)[0]:,} form={d[8:12]!r} "
                  f"fmt={struct.unpack_from('<H', d, 20)[0]:#06x} ch={struct.unpack_from('<H', d, 22)[0]} "
                  f"rate={struct.unpack_from('<I', d, 24)[0]}")


if __name__ == "__main__":
    main()
