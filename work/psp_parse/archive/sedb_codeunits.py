"""Check whether SEDB payload is fixed 16-bit code units (glyph indices) or a byte stream."""
import collections
import glob
import os
import struct
import sys

SEQ = os.path.join(os.path.dirname(__file__), "extract", "sedb")


def load(n):
    p = glob.glob(os.path.join(SEQ, f"sedb_{n:03d}_*.bin"))[0]
    with open(p, "rb") as f:
        return os.path.basename(p), f.read()


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    for n in (0, 244, 1):
        name, blob = load(n)
        body = blob[0xC0:]
        u16 = [struct.unpack_from("<H", body, i)[0] for i in range(0, len(body) - 1, 2)]
        c = collections.Counter(u16)
        top = c.most_common(12)
        print(f"== {name}  body={len(body):,}  u16_count={len(u16):,}  distinct={len(c):,}")
        print("   top u16:", [(hex(k), v) for k, v in top])
        # how many u16 are < 0x1000
        small = sum(v for k, v in c.items() if k < 0x1000)
        print(f"   u16 < 0x1000: {small:,} ({small / len(u16) * 100:.1f}%)")
        # tag histogram at 16-byte boundaries
        tags = collections.Counter()
        for i in range(0, len(body) - 1, 16):
            tags[struct.unpack_from("<H", body, i)[0]] += 1
        print(f"   16B-record tags (top 8): {[(hex(k), v) for k, v in tags.most_common(8)]}")
        print()


if __name__ == "__main__":
    main()
