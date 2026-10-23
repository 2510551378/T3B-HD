"""Look at pkg surroundings: signature hits, tail, and region boundaries."""
import math
import os
import struct
import sys

ROOT = r"C:\Users\25105\Documents\寄生前夜第四日"
ISO = os.path.join(ROOT, r"PSP\The_3rd_birthday_cn_full_v101.iso")
SEC = 2048
PKG_LBA, PKG_SIZE = 59600, 1344292864


def hexdump(f, base_off, length=256, label=""):
    f.seek(PKG_LBA * SEC + base_off)
    data = f.read(length)
    print(f"--- {label} @ 0x{base_off:x} (pkg offset) ---")
    for i in range(0, len(data), 16):
        chunk = data[i:i + 16]
        hx = " ".join(f"{b:02x}" for b in chunk)
        asc = "".join(chr(b) if 32 <= b < 127 else "." for b in chunk)
        print(f"  {base_off + i:010x}  {hx:<47}  |{asc}|")
    print()


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    with open(ISO, "rb") as f:
        hexdump(f, 0x0006800, 512, "after first PNG (padding?)")
        hexdump(f, 0x0006FF0, 96, "next PNG start")
        hexdump(f, 0x00058700, 512, "'pack' hit 0x58800")
        hexdump(f, 0x001AD700, 512, "SEDB hit 0x1ad800")
        hexdump(f, 0x005F6100, 512, "RIFF hit 0x5f61f0")
        hexdump(f, 0x03472700, 512, "PSMF hit 0x3472800")
        hexdump(f, 0x4FEA8700, 512, "near '0x4fea8800'")
        hexdump(f, PKG_SIZE - 4096, 4096, "pkg tail 4 KiB")
        hexdump(f, PKG_SIZE - 65536, 1024, "pkg tail-64K start")

    # entropy in 4 KiB windows over the last 64 MiB to find the structured zone
    print("### entropy per 1 MiB, last 64 MiB")
    with open(ISO, "rb") as f:
        for k in range(64):
            off = PKG_SIZE - 64 * 1024 * 1024 + k * 1024 * 1024
            f.seek(PKG_LBA * SEC + off)
            d = f.read(1 << 20)
            c = [0] * 256
            for x in d:
                c[x] += 1
            n = len(d)
            e = -sum((v / n) * math.log2(v / n) for v in c if v)
            print(f"  {off:>10} (0x{off:08x})  entropy={e:.3f}")


if __name__ == "__main__":
    main()
