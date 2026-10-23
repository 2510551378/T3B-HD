"""Step 1: dump pack headers, test (size, offset) pair hypotheses against the next-pack oracle."""
import os
import struct
import sys

ROOT = r"C:\Users\25105\Documents\寄生前夜第四日"
ISO = os.path.join(ROOT, r"PSP\The_3rd_birthday_cn_full_v101.iso")
SEC = 2048
PKG_LBA, PKG_SIZE = 59600, 1344292864
OUT = os.path.join(os.path.dirname(__file__), "extract", "packs")


def align(v, a=0x800):
    return (v + a - 1) // a * a


def scan_packs(f):
    f.seek(PKG_LBA * SEC)
    pos, left, out = 0, PKG_SIZE, []
    CH = 1 << 23
    while left > 0:
        buf = f.read(min(CH, left))
        if not buf:
            break
        left -= len(buf)
        i = 0
        while True:
            i = buf.find(b"pack", i)
            if i < 0:
                break
            if (pos + i) % 0x800 == 0:
                out.append(pos + i)
            i += 1
        pos += len(buf)
    return out


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    os.makedirs(OUT, exist_ok=True)
    with open(ISO, "rb") as f:
        starts = scan_packs(f)
        print(f"packs: {len(starts)}")
        # one sample per (type, index-in-type)
        samples = []
        seen = {}
        for h in starts:
            f.seek(PKG_LBA * SEC + h)
            d = f.read(0x40)
            typ = struct.unpack_from("<I", d, 4)[0]
            seen.setdefault(typ, 0)
            if seen[typ] < 2:
                samples.append((h, typ, d))
            seen[typ] += 1
        for h, typ, d in samples:
            print(f"\n=== pack @0x{h:08x} type={typ}")
            words = struct.unpack_from("<16I", d, 0)
            print("   dwords:", " ".join(f"{w:#x}" for w in words))
            # next pack start
            nxt = [s for s in starts if s > h]
            print(f"   next pack @0x{min(nxt):08x}  (delta {min(nxt) - h:,})" if nxt else "   last pack")
            # hypothesis: after magic+type, pairs (size, offset); first offset == header size
            for i in range(0, 12):
                pass


if __name__ == "__main__":
    main()
