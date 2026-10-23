"""pack_bundle.py -- one pack -> one folder: mesh OBJ (with UVs) + its textures + README.

usage:
    python pack_bundle.py <pack_offset> [...] --out <dir>
    python pack_bundle.py 0x444e5000 0x49fb1000 --out work/psp_parse/bundle
"""
import os
import shutil
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import pack_export  # noqa: E402
import pack_tex  # noqa: E402

ROOT = r"C:\Users\25105\Documents\寄生前夜第四日"
ISO = os.path.join(ROOT, r"PSP\The_3rd_birthday_cn_full_v101.iso")
SEC = 2048
PKG_LBA, PKG_SIZE = 59600, 1344292864


def bundle(f, off, spans, outroot):
    from psp_pack import parse_pack, open_pack
    buf = open_pack(f, off, spans[off])
    p = parse_pack(buf, off, spans[off])
    if not p.sections:
        return None
    big = max(p.sections, key=lambda s: s[0])
    blob = buf[big[1]:big[1] + big[0]]
    if struct.unpack_from("<I", blob, 4)[0] != 0x3002:
        return None
    d = os.path.join(outroot, f"pack_0x{off:08x}")
    os.makedirs(d, exist_ok=True)
    td = os.path.join(d, "tex")
    os.makedirs(td, exist_ok=True)
    ntex = pack_tex.extract_pack(blob, td, "t")
    r = pack_export.export_one(f, off, d, soup=True, with_uv=True, offs=[o for o in spans])
    if r:
        os.replace(os.path.join(d, f"pack_0x{off:08x}.obj"), os.path.join(d, "mesh.obj"))
    with open(os.path.join(d, "README.txt"), "w", encoding="utf-8") as o:
        o.write(f"pack 0x{off:08x}  type={p.type}\n")
        o.write(f"vertices {r['verts'] if r else 0}  triangles {r['tris'] if r else 0}  "
                f"runs {r['runs'] if r else 0}\n")
        o.write(f"textures {ntex}\n\n")
        o.write("mesh.obj   positions + UVs, triangle list (3 consecutive vertices per face)\n")
        o.write("tex/*.png  4bpp palette textures of this container\n\n")
        o.write("NOTE: the mesh<->texture binding is not recovered yet; assign by eye.\n")
    print(f"  bundle 0x{off:08x}: {r['verts'] if r else 0} verts, {ntex} textures -> {d}")
    return d


def main(argv):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    args = [a for a in argv[1:]]
    out = None
    if "--out" in args:
        i = args.index("--out")
        out = args[i + 1]
        del args[i:i + 2]
    offs_wanted = [int(a, 0) for a in args]
    out = out or os.path.join(HERE, "bundle")
    os.makedirs(out, exist_ok=True)
    with open(ISO, "rb") as f:
        from psp_pack import iter_pack_offsets
        allofs = iter_pack_offsets(f)
        spans = {o: (allofs[i + 1] if i + 1 < len(allofs) else PKG_SIZE) - o
                 for i, o in enumerate(allofs)}
        for off in offs_wanted:
            bundle(f, off, spans, out)


if __name__ == "__main__":
    main(sys.argv)
