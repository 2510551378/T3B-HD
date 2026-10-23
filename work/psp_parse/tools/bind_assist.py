"""bind_assist.py -- build a .blend where every mesh run is its own object and all the
pack's textures are pre-loaded and packed as materials, so binding is drag-and-drop.

    blender -b --factory-startup -P tools/bind_assist.py -- --pack 0x444e5000 --out out/blend/bind.blend
"""
import os
import struct
import sys

import bpy

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from psp_pack import parse_pack, iter_pack_offsets, open_pack  # noqa: E402
from pack_export import find_runs, SCALE  # noqa: E402
import pack_tex  # noqa: E402

ROOT = r"C:\Users\25105\Documents\寄生前夜第四日"
ISO = os.path.join(ROOT, r"PSP\The_3rd_birthday_cn_full_v101.iso")
SEC = 2048
PKG_LBA, PKG_SIZE = 59600, 1344292864
TEXDIR = os.path.join(HERE, "..", "out", "textures")


def argval(flag, default=None):
    a = sys.argv
    return a[a.index(flag) + 1] if flag in a else default


def main():
    pack = int(argval("--pack", "0x444e5000"), 0)
    out = argval("--out", os.path.join(HERE, "..", "out", "blend", "bind.blend"))
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)

    with open(ISO, "rb") as f:
        offs = iter_pack_offsets(f)
        i = offs.index(pack)
        span = (offs[i + 1] if i + 1 < len(offs) else PKG_SIZE) - pack
        buf = open_pack(f, pack, span)
        p = parse_pack(buf, pack, span)
        big = max(p.sections, key=lambda s: s[0])
        blob = buf[big[1]:big[1] + big[0]]

    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene = bpy.context.scene

    # --- textures as packed images + one material each
    pngs = sorted(
        f for f in (os.listdir(TEXDIR) if os.path.isdir(TEXDIR) else [])
        if f.startswith(f"p{pack:08x}_tex") and f.endswith(".png"))
    mats = []
    for k, fn in enumerate(pngs):
        img = bpy.data.images.load(os.path.join(TEXDIR, fn), check_existing=True)
        img.pack()
        img.name = f"tex{k:02d}"
        name = f"mat_tex{k:02d}"
        mat = bpy.data.materials.new(name)
        mat.use_nodes = True
        nt = mat.node_tree
        for n in list(nt.nodes):
            nt.nodes.remove(n)
        outp = nt.nodes.new("ShaderNodeOutputMaterial")
        bsdf = nt.nodes.new("ShaderNodeBsdfPrincipled")
        tex = nt.nodes.new("ShaderNodeTexImage")
        tex.image = img
        tex.interpolation = "Closest"
        nt.links.new(tex.outputs["Color"], bsdf.inputs["Base Color"])
        nt.links.new(bsdf.outputs["BSDF"], outp.inputs["Surface"])
        bsdf.inputs["Roughness"].default_value = 0.9
        mats.append(mat)
        print(f"  texture {k:>2} {fn}")

    # --- one object per run
    runs = [r for r in find_runs(blob) if len(r) >= 3]
    total = 0
    auto = "--autobind" in sys.argv
    detail = None
    if auto and pngs:
        # detail maps are near-grayscale; pick one by name (default tex07, meanSat 0.002)
        want = argval("--detail", "tex07")
        detail = next((f for f in pngs if f"_{want}_" in f), pngs[0])
        didx = pngs.index(detail)
        print(f"  detail map: {detail} -> texture slot {didx}")

        dmat = bpy.data.materials.new("vc_x_detail")
        dmat.use_nodes = True
        nt = dmat.node_tree
        for n in list(nt.nodes):
            nt.nodes.remove(n)
        outp = nt.nodes.new("ShaderNodeOutputMaterial")
        bsdf = nt.nodes.new("ShaderNodeBsdfPrincipled")
        vc = nt.nodes.new("ShaderNodeVertexColor")
        vc.layer_name = "Col"
        tex = nt.nodes.new("ShaderNodeTexImage")
        tex.image = bpy.data.images.get(f"tex{didx:02d}")
        tex.interpolation = "Closest"
        mix = nt.nodes.new("ShaderNodeMix")
        mix.data_type = "RGBA"
        mix.blend_type = "MULTIPLY"
        mix.inputs[0].default_value = 1.0
        nt.links.new(vc.outputs["Color"], mix.inputs[6])
        nt.links.new(tex.outputs["Color"], mix.inputs[7])
        nt.links.new(mix.outputs[2], bsdf.inputs["Base Color"])
        nt.links.new(bsdf.outputs["BSDF"], outp.inputs["Surface"])
        bsdf.inputs["Roughness"].default_value = 0.9
        mats = [dmat]

    for ri, r in enumerate(runs):
        verts, uvs, cols, faces = [], [], [], []
        for o in r:
            x, y, z = struct.unpack_from("<3h", blob, o + 4)
            u, v = struct.unpack_from("<2f", blob, o + 12)
            verts.append((x * SCALE, y * SCALE, z * SCALE))
            uvs.append((u, v))
            cols.append((blob[o] / 255.0, blob[o + 1] / 255.0, blob[o + 2] / 255.0, 1.0))
        for k in range(0, len(r) - 2, 3):
            faces.append((k, k + 1, k + 2))
        me = bpy.data.meshes.new(f"run{ri:02d}")
        me.from_pydata(verts, [], faces)
        me.validate(verbose=False)
        uv = me.uv_layers.new(name="UVMap")
        for poly in me.polygons:
            for li in poly.loop_indices:
                uv.data[li].uv = uvs[me.loops[li].vertex_index]
        try:
            ca = me.color_attributes.new(name="Col", type="BYTE_COLOR", domain="CORNER")
        except Exception:
            ca = me.color_attributes.new(name="Col", type="FLOAT_COLOR", domain="CORNER")
        for poly in me.polygons:
            for li in poly.loop_indices:
                ca.data[li].color = cols[me.loops[li].vertex_index]
        for poly in me.polygons:
            poly.use_smooth = False
        for m in mats:
            me.materials.append(m)
        ob = bpy.data.objects.new(f"run{ri:02d}_{len(verts)}v", me)
        scene.collection.objects.link(ob)
        total += len(verts)
    print(f"pack 0x{pack:08x}: {len(runs)} objects, {total} verts, {len(mats)} materials")

    world = bpy.data.worlds.new("W")
    world.use_nodes = True
    bg = world.node_tree.nodes.get("Background")
    if bg:
        bg.inputs[0].default_value = (0.06, 0.065, 0.08, 1)
        bg.inputs[1].default_value = 1.5
    scene.world = world

    sun_d = bpy.data.lights.new("Sun", type="SUN")
    sun_d.energy = 4.0
    sun = bpy.data.objects.new("Sun", sun_d)
    sun.rotation_euler = (0.9, 0.2, 0.6)
    scene.collection.objects.link(sun)

    cam_d = bpy.data.cameras.new("Cam")
    cam_d.lens = 22
    cam = bpy.data.objects.new("Cam", cam_d)
    scene.collection.objects.link(cam)
    scene.camera = cam
    cam.location = (0, -2.6, 1.6)
    cam.rotation_euler = (1.2, 0, 0)
    cam_d.clip_start = 0.01

    view_layer = bpy.context.view_layer
    for ob in scene.objects:
        ob.select_set(False)
    bpy.ops.wm.save_as_mainfile(filepath=os.path.abspath(out))
    print("saved", out)


if __name__ == "__main__":
    main()
