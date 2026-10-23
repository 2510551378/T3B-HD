"""Step 23: dump the small records that sit between vertex runs (material binding?)."""
import os
import struct
import sys

DIR = os.path.join(os.path.dirname(__file__), "extract", "packs")


def load(fn):
    with open(os.path.join(DIR, fn), "rb") as f:
        return f.read()


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    t8 = load("t8_a_0x444e5000.pack")
    sec = t8[0x80:0x80 + 0x37250]
    geo = sec[0x30:0x225E8]
    verts = [o for o in range(0, len(geo) - 20, 2) if geo[o + 10:o + 12] == b"\xcc\xcc"]
    runs = []
    cur = [verts[0]]
    for o in verts[1:]:
        if o - cur[-1] == 20:
            cur.append(o)
        else:
            runs.append((cur[0], len(cur)))
            cur = [o]
    runs.append((cur[0], len(cur)))
    runs.sort()
    print(f"{len(runs)} runs; dumping the bytes after each run")
    for i, (st, n) in enumerate(runs):
        end = st + n * 20
        nxt = runs[i + 1][0] if i + 1 < len(runs) else len(geo)
        gap = geo[end:min(nxt, end + 80)]
        print(f"  run {i:>2} n={n:>5} end=0x{end:06x} gap={nxt - end:>3}  {gap.hex(' ')}")
        if i >= 12:
            break
    print("\nheader area 0x30..0x268:")
    for o in range(0x30, 0x270, 16):
        c = geo[o:o + 16]
        print(f"  {o:05x}  {' '.join('%02x' % b for b in c)}")


if __name__ == "__main__":
    main()
