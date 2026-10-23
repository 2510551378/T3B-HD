"""Step 15: index-buffer detector (u16 windows where nearly all values fall below a small bound)."""
import os
import struct
import sys

DIR = os.path.join(os.path.dirname(__file__), "extract", "packs")


def load(fn):
    with open(os.path.join(DIR, fn), "rb") as f:
        return f.read()


def windows(b, win=512, step=256, bound=8192):
    n = len(b) // 2
    hit = []
    for start in range(0, n - win, step):
        vals = struct.unpack_from(f"<{win}H", b, start * 2)
        mx = max(vals)
        if mx == 0:
            continue
        small = sum(1 for v in vals if v <= bound)
        frac = small / win
        if frac > 0.97 and mx <= bound:
            uniq = len(set(vals))
            if uniq > win * 0.2:
                hit.append((start * 2, mx, uniq, frac))
    return hit


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    t8 = load("t8_a_0x444e5000.pack")
    sec = t8[0x80:0x80 + 0x37250]
    for name, region in (("t8 section0", sec), ("t8 0x30..0x225e8", sec[0x30:0x225E8]),
                         ("t8 0x37300..", t8[0x37300:0x37300 + 0x291c])):
        hits = windows(region)
        print(f"\n{name}: {len(hits)} index-like windows")
        for off, mx, uniq, frac in hits[:6]:
            print(f"  @0x{off:06x} max={mx} uniq={uniq} frac={frac:.3f}")
        if hits:
            runs = []
            cur = [hits[0]]
            for h in hits[1:]:
                if h[0] - cur[-1][0] <= 0x200:
                    cur.append(h)
                else:
                    runs.append(cur)
                    cur = [h]
            runs.append(cur)
            runs.sort(key=len, reverse=True)
            for r in runs[:3]:
                print(f"   run 0x{r[0][0]:06x}..0x{r[-1][0]:06x} windows={len(r)} "
                      f"max~{max(x[1] for x in r)}")


if __name__ == "__main__":
    main()
