"""Locate 0x800-aligned file starts in 3rd.pkg (zero block followed by data) and match to fsd."""
import os
import struct
import sys

ROOT = r"C:\Users\25105\Documents\寄生前夜第四日"
ISO = os.path.join(ROOT, r"PSP\The_3rd_birthday_cn_full_v101.iso")
SEC = 2048
PKG_LBA, PKG_SIZE = 59600, 1344292864
FSD_LBA, FSD_SIZE = 59584, 7932
BLK = 0x800


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    starts = []
    prev_zero = None
    with open(ISO, "rb") as f:
        f.seek(PKG_LBA * SEC)
        pos = 0
        left = PKG_SIZE
        CH = 1 << 23
        carry = b""
        while left > 0:
            chunk = f.read(min(CH, left))
            if not chunk:
                break
            left -= len(chunk)
            buf = carry + chunk
            n = len(buf) // BLK
            for i in range(n):
                blk = buf[i * BLK:(i + 1) * BLK]
                zero = not any(blk)
                off = pos - len(carry) + i * BLK
                if prev_zero is False and zero:
                    pass
                if prev_zero is True and not zero:
                    starts.append(off)
                prev_zero = zero
            carry = buf[n * BLK:]
            pos += len(chunk)
    print(f"0x800-aligned starts after zero block: {len(starts)}")
    print("first 20:", [hex(x) for x in starts[:20]])
    print("last 5:", [hex(x) for x in starts[-5:]])

    with open(ISO, "rb") as f:
        f.seek(FSD_LBA * SEC)
        fsd = f.read(FSD_SIZE)
    dwords = [struct.unpack_from("<I", fsd, o)[0] for o in range(0, len(fsd) - 3, 4)]
    sset = set(starts)
    found = {}
    for idx, v in enumerate(dwords):
        for name, c in (("v", v), ("v&~ff", v & 0xFFFFFF00), ("v>>8", v >> 8),
                        ("v&~fff", v & 0xFFFFF000)):
            if c in sset:
                found.setdefault(name, []).append((idx, hex(v), hex(c)))
    for k, arr in found.items():
        print(f"fsd dword match via {k}: {len(arr)} e.g. {arr[:6]}")

    # how many starts are multiples of 0x1000 too
    print("starts %0x1000 ==0:", sum(1 for x in starts if x % 0x1000 == 0), "of", len(starts))
    # distribution of gaps
    gaps = [starts[i + 1] - starts[i] for i in range(len(starts) - 1)]
    from collections import Counter
    print("gap histogram (top 10):", Counter(gaps).most_common(10))


if __name__ == "__main__":
    main()
