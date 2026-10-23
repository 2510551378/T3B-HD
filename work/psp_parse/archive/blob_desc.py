"""Step 12: do the big 'blob' sections share a descriptor layout? Compare first 0x30 bytes."""
import collections
import os
import struct
import sys

ROOT = r"C:\Users\25105\Documents\寄生前夜第四日"
ISO = os.path.join(ROOT, r"PSP\The_3rd_birthday_cn_full_v101.iso")
SEC = 2048
PKG_LBA, PKG_SIZE = 59600, 1344292864
sys.path.insert(0, os.path.dirname(__file__))
from psp_pack import parse_pack, iter_pack_offsets, open_pack  # noqa: E402


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    heads = []
    with open(ISO, "rb") as f:
        offs = iter_pack_offsets(f)
        spans = {o: (offs[i + 1] if i + 1 < len(offs) else PKG_SIZE) - o for i, o in enumerate(offs)}
        for o in offs:
            buf = open_pack(f, o, spans[o])
            p = parse_pack(buf, o, spans[o])
            if p.type not in (8, 12) or not p.sections:
                continue
            big = max(p.sections, key=lambda s: s[0])
            sz, off = big
            heads.append((p.type, o, sz, off, buf[off:off + 0x30]))
    print(f"type 8/12 packs: {len(heads)}")
    # word 1 (offset 4) distribution
    w1 = collections.Counter(struct.unpack_from("<I", h[4], 4)[0] for h in heads)
    print("dword@+4 distribution:", {hex(k): v for k, v in w1.most_common(8)})
    w2 = collections.Counter(struct.unpack_from("<H", h[4], 4)[0] for h in heads)
    print("u16@+4  distribution:", {hex(k): v for k, v in w2.most_common(8)})
    print("\nsample heads (type, pack, size, head):")
    for t, o, sz, off, h in heads[:12]:
        print(f"  t{t:<3} 0x{o:08x} sz={sz:>9,} {h.hex(' ')}")
    # count how many have the same first 8 bytes pattern 00000000 at +0
    z = sum(1 for h in heads if h[:4] == b"\x00\x00\x00\x00")
    print(f"\nfirst dword zero: {z}/{len(heads)}")


if __name__ == "__main__":
    main()
