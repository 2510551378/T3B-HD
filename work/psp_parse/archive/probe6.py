"""Clean fsd record dump + extract the plaintext PNGs at the head of 3rd.pkg."""
import os
import struct
import sys

ROOT = r"C:\Users\25105\Documents\寄生前夜第四日"
ISO = os.path.join(ROOT, r"PSP\The_3rd_birthday_cn_full_v101.iso")
OUT = os.path.join(os.path.dirname(__file__), "extract")
SEC = 2048
PKG_LBA = 59600
FSD_LBA, FSD_SIZE = 59584, 7932
PNG_OFFS = [0x0, 0x7000, 0xA000, 0x11000, 0x17800]


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    os.makedirs(OUT, exist_ok=True)
    with open(ISO, "rb") as f:
        f.seek(FSD_LBA * SEC)
        fsd = f.read(FSD_SIZE)
        hdr = struct.unpack_from("<6I", fsd, 0)
        print("fsd header dwords:", [hex(x) for x in hdr])
        print("  fields: ver=%d hdr=%d f2=%d f3=%d f4=%d size=%d" % hdr)
        print("  pkg_size_field = %#x (%d)  vs real %d" % (
            struct.unpack_from("<I", fsd, 0x18)[0],
            struct.unpack_from("<I", fsd, 0x18)[0], 1344292864))
        print("\nrecords from 0x70c (value,type):")
        for i in range(6):
            o = 0x70C + i * 8
            a, b = struct.unpack_from("<II", fsd, o)
            print(f"  [{i:>3}] @{o:#06x}  {a:#010x} {b:#010x}   (b as type)")
        print("  ...")
        for i in range(760, 766):
            o = 0x70C + i * 8
            if o + 8 > len(fsd):
                break
            a, b = struct.unpack_from("<II", fsd, o)
            print(f"  [{i:>3}] @{o:#06x}  {a:#010x} {b:#010x}")
        # how many distinct 'type' words
        types = {}
        for o in range(0x70C, len(fsd) - 7, 8):
            a, b = struct.unpack_from("<II", fsd, o)
            types[b] = types.get(b, 0) + 1
        print("\n  type-word histogram:", {hex(k): v for k, v in list(types.items())[:8]})

        # extract head PNGs
        print("\nPNGs at head of 3rd.pkg:")
        for off in PNG_OFFS:
            f.seek(PKG_LBA * SEC + off)
            d = f.read(33)
            if d[:8] != b"\x89PNG\r\n\x1a\n":
                print(f"  {off:#08x}: not PNG")
                continue
            w, h = struct.unpack_from(">II", d, 16)
            f.seek(PKG_LBA * SEC + off)
            p = 8
            while True:
                f.seek(PKG_LBA * SEC + off + p)
                hdr = f.read(8)
                ln, typ = struct.unpack(">I4s", hdr)
                p += 12 + ln
                if typ == b"IEND":
                    break
            f.seek(PKG_LBA * SEC + off)
            blob = f.read(p)
            name = f"pkg_{off:08x}_{w}x{h}.png"
            with open(os.path.join(OUT, name), "wb") as o:
                o.write(blob)
            print(f"  {off:#08x}: {w}x{h}  {p:,} bytes -> {name}")


if __name__ == "__main__":
    main()
