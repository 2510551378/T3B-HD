"""Is the s16 triple a position or a direction?  Test radial + covariance structure per run."""
import math
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
    runs.sort(key=len, reverse=True)

    print(f"{'run':>4} {'n':>5} {'|v| mean':>9} {'|v| sd':>7} {'|v|/16384':>10} "
          f"{'eig1':>7} {'eig2':>7} {'eig3':>7}  shape")
    for ri, r in enumerate(runs[:8]):
        P = [struct.unpack_from("<3h", geo, o + 4) for o in r]
        n = len(P)
        mean = [sum(p[i] for p in P) / n for i in range(3)]
        rad = [math.dist(p, mean) for p in P]
        mr = sum(rad) / n
        sr = math.sqrt(sum((x - mr) ** 2 for x in rad) / n)
        # covariance eigenvalues (power iteration on 3x3)
        C = [[sum((p[i] - mean[i]) * (p[j] - mean[j]) for p in P) / n for j in range(3)] for i in range(3)]
        tr = C[0][0] + C[1][1] + C[2][2]
        det = (C[0][0] * (C[1][1] * C[2][2] - C[1][2] * C[2][1])
               - C[0][1] * (C[1][0] * C[2][2] - C[1][2] * C[2][0])
               + C[0][2] * (C[1][0] * C[2][1] - C[1][1] * C[2][0]))
        # rough: use sqrt of diagonal as proxy
        e = sorted((math.sqrt(C[0][0]), math.sqrt(C[1][1]), math.sqrt(C[2][2])))
        shape = "sphere?" if e[2] / max(e[0], 1e-9) < 1.6 else ("flat" if e[0] / max(e[2], 1e-9) < 0.4 else "box")
        print(f"{ri:>4} {n:>5} {mr:>9.0f} {sr:>7.0f} {mr/16384:>10.3f} "
              f"{e[0]:>7.0f} {e[1]:>7.0f} {e[2]:>7.0f}  {shape}")

    # global radial histogram of one run
    r = runs[0]
    P = [struct.unpack_from("<3h", geo, o + 4) for o in r]
    n = len(P)
    mean = [sum(p[i] for p in P) / n for i in range(3)]
    rad = sorted(math.dist(p, mean) for p in P)
    print("\nbiggest run radial percentiles (units):",
          [round(rad[int(n * q)], 0) for q in (0.05, 0.25, 0.5, 0.75, 0.95)])
    print("radial/32768:", [round(rad[int(n * q)] / 32768, 3) for q in (0.05, 0.5, 0.95)])


if __name__ == "__main__":
    main()
