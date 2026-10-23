"""Step 19: order the vertex runs and look for index buffers in the gaps."""
import os
import struct
import sys

DIR = os.path.join(os.path.dirname(__file__), "extract", "packs")


def load(fn):
    with open(os.path.join(DIR, fn), "rb") as f:
        return f.read()


def index_score(blob, off, count, n):
    """Fraction of the next `count` indices that are < n."""
    if off + count > len(blob):
        return None
    vals = struct.unpack_from(f"<{count}H", blob, off)
    return sum(1 for v in vals if v < n) / count, max(vals)


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
    print(f"{len(runs)} runs")
    print(f"{'#':>3} {'start':>8} {'nverts':>7} {'end':>8} {'gap_after':>10}")
    for i, (st, n) in enumerate(runs):
        end = st + n * 20
        nxt = runs[i + 1][0] if i + 1 < len(runs) else len(geo)
        print(f"{i:>3} 0x{st:06x} {n:>7} 0x{end:06x} {nxt - end:>10}")

    print("\ngap analysis (u16 index hypothesis):")
    for i, (st, n) in enumerate(runs[:-1]):
        end = st + n * 20
        nxt = runs[i + 1][0]
        gap = nxt - end
        if gap <= 0:
            continue
        r = index_score(geo, end, min(gap // 2, 64), n)
        if r:
            frac, mx = r
            print(f"  after run {i:>2} (n={n:>4}) gap={gap:>5}: first 32 u16 <{n}? frac={frac:.2f} max={mx}")
    # also u32
    print("\ngap analysis (u32 index hypothesis):")
    for i, (st, n) in enumerate(runs[:-1]):
        end = st + n * 20
        nxt = runs[i + 1][0]
        gap = nxt - end
        if gap < 64:
            continue
        vals = struct.unpack_from("<32I", geo, end)
        frac = sum(1 for v in vals if v < n) / 32
        print(f"  after run {i:>2} (n={n:>4}) gap={gap:>6}: u32 frac<{n}={frac:.2f} first={vals[:6]}")


if __name__ == "__main__":
    main()
