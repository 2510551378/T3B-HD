"""Step 21: generalised 'ruler' -- find any u16/u32 constant repeated at a fixed stride inside FEP."""
import collections
import os
import struct
import sys

ROOT = r"C:\Users\25105\Documents\寄生前夜第四日"
ISO = os.path.join(ROOT, r"PSP\The_3rd_birthday_cn_full_v101.iso")
SEC = 2048
PKG_LBA = 59600
DIR = os.path.join(os.path.dirname(__file__), "extract", "packs")


def load(fn):
    with open(os.path.join(DIR, fn), "rb") as f:
        return f.read()


def ruler(blob, width=2):
    n = len(blob) - width
    vals = collections.Counter()
    pos = collections.defaultdict(list)
    fmt = "<H" if width == 2 else "<I"
    for o in range(0, n + 1, width):
        v = struct.unpack_from(fmt, blob, o)[0]
        vals[v] += 1
        if len(pos[v]) < 24000:
            pos[v].append(o)
    out = []
    for v, c in vals.most_common(40):
        if c < 200:
            break
        ps = pos[v]
        d = collections.Counter(b - a for a, b in zip(ps, ps[1:]))
        mode, cnt = d.most_common(1)[0]
        if cnt > 100:
            out.append((cnt, mode, v, c))
    out.sort(reverse=True)
    return out


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    t12 = load("t12_a_0x4c685800.pack")
    fep = t12[0x130:0x130 + 0xA4860]
    print(f"t12 FEP {len(fep):,} B")
    for width in (2, 4):
        res = ruler(fep, width)
        tag = {2: "  u16", 4: "  u32"}[width]
        print(f"{tag} rulers (mode_delta, value, count):")
        for cnt, mode, v, c in res[:8]:
            print(f"    stride={mode:>4}  value={v:#06x}  pairs={cnt:>6}  occ={c}")


if __name__ == "__main__":
    main()
