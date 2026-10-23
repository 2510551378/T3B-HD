"""Step 2: extract sample packs to disk and dump their headers byte-precisely."""
import os
import struct
import sys

ROOT = r"C:\Users\25105\Documents\寄生前夜第四日"
ISO = os.path.join(ROOT, r"PSP\The_3rd_birthday_cn_full_v101.iso")
SEC = 2048
PKG_LBA = 59600
OUT = os.path.join(os.path.dirname(__file__), "extract", "packs")

SAMPLES = [
    (0x00058800, 0x53800, "t2_a"),
    (0x00137800, 0x62800, "t11_a"),
    (0x0019a000, 0x2a6000, "t7_a"),
    (0x444e5000, 0x41800, "t8_a"),
    (0x4c685800, 0xC0800, "t12_a"),
    (0x4fea7800, 0x7A000, "t4_a"),
]


def hexdump(d, base=0, limit=0x100):
    for i in range(0, min(len(d), limit), 16):
        c = d[i:i + 16]
        hx = " ".join(f"{b:02x}" for b in c)
        asc = "".join(chr(b) if 32 <= b < 127 else "." for b in c)
        print(f"  {base + i:08x}  {hx:<47}  |{asc}|")


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    os.makedirs(OUT, exist_ok=True)
    with open(ISO, "rb") as f:
        for off, size, tag in SAMPLES:
            f.seek(PKG_LBA * SEC + off)
            blob = f.read(size)
            p = os.path.join(OUT, f"{tag}_0x{off:08x}.pack")
            with open(p, "wb") as o:
                o.write(blob)
            typ = struct.unpack_from("<I", blob, 4)[0]
            hdr = struct.unpack_from("<I", blob, 8)[0]
            print(f"\n=== {tag} type={typ} first_size={hdr:#x} file={size:,}")
            print("   first 0x100:")
            hexdump(blob, 0, 0x100)
            # try: count = ? ; print dwords 8..40
            words = struct.unpack_from("<40I", blob, 0)
            print("   dwords:", " ".join(f"{w:#x}" for w in words[2:22]))


if __name__ == "__main__":
    main()
