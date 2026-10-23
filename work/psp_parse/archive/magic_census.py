"""Census of 8-byte magics at every 0x800 boundary inside 3rd.pkg."""
import collections
import os
import sys

ROOT = r"C:\Users\25105\Documents\寄生前夜第四日"
ISO = os.path.join(ROOT, r"PSP\The_3rd_birthday_cn_full_v101.iso")
SEC = 2048
PKG_LBA, PKG_SIZE = 59600, 1344292864
BLK = 0x800


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    counts = collections.Counter()
    first = {}
    with open(ISO, "rb") as f:
        f.seek(PKG_LBA * SEC)
        pos, left = 0, PKG_SIZE
        CH = 1 << 22
        carry = b""
        while left > 0:
            chunk = f.read(min(CH, left))
            if not chunk:
                break
            left -= len(chunk)
            buf = carry + chunk
            base = pos - len(carry)
            n = len(buf) // BLK
            for i in range(n):
                off = base + i * BLK
                if off >= PKG_SIZE:
                    break
                key = bytes(buf[i * BLK:i * BLK + 8])
                counts[key] += 1
                first.setdefault(key, off)
            carry = buf[n * BLK:]
            pos += len(chunk)

    print(f"distinct 8-byte block heads: {len(counts)}")
    for key, n in counts.most_common(60):
        if key == b"\x00" * 8:
            continue
        asc = "".join(chr(b) if 32 <= b < 127 else "." for b in key)
        print(f"  {n:>6}  {key.hex(' ')}  |{asc}|  first@0x{first[key]:08x}")


if __name__ == "__main__":
    main()
