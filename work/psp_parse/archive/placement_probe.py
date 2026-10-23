"""Does every pack carry a world-space bbox (section 1) that differs per room?"""
import os
import struct
import sys

ROOT = r"C:\Users\25105\Documents\寄生前夜第四日"
ISO = os.path.join(ROOT, r"PSP\The_3rd_birthday_cn_full_v101.iso")
SEC = 2048
PKG_LBA, PKG_SIZE = 59600, 1344292864
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tools"))
from psp_pack import parse_pack, iter_pack_offsets, open_pack  # noqa: E402


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    with open(ISO, "rb") as f:
        offs = iter_pack_offsets(f)
        spans = {o: (offs[i + 1] if i + 1 < len(offs) else PKG_SIZE) - o for i, o in enumerate(offs)}
        n = 0
        for o in offs:
            buf = open_pack(f, o, spans[o])
            p = parse_pack(buf, o, spans[o])
            if p.type != 8 or len(p.sections) < 2:
                continue
            sz, so = p.sections[1]
            s1 = buf[so:so + sz]
            if len(s1) < 0x40:
                continue
            hdr = struct.unpack_from("<8I", s1, 0)
            fl = struct.unpack_from("<12f", s1, 0x20)
            print(f"0x{o:08x} s1={sz:>6}  hdr={[hex(x) for x in hdr[:7]]}")
            print(f"           floats={[round(x,2) for x in fl]}")
            n += 1
            if n >= 6:
                break


if __name__ == "__main__":
    main()
