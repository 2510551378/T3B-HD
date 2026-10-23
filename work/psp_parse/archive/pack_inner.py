"""Step 4: hunt for inner chunk magics (FEP etc.) across pack samples and the whole pkg."""
import collections
import os
import struct
import sys

ROOT = r"C:\Users\25105\Documents\寄生前夜第四日"
ISO = os.path.join(ROOT, r"PSP\The_3rd_birthday_cn_full_v101.iso")
SEC = 2048
PKG_LBA, PKG_SIZE = 59600, 1344292864
DIR = os.path.join(os.path.dirname(__file__), "extract", "packs")


def hexdump(d, base=0, limit=0x80):
    for i in range(0, min(len(d), limit), 16):
        c = d[i:i + 16]
        hx = " ".join(f"{b:02x}" for b in c)
        asc = "".join(chr(b) if 32 <= b < 127 else "." for b in c)
        print(f"  {base + i:08x}  {hx:<47}  |{asc}|")


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    for fn in sorted(os.listdir(DIR)):
        p = os.path.join(DIR, fn)
        blob = open(p, "rb").read()
        n_fep = blob.count(b"FEP")
        n_gim = blob.count(b"MIG.00")
        print(f"\n{fn}  size={len(blob):,}  FEP={n_fep}  GIM={n_gim}")
        # position of first FEP
        i = blob.find(b"FEP")
        if i >= 0:
            print(f"  first FEP @0x{i:x}:")
            hexdump(blob[i:i + 0x60], i)

    print("\n=== FEP inside whole pkg")
    with open(ISO, "rb") as f:
        f.seek(PKG_LBA * SEC)
        pos, left = 0, PKG_SIZE
        cnt = 0
        firsts = []
        CH = 1 << 23
        while left > 0:
            buf = f.read(min(CH, left))
            if not buf:
                break
            left -= len(buf)
            i = 0
            while True:
                i = buf.find(b"FEP", i)
                if i < 0:
                    break
                cnt += 1
                if len(firsts) < 5:
                    firsts.append(pos + i)
                i += 1
            pos += len(buf)
    print(f"  count={cnt} first={[hex(x) for x in firsts]}")


if __name__ == "__main__":
    main()
