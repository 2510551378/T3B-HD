"""Step 24: per-pack bounding boxes -- find character-proportioned packs."""
import glob
import os
import sys

DIR = os.path.join(os.path.dirname(__file__), "export")


def bbox(path):
    xs = []
    ys = []
    zs = []
    with open(path, "r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            if line.startswith("v "):
                _, x, y, z = line.split()
                xs.append(float(x))
                ys.append(float(y))
                zs.append(float(z))
    if not xs:
        return None
    return (min(xs), max(xs), min(ys), max(ys), min(zs), max(zs), len(xs))


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    rows = []
    for p in glob.glob(os.path.join(DIR, "*.obj")):
        b = bbox(p)
        if not b:
            continue
        dx, dy, dz = b[1] - b[0], b[3] - b[2], b[5] - b[4]
        rows.append((os.path.basename(p), b[6], dx, dy, dz))
    rows.sort(key=lambda r: -r[1])
    print(f"{'obj':>28} {'verts':>7} {'dx':>7} {'dy':>7} {'dz':>7}  h>w?")
    for name, n, dx, dy, dz in rows[:10]:
        print(f"{name:>28} {n:>7} {dx:>7.2f} {dy:>7.2f} {dz:>7.2f}")
    print("\ncharacter-proportioned candidates (1.2 < dy < 2.5, dx,dz < 2.0):")
    for name, n, dx, dy, dz in rows:
        if 1.2 < dy < 2.5 and dx < 2.0 and dz < 2.0 and n > 2000:
            print(f"  {name:>28} verts={n:>7} dx={dx:.2f} dy={dy:.2f} dz={dz:.2f}")
    print(f"\n{len(rows)} objects total")


if __name__ == "__main__":
    main()
