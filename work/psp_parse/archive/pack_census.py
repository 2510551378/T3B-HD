"""Census of the 'pack' containers inside 3rd.pkg: type field, offsets, sizes, vertex-likeness."""
import collections
import math
import os
import struct
import sys

ROOT = r"C:\Users\25105\Documents\寄生前夜第四日"
ISO = os.path.join(ROOT, r"PSP\The_3rd_birthday_cn_full_v101.iso")
SEC = 2048
PKG_LBA, PKG_SIZE = 59600, 1344292864


def scan(f, sig):
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


def vertex_score(body):
    """Fraction of 4-byte groups that decode as plausible small floats or small ints."""
    n = len(body) // 4
    if n == 0:
        return 0.0
    good = 0
    step = max(1, n // 4000)
    checked = 0
    for i in range(0, n, step):
        v = struct.unpack_from("<f", body, i * 4)[0]
        checked += 1
        if -1e4 < v < 1e4 and (abs(v) < 1e-6 or 1e-3 < abs(v) < 1e4):
            good += 1
    return good / max(1, checked)


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    with open(ISO, "rb") as f:
        packs = scan(f, b"pack")
        rows = []
        for h in packs:
            f.seek(PKG_LBA * SEC + h)
            d = f.read(0x20)
            if len(d) < 0x20:
                continue
            typ = struct.unpack_from("<I", d, 4)[0]
            f0 = struct.unpack_from("<I", d, 8)[0]
            f1 = struct.unpack_from("<I", d, 12)[0]
            f2 = struct.unpack_from("<I", d, 16)[0]
            rows.append((h, typ, f0, f1, f2))
    by_type = collections.defaultdict(list)
    for r in rows:
        by_type[r[1]].append(r)
    print(f"{'type':>6} {'count':>6} {'offset range':>26} {'sum(f2)':>14}")
    for typ in sorted(by_type):
        rs = by_type[typ]
        print(f"{typ:>6} {len(rs):>6} 0x{min(r[0] for r in rs):08x}..0x{max(r[0] for r in rs):08x} "
              f"{sum(r[4] for r in rs):>14,}")

    print("\nvertex-likeness of a few packs:")
    with open(ISO, "rb") as f:
        for typ in sorted(by_type):
            h, t, f0, f1, f2 = by_type[typ][0]
            size = min(f2 if f2 else 65536, 65536)
            f.seek(PKG_LBA * SEC + h + 0x20)
            body = f.read(size)
            print(f"  type={t:>3} @0x{h:08x} head={body[:16].hex(' ')} vertex_score={vertex_score(body):.2f}")


if __name__ == "__main__":
    main()
