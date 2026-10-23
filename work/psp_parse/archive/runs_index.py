"""Step 32: index every mesh run (bbox, verts) and export character-sized candidates as OBJ."""
import csv
import os
import struct
import sys

ROOT = r"C:\Users\25105\Documents\寄生前夜第四日"
ISO = os.path.join(ROOT, r"PSP\The_3rd_birthday_cn_full_v101.iso")
SEC = 2048
PKG_LBA, PKG_SIZE = 59600, 1344292864
OUT = os.path.join(os.path.dirname(__file__), "runs")
sys.path.insert(0, os.path.dirname(__file__))
from psp_pack import parse_pack, iter_pack_offsets, open_pack  # noqa: E402
from pack_export import find_runs, SCALE  # noqa: E402


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    os.makedirs(OUT, exist_ok=True)
    rows = []
    with open(ISO, "rb") as f:
        offs = iter_pack_offsets(f)
        spans = {o: (offs[i + 1] if i + 1 < len(offs) else PKG_SIZE) - o for i, o in enumerate(offs)}
        for o in offs:
            buf = open_pack(f, o, spans[o])
            p = parse_pack(buf, o, spans[o])
            if not p.sections:
                continue
            big = max(p.sections, key=lambda s: s[0])
            blob = buf[big[1]:big[1] + big[0]]
            if struct.unpack_from("<I", blob, 4)[0] != 0x3002:
                continue
            runs = [r for r in find_runs(blob) if len(r) >= 30]
            for ri, r in enumerate(runs):
                pts = []
                for off in r:
                    x, y, z = struct.unpack_from("<3h", blob, off + 4)
                    pts.append((x * SCALE, y * SCALE, z * SCALE))
                xs = [q[0] for q in pts]
                ys = [q[1] for q in pts]
                zs = [q[2] for q in pts]
                dx, dy, dz = max(xs) - min(xs), max(ys) - min(ys), max(zs) - min(zs)
                rows.append({"pack": f"0x{o:08x}", "run": ri, "verts": len(r),
                             "tris": len(r) // 3 if len(r) % 3 == 0 else 0,
                             "dx": round(dx, 3), "dy": round(dy, 3), "dz": round(dz, 3)})
                if 1.2 < dy < 2.4 and dx < 1.2 and dz < 1.2 and len(r) >= 300:
                    fn = os.path.join(OUT, f"0x{o:08x}_r{ri:03d}_{len(r)}v.obj")
                    with open(fn, "w", encoding="utf-8") as fo:
                        for q in pts:
                            fo.write("v %.4f %.4f %.4f\n" % q)
                        if len(r) % 3 == 0:
                            for t in range(0, len(r), 3):
                                fo.write(f"f {t + 1} {t + 2} {t + 3}\n")
    with open(os.path.join(OUT, "runs_index.csv"), "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    print(f"{len(rows):,} runs indexed -> {os.path.join(OUT, 'runs_index.csv')}")
    cand = [r for r in rows if 1.2 < r["dy"] < 2.4 and r["dx"] < 1.2 and r["dz"] < 1.2 and r["verts"] >= 300]
    print(f"{len(cand)} character-sized candidates exported to {OUT}")
    for r in cand[:15]:
        print(f"  {r['pack']} run {r['run']:>3} {r['verts']:>5} verts  "
              f"{r['dx']:.2f} x {r['dy']:.2f} x {r['dz']:.2f} m")


if __name__ == "__main__":
    main()
