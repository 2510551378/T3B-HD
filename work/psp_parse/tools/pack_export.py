"""pack_export.py -- geometry exporter for The 3rd Birthday (ULJM-05798) 'pack' containers.

Format (type-8 containers, verified on 91/91 of them)
-----------------------------------------------------
pack header:
    +0x00  char[4] "pack"
    +0x04  u32     type / version
    +0x08  N x (u32 size, u32 offset)          N = (first offset - 8) / 8
    sections tile forward; (0,0) = empty slot

the biggest section is a vertex pool of 20-byte records:

    +0x00  4 x u8   RGBA (alpha 0xFF) -- baked shading / vertex colour
    +0x04  3 x s16  position, fixed point:  metres = raw / 32768 * 3.125
    +0x0A  u16      0xCCCC, constant pad -- the record signature
    +0x0C  f32      U
    +0x10  f32      V

records come in runs (37 in pack 0x444e5000, up to 380 elsewhere); every run
length that is a multiple of 3 is written as a triangle list, i.e. vertices are
already split per triangle (no index buffer), which is what the 3*V == 3*T
bookkeeping shows.

usage:
    python pack_export.py <pack_offset> <out_dir> [--points] [--uv]
    python pack_export.py all <out_dir> [--points] [--uv]
"""
import csv
import os
import struct
import sys

ROOT = r"C:\Users\25105\Documents\寄生前夜第四日"
ISO = os.path.join(ROOT, r"PSP\The_3rd_birthday_cn_full_v101.iso")
SEC = 2048
PKG_LBA, PKG_SIZE = 59600, 1344292864
REC = 20
SCALE = 3.125 / 32768.0


def find_runs(blob, start=0, end=None, rec=REC):
    end = len(blob) if end is None else end
    hits = [o for o in range(start, end - rec, 2) if blob[o + 10:o + 12] == b"\xcc\xcc"]
    if not hits:
        return []
    runs = []
    cur = [hits[0]]
    for o in hits[1:]:
        if o - cur[-1] == rec:
            cur.append(o)
        else:
            runs.append(cur)
            cur = [o]
    runs.append(cur)
    return runs


def write_obj(blob, runs, path, tag, scale=SCALE, soup=True, with_uv=False):
    nv = nt = 0
    with open(path, "w", encoding="utf-8") as o:
        o.write(f"# {tag}  scale={scale:.8g}\n")
        base = 1
        for ri, r in enumerate(runs):
            o.write(f"o m{ri:03d}_n{len(r)}\n")
            for off in r:
                x, y, z = struct.unpack_from("<3h", blob, off + 4)
                o.write("v %.4f %.4f %.4f\n" % (x * scale, y * scale, z * scale))
            if with_uv:
                for off in r:
                    u, v = struct.unpack_from("<2f", blob, off + 12)
                    o.write("vt %.4f %.4f\n" % (u, v))
            if soup and len(r) % 3 == 0:
                for t in range(0, len(r), 3):
                    if with_uv:
                        a, b, c = base + t, base + t + 1, base + t + 2
                        o.write(f"f {a}/{a} {b}/{b} {c}/{c}\n")
                    else:
                        o.write(f"f {base + t} {base + t + 1} {base + t + 2}\n")
                    nt += 1
            base += len(r)
            nv += len(r)
    return nv, nt


def export_one(f, off, outdir, soup=True, with_uv=False, offs=None):
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from psp_pack import parse_pack, open_pack, iter_pack_offsets
    if offs is None:
        offs = iter_pack_offsets(f)
    if off not in offs:
        raise SystemExit(f"{off:#x} is not a pack")
    i = offs.index(off)
    span = (offs[i + 1] if i + 1 < len(offs) else PKG_SIZE) - off
    buf = open_pack(f, off, span)
    p = parse_pack(buf, off, span)
    if not p.sections:
        return None
    big = max(p.sections, key=lambda s: s[0])
    blob = buf[big[1]:big[1] + big[0]]
    runs = [r for r in find_runs(blob) if len(r) >= 3]
    if not runs:
        return None
    runs.sort(key=lambda r: r[0])
    path = os.path.join(outdir, f"pack_0x{off:08x}.obj")
    nv, nt = write_obj(blob, runs, path, f"pack 0x{off:08x} type={p.type}", SCALE, soup, with_uv)
    return {"pack": f"0x{off:08x}", "type": p.type, "section": f"0x{big[1]:x}",
            "sec_size": big[0], "runs": len(runs), "verts": nv, "tris": nt,
            "obj": os.path.basename(path)}


def main(argv):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if len(argv) < 3:
        print(__doc__)
        return
    target, outdir = argv[1], argv[2]
    soup = "--points" not in argv
    with_uv = "--uv" in argv
    os.makedirs(outdir, exist_ok=True)
    rows = []
    with open(ISO, "rb") as f:
        if target == "all":
            from psp_pack import iter_pack_offsets
            offs = iter_pack_offsets(f)
            for off in offs:
                r = export_one(f, off, outdir, soup, with_uv, offs)
                if r:
                    rows.append(r)
                    print(f"  {r['pack']} type={r['type']:>2} runs={r['runs']:>3} "
                          f"verts={r['verts']:>7} tris={r['tris']:>7}", flush=True)
        else:
            r = export_one(f, int(target, 0), outdir, soup, with_uv)
            if r:
                rows.append(r)
                print(f"  {r['pack']} type={r['type']:>2} runs={r['runs']:>3} "
                      f"verts={r['verts']:>7} tris={r['tris']:>7}")
    if rows:
        with open(os.path.join(outdir, "index.csv"), "w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=list(rows[0]))
            w.writeheader()
            w.writerows(rows)
        print(f"\n{len(rows)} packs, {sum(r['verts'] for r in rows):,} verts, "
              f"{sum(r['tris'] for r in rows):,} tris -> {outdir}")


if __name__ == "__main__":
    main(sys.argv)
