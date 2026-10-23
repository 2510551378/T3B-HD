"""Extract every plaintext PNG from the head of 3rd.pkg and re-extract video #0 with the correct BE size."""
import os
import struct
import sys

ROOT = r"C:\Users\25105\Documents\寄生前夜第四日"
ISO = os.path.join(ROOT, r"PSP\The_3rd_birthday_cn_full_v101.iso")
OUT = os.path.join(os.path.dirname(__file__), "extract")
SEC = 2048
PKG_LBA, PKG_SIZE = 59600, 1344292864


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    os.makedirs(OUT, exist_ok=True)
    with open(ISO, "rb") as f:
        # --- all PNGs in the pkg
        f.seek(PKG_LBA * SEC)
        pos, left = 0, PKG_SIZE
        hits = []
        CH = 1 << 23
        while left > 0:
            buf = f.read(min(CH, left))
            if not buf:
                break
            left -= len(buf)
            i = 0
            while True:
                i = buf.find(b"\x89PNG\r\n\x1a\n", i)
                if i < 0:
                    break
                hits.append(pos + i)
                i += 1
            pos += len(buf)
        print(f"PNG hits in pkg: {len(hits)}")
        for n, off in enumerate(hits):
            f.seek(PKG_LBA * SEC + off)
            d = f.read(33)
            w, h = struct.unpack_from(">II", d, 16)
            p = 8
            while True:
                f.seek(PKG_LBA * SEC + off + p)
                hdr = f.read(8)
                if len(hdr) < 8:
                    break
                ln, typ = struct.unpack(">I4s", hdr)
                p += 12 + ln
                if typ == b"IEND":
                    break
            f.seek(PKG_LBA * SEC + off)
            blob = f.read(p)
            name = f"pkg_{n:02d}_0x{off:08x}_{w}x{h}.png"
            with open(os.path.join(OUT, name), "wb") as o:
                o.write(blob)
            print(f"  [{n:>2}] 0x{off:08x} {w}x{h} {p:>8,} B -> {name}")

        # --- video #0 with correct big-endian size
        h = 0x03472800
        f.seek(PKG_LBA * SEC + h)
        d = f.read(0x10)
        hdr = struct.unpack_from(">I", d, 8)[0]
        stream = struct.unpack_from(">I", d, 12)[0]
        total = hdr + stream
        f.seek(PKG_LBA * SEC + h)
        blob = f.read(total)
        name = "video_01_0x03472800.psmf"
        with open(os.path.join(OUT, name), "wb") as o:
            o.write(blob)
        print(f"\nvideo #1: {total:,} B -> {name}  (was wrongly 14,195,202 B)")
        old = os.path.join(OUT, "video_03472800.psmf")
        if os.path.exists(old):
            os.remove(old)
            print("  removed the truncated old extraction")


if __name__ == "__main__":
    main()
