"""build_blend.py -- bake pack geometry into a .blend you can just open in Blender.

Runs inside Blender's Python:
    blender -b --factory-startup -P tools/build_blend.py -- --out out/blend/x.blend [--packs 0x...,0x...] [--all]

Each pack becomes one mesh object placed in a grid, with
  * baked vertex colours (the RGBA stored in every 20-byte vertex record)
  * UV coordinates
  * flat shading + a material that shows the vertex colours
  * a sun light, ambient world and a camera framing the grid
"""
import math
import os
import struct
import sys

import bpy

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from psp_pack import parse_pack, iter_pack_offsets, open_pack  # noqa: E402
from pack_export import find_runs, SCALE  # noqa: E402

ROOT = r"C:\Users\25105\Documents\寄生前夜第四日"
ISO = os.path.join(ROOT, r"PSP\The_3rd_birthday_cn_full_v101.iso")
SEC = 2048
PKG_LBA, PKG_SIZE = 59600, 1344292864


def args():
    argv = sys.argv
    argv = argv[argv.index("--") + 1:] if "--" in argv else []
    out = os.path.join(HERE, "..", "out", "blend", "packs.blend")
    packs = []
    do_all = "--all" in argv
    inside = "--inside" in argv
    for i, a in enumerate(argv):
        if a == "--out":
            out = argv[i + 1]
        elif a == "--packs":
            packs = [int(x, 0) for x in argv[i + 1].split(",") if x.strip()]
        elif a == "--limit":
            packs = packs[:int(argv[i + 1])]
    return out, packs, do_all, inside


def classify(verts, faces):
    """floor / ceiling / wall / prop from the area-weighted normal and the bbox."""
    import math as _m
    xs = [p[0] for p in verts]
    ys = [p[1] for p in verts]
    zs = [p[2] for p in verts]
    dx, dy, dz = max(xs) - min(xs), max(ys) - min(ys), max(zs) - min(zs)
    acc = [0.0, 0.0, 0.0]
    tot = 0.0
    for a, b, c in faces:
        A, B, C = verts[a], verts[b], verts[c]
        u = (B[0] - A[0], B[1] - A[1], B[2] - A[2])
        v = (C[0] - A[0], C[1] - A[1], C[2] - A[2])
        n = (u[1] * v[2] - u[2] * v[1], u[2] * v[0] - u[0] * v[2], u[0] * v[1] - u[1] * v[0])
        ln = _m.sqrt(n[0] ** 2 + n[1] ** 2 + n[2] ** 2)
        if ln <= 0:
            continue
        for i in range(3):
            acc[i] += n[i]
        tot += ln
    if tot <= 0:
        return "prop"
    ax = max(range(3), key=lambda i: abs(acc[i]))
    frac = abs(acc[ax]) / tot
    horiz = max(dx, dz) or 1e-9
    if frac > 0.45 and ax == 1:
        return "floor" if dy < horiz * 0.25 else "slab"
    if frac > 0.35 and ax in (0, 2):
        return "wall"
    if dy > horiz * 0.9:
        return "prop"
    return "prop"


def load_pack(f, off, offs, split=False):
    i = offs.index(off)
    span = (offs[i + 1] if i + 1 < len(offs) else PKG_SIZE) - off
    buf = open_pack(f, off, span)
    p = parse_pack(buf, off, span)
    if not p.sections:
        return None
    big = max(p.sections, key=lambda s: s[0])
    blob = buf[big[1]:big[1] + big[0]]
    if struct.unpack_from("<I", blob, 4)[0] != 0x3002:
        return None
    runs = [r for r in find_runs(blob) if len(r) >= 3 and len(r) % 3 == 0]
    if not runs:
        return None
    groups = {}
    for r in runs:
        verts, cols, uvs, faces = [], [], [], []
        for o in r:
            x, y, z = struct.unpack_from("<3h", blob, o + 4)
            u, v = struct.unpack_from("<2f", blob, o + 12)
            verts.append((x * SCALE, y * SCALE, z * SCALE))
            cols.append((blob[o] / 255.0, blob[o + 1] / 255.0, blob[o + 2] / 255.0, 1.0))
            uvs.append((u, v))
        for k in range(0, len(r), 3):
            faces.append((k, k + 1, k + 2))
        cls = classify(verts, faces) if split else "all"
        g = groups.setdefault(cls, ([], [], [], []))
        base = len(g[0])
        g[0].extend(verts)
        g[1].extend(cols)
        g[2].extend(uvs)
        g[3].extend([(a + base, b + base, c + base) for a, b, c in faces])
    return groups, p.type


def make_object(name, verts, cols, uvs, faces, vcol_name="Col", uv_name="UVMap"):
    me = bpy.data.meshes.new(name)
    me.from_pydata(verts, [], faces)
    me.validate(verbose=False)
    me.update()

    uv = me.uv_layers.new(name=uv_name)
    for poly in me.polygons:
        for li in poly.loop_indices:
            vi = me.loops[li].vertex_index
            uv.data[li].uv = uvs[vi]

    try:
        ca = me.color_attributes.new(name=vcol_name, type="BYTE_COLOR", domain="CORNER")
    except Exception:
        ca = me.color_attributes.new(name=vcol_name, type="FLOAT_COLOR", domain="CORNER")
    for poly in me.polygons:
        for li in poly.loop_indices:
            vi = me.loops[li].vertex_index
            ca.data[li].color = cols[vi]

    for poly in me.polygons:
        poly.use_smooth = False

    mat = bpy.data.materials.new(name + "_mat")
    mat.use_nodes = True
    nt = mat.node_tree
    for n in list(nt.nodes):
        nt.nodes.remove(n)
    outn = nt.nodes.new("ShaderNodeOutputMaterial")
    bsdf = nt.nodes.new("ShaderNodeBsdfPrincipled")
    attr = nt.nodes.new("ShaderNodeVertexColor")
    attr.layer_name = vcol_name
    nt.links.new(attr.outputs["Color"], bsdf.inputs["Base Color"])
    bsdf.inputs["Roughness"].default_value = 0.85
    nt.links.new(bsdf.outputs["BSDF"], outn.inputs["Surface"])
    me.materials.append(mat)

    ob = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(ob)
    return ob


def main():
    out, packs, do_all, inside = args()
    split = "--split" in sys.argv
    os.makedirs(os.path.dirname(out), exist_ok=True)

    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene = bpy.context.scene
    scene.render.engine = "BLENDER_EEVEE_NEXT" if "BLENDER_EEVEE_NEXT" in [
        e.bl_rna.identifier for e in [] ] else scene.render.engine

    built = []
    with open(ISO, "rb") as f:
        offs = iter_pack_offsets(f)
        sel = offs if do_all else (packs or offs[:12])
        for off in sel:
            name = f"pack_0x{off:08x}"
            data = load_pack(f, off, offs, split=split)
            if not data:
                continue
            groups, ptype = data
            origin = None
            for cls, (verts, cols, uvs, faces) in sorted(groups.items()):
                if not verts:
                    continue
                oname = name if len(groups) == 1 else f"{name}_{cls}"
                ob = make_object(oname, verts, cols, uvs, faces)
                built.append((ob, verts))
                if cls in ("wall", "floor", "slab"):
                    print(f"  {oname} type={ptype} verts={len(verts)} tris={len(faces)}")
            total_v = sum(len(g[0]) for g in groups.values())
            print(f"  {name} type={ptype} groups={list(groups)} verts={total_v}")

    if not built:
        print("nothing built")
        return
    # grid layout
    ext = 0.0
    for _, v in built:
        xs = [p[0] for p in v]
        ys = [p[1] for p in v]
        ext = max(ext, max(xs) - min(xs), max(ys) - min(ys), max(p[2] for p in v) - min(p[2] for p in v))
    ext = max(ext, 1.0)
    cols = max(1, int(math.ceil(math.sqrt(len(built)))))
    step = ext * 1.35
    for k, (ob, v) in enumerate(built):
        cx = (k % cols) - (cols - 1) / 2
        cy = (k // cols) - (len(built) / cols - 0.5)
        xs = [p[0] for p in v]
        ys = [p[1] for p in v]
        zs = [p[2] for p in v]
        ob.location = (cx * step - (min(xs) + max(xs)) / 2,
                       cy * step - (min(ys) + max(ys)) / 2,
                       -(min(zs) + max(zs)) / 2)

    world = bpy.data.worlds.new("W")
    world.use_nodes = True
    bg = world.node_tree.nodes.get("Background")
    if bg:
        bg.inputs[0].default_value = (0.05, 0.055, 0.07, 1)
        bg.inputs[1].default_value = 1.2
    scene.world = world

    sun_d = bpy.data.lights.new("Sun", type="SUN")
    sun_d.energy = 3.0
    sun = bpy.data.objects.new("Sun", sun_d)
    sun.rotation_euler = (math.radians(55), math.radians(12), math.radians(35))
    scene.collection.objects.link(sun)

    cam_d = bpy.data.cameras.new("Cam")
    cam_d.lens = 50
    cam = bpy.data.objects.new("Cam", cam_d)
    scene.collection.objects.link(cam)
    scene.camera = cam

    ncol = cols
    nrow = max(1, int(math.ceil(len(built) / cols)))
    grid_w = (ncol - 1) * step + ext
    grid_h = (nrow - 1) * step + ext
    radius = 0.5 * math.sqrt(grid_w ** 2 + grid_h ** 2 + ext ** 2)

    target = bpy.data.objects.new("CamTarget", None)
    scene.collection.objects.link(target)
    target.location = (0.0, 0.0, 0.0)

    if inside and len(built) == 1:
        # first-person view from inside the room
        ob, v = built[0]
        L = ob.location[:]          # the grid pass moved the object; follow it
        xs = [p[0] + L[0] for p in v]
        ys = [p[1] + L[1] for p in v]
        zs = [p[2] + L[2] for p in v]
        cx = (min(xs) + max(xs)) / 2
        cy = (min(ys) + max(ys)) / 2
        cz = (min(zs) + max(zs)) / 2
        h = max(zs) - min(zs)
        cam_d.lens = 16
        cam.location = (cx - (max(xs) - min(xs)) * 0.12, cy - h * 0.18, cz + h * 0.55)
        scene.view_settings.look = "None"
        cam["inside"] = True
        # aim across the room
        target.location = (cx + (max(xs) - min(xs)) * 0.25, cy + h * 0.2, cz + h * 0.25)
        ob.select_set(False)
        con = cam.constraints.new(type="TRACK_TO")
        con.target = target
        con.track_axis = "TRACK_NEGATIVE_Z"
        con.up_axis = "UP_Y"
        d = radius * 1.9
        cam_d.clip_start = 0.01
        cam_d.clip_end = 200
        world = bpy.data.worlds.new("W")
        world.use_nodes = True
        bg = world.node_tree.nodes.get("Background")
        if bg:
            bg.inputs[0].default_value = (0.08, 0.09, 0.11, 1)
            bg.inputs[1].default_value = 1.5
        scene.world = world
        sun_d = bpy.data.lights.new("Sun", type="SUN")
        sun_d.energy = 4.0
        sun = bpy.data.objects.new("Sun", sun_d)
        sun.rotation_euler = (math.radians(50), math.radians(10), math.radians(30))
        scene.collection.objects.link(sun)
        bpy.ops.wm.save_as_mainfile(filepath=os.path.abspath(out))
        print(f"saved {out} with {len(built)} objects (inside camera)")
        return

    d = radius * 1.9
    cam.location = (d * 0.62, -d * 0.72, d * 0.38)
    con = cam.constraints.new(type="TRACK_TO")
    con.target = target
    con.track_axis = "TRACK_NEGATIVE_Z"
    con.up_axis = "UP_Y"

    bpy.ops.wm.save_as_mainfile(filepath=os.path.abspath(out))
    print(f"saved {out} with {len(built)} objects")


if __name__ == "__main__":
    main()
