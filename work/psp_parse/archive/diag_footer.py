"""Do the bytes after each vertex run describe a world-space bounding box?"""
import os
import struct
import sys

DIR = os.path.join(os.path.dirname(__file__), "..", "raw", "packs")


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
            runs.append(cur)
            cur = [o]
    runs.append(cur)
    runs.sort()

    print(f"{'run':>3} {'n':>5} {'gap':>4} local bbox (x y z)                    footer s16 head")
    for i, r in enumerate(runs[:-1]):
        end = r[-1] + 20
        nxt = runs[i + 1][0]
        gap = geo[end:nxt]
        P = [struct.unpack_from("<3h", geo, o + 4) for o in r]
        mn = [min(p[j] for p in P) for j in range(3)]
        mx = [max(p[j] for p in P) for j in range(3)]
        s = struct.unpack_from(f"<{min(16, len(gap)//2)}h", gap, 0)
        print(f"{i:>3} {len(r):>5} {len(gap):>4} "
              f"[{mn[0]:>6} {mn[1]:>6} {mn[2]:>6}] .. [{mx[0]:>6} {mx[1]:>6} {mx[2]:>6}]  {list(s[:8])}")
        if i >= 10:
            break


if __name__ == "__main__":
    main()
