"""Are the 'pack' entries contiguous? Test candidate size fields like we did for PSMF/SEDB."""
import os
import struct
import sys

ROOT = r"C:\Users\25105\Documents\寄生前夜第四日"
ISO = os.path.join(ROOT, r"PSP\The_3rd_birthday_cn_full_v101.iso")
SEC = 2048
PKG_LBA, PKG_SIZE = 59600, 1344292864


def align(v, a=0x800):
    return (v + a - 1) // a * a


def scan_offsets(f, sig):
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
            i = buf.find(sig, i)
            if i < 0:
                break
            if (pos + i) % 0x800 == 0:
                out.append(pos + i)
            i += 1
        pos += len(buf)
    return out


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    with open(ISO, "rb") as f:
        packs = scan_offsets(f, b"pack")
        print(f"aligned 'pack' starts: {len(packs)}")
        heads = []
        for h in packs:
            f.seek(PKG_LBA * SEC + h)
            d = f.read(0x30)
            w = struct.unpack_from("<7I", d, 4)
            heads.append((h, w))
        for idx in (8, 12, 16, 20, 24):
            ok = 0
            for i in range(len(heads) - 1):
                h, w = heads[i]
                size = w[idx - 1] if idx - 1 < len(w) else 0
                if size and align(h + size) == heads[i + 1][0]:
                    ok += 1
            print(f"  field @+{idx:>2} as size: contiguous {ok}/{len(heads) - 1}")
        print("\nsample heads:")
        for h, w in heads[:6]:
            print(f"  0x{h:08x}: " + " ".join(f"{x:#x}" for x in w))
        print("\ntail heads:")
        for h, w in heads[-6:]:
            print(f"  0x{h:08x}: " + " ".join(f"{x:#x}" for x in w))


if __name__ == "__main__":
    main()
