"""ram_mesh.py -- pull every 20-byte vertex run out of a RAM blob and export candidates.

The static format is the same one the pack containers use: 20 bytes per vertex with the
0xCCCC pad at +0x0A.  In RAM the game holds whole rooms plus, if a character is on screen,
that character's mesh -- so we export every run and sort them by "looks like a person".
"""
import os
import struct
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "tools"))
from pack_export import find_runs, SCALE  # noqa: E402


def run_geo(blob, r):
    V, C, F = [], [], []
    for o in r:
        x, y, z = struct.unpack_from("<3h", blob, o + 4)
        V.append((x * SCALE, y * SCALE, z * SCALE))
        C.append((blob[o], blob[o + 1], blob[o + 2]))
    for k in range(0, len(r) - 2, 3):
        F.append((k, k + 1, k + 2))
    return V, C, F


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    src = sys.argv[1]
    outdir = sys.argv[2] if len(sys.argv) > 2 else "out/dump"
    os.makedirs(outdir, exist_ok=True)
    blob = open(src, "rb").read()
    runs = [r for r in find_runs(blob) if len(r) >= 3]
    print(f"{src}: {len(blob):,} bytes, {len(runs)} runs, "
          f"{sum(len(r) for r in runs):,} vertices")

    info = []
    for r in runs:
        V, C, F = run_geo(blob, r)
        xs = [p[0] for p in V]
        ys = [p[1] for p in V]
        zs = [p[2] for p in V]
        dx, dy, dz = max(xs) - min(xs), max(ys) - min(ys), max(zs) - min(zs)
        info.append((len(r), r[0], dx, dy, dz, min(ys), max(ys)))

    def human(t):
        n, off, dx, dy, dz, y0, y1 = t
        if not (1.2 <= dy <= 2.1):
            return False
        if not (0.15 <= dx <= 1.3 and 0.15 <= dz <= 1.3):
            return False
        if n < 300:
            return False
        return dy > 1.6 * max(dx, dz)

    hum = sorted([t for t in info if human(t)], key=lambda t: -t[0])
    print(f"\nperson-shaped runs (1.2-2.1 m tall, taller than wide): {len(hum)}")
    for n, off, dx, dy, dz, y0, y1 in hum[:12]:
        print(f"  @0x{off:08x} {n:>5}v  {dx:.2f} x {dy:.2f} x {dz:.2f} m  y {y0:.2f}..{y1:.2f}")

    big = sorted(info, key=lambda t: -t[0])[:6]
    print("\nlargest runs:")
    for n, off, dx, dy, dz, y0, y1 in big:
        print(f"  @0x{off:08x} {n:>5}v  {dx:.2f} x {dy:.2f} x {dz:.2f} m")

    # export: every person-shaped run separately, plus everything combined
    picked = hum[:40]
    made = 0
    for i, (n, off, dx, dy, dz, y0, y1) in enumerate(picked):
        r = next(r for r in runs if r[0] == off)
        V, C, F = run_geo(blob, r)
        path = os.path.join(outdir, f"ram_{i:02d}_0x{off:08x}_{n}v.obj")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(f"# run @0x{off:x} {n} verts {dx:.2f}x{dy:.2f}x{dz:.2f} m\n")
            for p in V:
                fh.write("v %.4f %.4f %.4f\n" % p)
            for a, b, c in F:
                fh.write(f"f {a+1} {b+1} {c+1}\n")
        made += 1
    print(f"\nwrote {made} candidate OBJs -> {outdir}")


if __name__ == "__main__":
    main()
