"""Step 9: per-pack coverage - do the header sections account for the whole container?"""
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
    rows = []
    with open(ISO, "rb") as f:
        offs = iter_pack_offsets(f)
        spans = {o: (offs[i + 1] if i + 1 < len(offs) else PKG_SIZE) - o for i, o in enumerate(offs)}
        for o in offs:
            buf = open_pack(f, o, spans[o])
            p = parse_pack(buf, o, spans[o])
            covered = sum(sz for sz, _ in p.sections)
            rows.append((o, p.type, len(p.sections), p.hdr_size, covered, p.span,
                         covered / p.span if p.span else 0))
    rows.sort(key=lambda r: -r[5])
    print(f"{'offset':>12} {'type':>4} {'secs':>5} {'hdr':>7} {'covered':>12} {'span':>12} {'ratio':>6}")
    for r in rows[:15]:
        print(f"0x{r[0]:08x} {r[1]:>4} {r[2]:>5} {r[3]:>7} {r[4]:>12,} {r[5]:>12,} {r[6]:>6.2f}")
    print("...")
    for r in rows[-5:]:
        print(f"0x{r[0]:08x} {r[1]:>4} {r[2]:>5} {r[3]:>7} {r[4]:>12,} {r[5]:>12,} {r[6]:>6.2f}")
    big = [r for r in rows if r[5] > 1_000_000]
    print(f"\npacks >1 MB: {len(big)}, their span sum = {sum(r[5] for r in big):,}, "
          f"covered = {sum(r[4] for r in big):,}")
    for r in big[:10]:
        print(f"  0x{r[0]:08x} type={r[1]} span={r[5]:,} covered={r[4]:,} ratio={r[6]:.2f} secs={r[2]}")


if __name__ == "__main__":
    main()
