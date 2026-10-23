"""body_fields.py -- decode a stride-40 s16 record layout around a candidate vertex buffer."""
import struct
import sys

SCALE = 3.125 / 32768.0


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    blob = open(sys.argv[1], "rb").read()
    off = int(sys.argv[2], 0)
    n = int(sys.argv[3]) if len(sys.argv) > 3 else 8
    stride = int(sys.argv[4]) if len(sys.argv) > 4 else 40
    print(f"@0x{off:08x}  stride {stride}")
    for k in range(n):
        rec = blob[off + k * stride: off + (k + 1) * stride]
        s16 = struct.unpack_from("<%dh" % (stride // 2), rec, 0)
        u8 = list(rec)
        print(f"  [{k}] s16: " + " ".join(f"{v:>6}" for v in s16[:8]))
        print(f"      u8 : " + " ".join(f"{v:>3}" for v in u8[:12]) + " | "
              + " ".join(f"{v:>3}" for v in u8[12:24]))
    print()
    # walk the buffer with the assumed layout and report ranges per field
    pts = []
    for k in range(2000):
        p = off + k * stride
        if p + stride > len(blob):
            break
        x, y, z = struct.unpack_from("<3h", blob, p)
        pts.append((x * SCALE, y * SCALE, z * SCALE))
    if pts:
        xs = [p[0] for p in pts]
        ys = [p[1] for p in pts]
        zs = [p[2] for p in pts]
        print(f"2000 verts: x {min(xs):.2f}..{max(xs):.2f}  "
              f"y {min(ys):.2f}..{max(ys):.2f}  z {min(zs):.2f}..{max(zs):.2f}")


if __name__ == "__main__":
    main()
