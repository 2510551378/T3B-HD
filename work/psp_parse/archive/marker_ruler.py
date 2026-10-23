"""Step 16: use the repeated 0xCCCC marker as a stride ruler."""
import collections
import os
import sys

DIR = os.path.join(os.path.dirname(__file__), "extract", "packs")


def load(fn):
    with open(os.path.join(DIR, fn), "rb") as f:
        return f.read()


def marker_deltas(b, marker=b"\xcc\xcc"):
    pos = []
    i = 0
    while True:
        i = b.find(marker, i)
        if i < 0:
            break
        if i % 2 == 0:
            pos.append(i)
        i += 1
    d = [b - a for a, b in zip(pos, pos[1:])]
    return pos, collections.Counter(d).most_common(12)


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    t8 = load("t8_a_0x444e5000.pack")
    sec = t8[0x80:0x80 + 0x37250]
    t12 = load("t12_a_0x4c685800.pack")
    fep = t12[0x130:0x130 + 0xA4860]
    for name, blob in (("t8 geometry 0x30..0x225e8", sec[0x30:0x225E8]),
                       ("t8 whole section", sec),
                       ("t12 FEP", fep)):
        pos, top = marker_deltas(blob)
        print(f"\n{name}: {len(pos)} markers, top deltas {top}")
        if pos:
            print("  first markers:", [hex(p) for p in pos[:10]])


if __name__ == "__main__":
    main()
