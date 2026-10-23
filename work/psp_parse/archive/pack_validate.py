"""Step 6: validate the (size, offset) section model across ALL 436 packs."""
import collections
import os
import struct
import sys

ROOT = r"C:\Users\25105\Documents\寄生前夜第四日"
ISO = os.path.join(ROOT, r"PSP\The_3rd_birthday_cn_full_v101.iso")
SEC = 2048
PKG_LBA, PKG_SIZE = 59600, 1344292864


def align(v, a=0x800):
    return (v + a - 1) // a * a


def find_packs(f):
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
    with open(ISO, "rb") as f:
        starts = find_packs(f)
        print(f"packs: {len(starts)}")
        nxt = {starts[i]: (starts[i + 1] if i + 1 < len(starts) else PKG_SIZE)
               for i in range(len(starts))}
        stats = collections.Counter()
        examples = {}
        for h in starts:
            f.seek(PKG_LBA * SEC + h)
            hdr = f.read(0x100)
            typ = struct.unpack_from("<I", hdr, 4)[0]
            pairs = []
            for i in range(60):
                o = 8 + i * 8
                if o + 8 > len(hdr):
                    break
                sz, off = struct.unpack_from("<II", hdr, o)
                pairs.append((sz, off))
                if sz == 0 and off == 0:
                    break
            # model: first pair's offset == header size; sections tile
            hdr_size = pairs[0][1] if pairs else 0
            end = None
            exact = 0
            aligned = 0
            for i, (sz, off) in enumerate(pairs):
                if sz == 0:
                    continue
                if end is not None:
                    if off == end:
                        exact += 1
                    elif align(off, 0x10) == align(end, 0x10):
                        aligned += 1
                end = off + sz
            span = nxt[h] - h
            fits = end is not None and align(end) <= span
            stats[(typ, bool(fits))] += 1
            examples.setdefault(typ, []).append((h, len(pairs), exact, aligned, end, span))
        print(f"{'type':>5} {'fits':>6} {'total':>6}")
        for (typ, fits), n in sorted(stats.items()):
            print(f"{typ:>5} {str(fits):>6} {n:>6}")
        print("\nexamples:")
        for typ in sorted(examples):
            h, np_, exact, aligned, end, span = examples[typ][0]
            print(f"  type={typ:>2} @0x{h:08x} pairs={np_:>2} exact={exact:>2} aligned={aligned:>2} "
                  f"end={end if end is None else hex(end)} span={hex(span)}")


if __name__ == "__main__":
    main()
