"""Step 31: render a single mesh run as ASCII (front + side) to identify what it is."""
import os
import struct
import sys

ROOT = r"C:\Users\25105\Documents\寄生前夜第四日"
ISO = os.path.join(ROOT, r"PSP\The_3rd_birthday_cn_full_v101.iso")
SEC = 2048
PKG_LBA, PKG_SIZE = 59600, 1344292864
sys.path.insert(0, os.path.dirname(__file__))
from psp_pack import parse_pack, iter_pack_offsets, open_pack  # noqa: E402
from pack_export import find_runs, SCALE  # noqa: E402


def ascii_view(pts, W=56, H=26, axis=(0, 1)):
    xs = [p[axis[0]] for p in pts]
    ys = [p[axis[1]] for p in pts]
    x0, x1 = min(xs), max(xs)
    y0, y1 = min(ys), max(ys)
    sx = (x1 - x0) or 1
    sy = (y1 - y0) or 1
    g = [[0] * W for _ in range(H)]
    for p in pts:
        cx = int((p[axis[0]] - x0) / sx * (W - 1))
        cy = int((p[axis[1]] - y0) / sy * (H - 1))
        g[H - 1 - cy][cx] += 1
    mx = max(max(r) for r in g) or 1
    for r in g:
        print("  " + "".join("#" if c > mx * 0.45 else ("+" if c > mx * 0.12 else ("." if c else " ")) for c in r))


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    pack = int(sys.argv[1], 0)
    run_idx = int(sys.argv[2])
    with open(ISO, "rb") as f:
        offs = iter_pack_offsets(f)
        i = offs.index(pack)
        span = (offs[i + 1] if i + 1 < len(offs) else PKG_SIZE) - pack
        buf = open_pack(f, pack, span)
        p = parse_pack(buf, pack, span)
        big = max(p.sections, key=lambda s: s[0])
        blob = buf[big[1]:big[1] + big[0]]
    runs = [r for r in find_runs(blob) if len(r) >= 30]
    r = runs[run_idx]
    pts = []
    for off in r:
        x, y, z = struct.unpack_from("<3h", blob, off + 4)
        pts.append((x * SCALE, y * SCALE, z * SCALE))
    xs = [q[0] for q in pts]
    ys = [q[1] for q in pts]
    zs = [q[2] for q in pts]
    print(f"pack 0x{pack:08x} run {run_idx}: {len(pts)} verts, "
          f"bbox {max(xs)-min(xs):.2f} x {max(ys)-min(ys):.2f} x {max(zs)-min(zs):.2f} m")
    print("\nfront (X-Y):")
    ascii_view(pts, 56, 26, (0, 1))
    print("\nside (Z-Y):")
    ascii_view(pts, 56, 26, (2, 1))


if __name__ == "__main__":
    main()
