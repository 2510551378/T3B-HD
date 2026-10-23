"""ram_diag.py -- what shapes does the savestate RAM actually hold?"""
import collections
import struct
import sys

sys.path.insert(0, r"work\psp_parse\tools")
from pack_export import find_runs, SCALE  # noqa: E402


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    blob = open(r"work\psp_parse\raw\ram.bin", "rb").read()
    runs = [r for r in find_runs(blob) if len(r) >= 3]
    info = []
    for r in runs:
        xs, ys, zs = [], [], []
        for o in r:
            x, y, z = struct.unpack_from("<3h", blob, o + 4)
            xs.append(x * SCALE)
            ys.append(y * SCALE)
            zs.append(z * SCALE)
        info.append((max(ys) - min(ys), max(xs) - min(xs), max(zs) - min(zs), len(r), r[0]))
    info.sort(reverse=True)

    print("runs sorted by height (dy):")
    for dy, dx, dz, n, off in info[:12]:
        print(f"  @0x{off:08x} {n:>5}v  {dx:.2f} x {dy:.2f} x {dz:.2f} m")

    c = collections.Counter(round(t[0], 1) for t in info)
    print("\ndy histogram:")
    for k in sorted(c)[:12]:
        print(f"  dy~{k:.1f} m : {c[k]} runs")

    i = 0
    n = 0
    while n < 14:
        i = blob.find(b"FEP", i)
        if i < 0:
            break
        print(f"FEP @0x{i:08x} ver={blob[i + 3]} hdr={blob[i + 4:i + 12].hex()}")
        i += 3
        n += 1


if __name__ == "__main__":
    main()
