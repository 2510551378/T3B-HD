"""gpu_blend.py -- build a .blend from a frame dump using the verified GPU vertex layout.

    20 bytes: uv f32 x2 @0 | colour RGBA @8 | position s16 x3 @12 | pad CC CC @18

Run with:  blender -b --factory-startup -P tools/gpu_blend.py -- --src <dump.bin> --out <x.blend>
"""
import bpy
import bmesh  # noqa: F401
import math
import os
import struct
import sys

SC = 3.125 / 32768.0


def find_runs(blob, min_len=3):
    marks = [o for o in range(0, len(blob) - 20, 2)
             if blob[o + 18:o + 20] == b"\xcc\xcc"]
    if not marks:
        return []
    runs = []
    cur = [marks[0]]
    for o in marks[1:]:
        if o - cur[-1] == 20:
            cur.append(o)
        else:
            runs.append(cur)
            cur = [o]
    runs.append(cur)
    return [r for r in runs if len(r) >= min_len]


def clear():
    bpy.ops.wm.read_factory_settings(use_empty=True)


def main():
    argv = sys.argv[sys.argv.index("--") + 1:]
    src = out = None
    for i, a in enumerate(argv):
        if a == "--src":
            src = argv[i + 1]
        elif a == "--out":
            out = argv[i + 1]
    blob = open(src, "rb").read()
    runs = find_runs(blob)
    runs.sort(key=len, reverse=True)
    print(f"{src}: {len(runs)} runs, {sum(len(r) for r in runs)} verts")

    clear()
    mat = bpy.data.materials.new("vcol")
    mat.use_nodes = True
    nt = mat.node_tree
    bsdf = nt.nodes["Principled BSDF"]
    vc = nt.nodes.new("ShaderNodeVertexColor")
    vc.layer_name = "Col"
    nt.links.new(vc.outputs["Color"], bsdf.inputs["Base Color"])
    bsdf.inputs["Roughness"].default_value = 0.85

    cols = 12
    for idx, r in enumerate(runs):
        n = len(r)
        verts = []
        colors = []
        for o in r:
            x, y, z = struct.unpack_from("<3h", blob, o + 12)
            verts.append((x * SC, z * SC, y * SC))
            rr, gg, bb = blob[o + 8], blob[o + 9], blob[o + 10]
            colors.append((rr / 255.0, gg / 255.0, bb / 255.0, 1.0))
        faces = [(k, k + 1, k + 2) for k in range(0, n - 2, 3)]
        me = bpy.data.meshes.new(f"run{idx}")
        me.from_pydata(verts, [], faces)
        me.update()
        col = me.color_attributes.new(name="Col", type="FLOAT_COLOR", domain="POINT")
        for k, c in enumerate(colors[: len(me.vertices)]):
            col.data[k].color = c
        ob = bpy.data.objects.new(f"run{idx:03d}_{n}v", me)
        ob.data.materials.append(mat)
        ob.location = ((idx % cols) * 2.2, 0.0, -(idx // cols) * 2.2)
        bpy.context.collection.objects.link(ob)

    cam_data = bpy.data.cameras.new("cam")
    cam = bpy.data.objects.new("cam", cam_data)
    cam.location = ((cols - 1) * 1.1, -22.0, -8.0)
    cam.rotation_euler = (math.radians(72), 0, 0)
    bpy.context.collection.objects.link(cam)
    bpy.context.scene.camera = cam
    sun_data = bpy.data.lights.new("sun", type="SUN")
    sun_data.energy = 3.0
    sun = bpy.data.objects.new("sun", sun_data)
    sun.rotation_euler = (math.radians(50), math.radians(15), 0)
    bpy.context.collection.objects.link(sun)

    bpy.ops.wm.save_as_mainfile(filepath=os.path.abspath(out))
    print("saved", out)


main()
