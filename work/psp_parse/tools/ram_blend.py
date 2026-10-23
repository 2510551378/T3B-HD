"""ram_blend.py -- build a .blend straight out of a RAM blob (Blender-side script).

    blender -b --factory-startup -P tools/ram_blend.py -- --ram raw/ram.bin --out out/blend/ram.blend

The static-mesh records (20 bytes, 0xCCCC at +0x0A) are the same ones the pack containers
use, so the room the savestate was taken in comes back with its baked vertex colours.
"""
import math
import os
import struct
import sys

import bpy

SCALE = 3.125 / 32768.0


def find_runs(blob):
    """20-byte vertex records; the page base can be either byte parity in a frame dump."""
    best = []
    for parity in (0, 1):
        marks = [o for o in range(parity, len(blob) - 20, 2)
                 if blob[o + 10:o + 12] == b"\xcc\xcc"]
        if len(marks) <= len(best):
            continue
        runs = []
        cur = [marks[0]]
        for o in marks[1:]:
            if o - cur[-1] == 20:
                cur.append(o)
            else:
                runs.append(cur)
                cur = [o]
        runs.append(cur)
        best = [r for r in runs if len(r) >= 3]
    return best


def arg(flag, default=None):
    a = sys.argv
    return a[a.index(flag) + 1] if flag in a else default


def main():
    ram = arg("--ram")
    out = arg("--out", "ram.blend")
    blob = open(ram, "rb").read()
    runs = [r for r in find_runs(blob) if len(r) >= 3]
    print(f"{ram}: {len(blob):,} bytes, {len(runs)} runs, "
          f"{sum(len(r) for r in runs):,} verts")

    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene = bpy.context.scene

    mat = bpy.data.materials.new("vc")
    mat.use_nodes = True
    nt = mat.node_tree
    for n in list(nt.nodes):
        nt.nodes.remove(n)
    outn = nt.nodes.new("ShaderNodeOutputMaterial")
    bsdf = nt.nodes.new("ShaderNodeBsdfPrincipled")
    vc = nt.nodes.new("ShaderNodeVertexColor")
    vc.layer_name = "Col"
    nt.links.new(vc.outputs["Color"], bsdf.inputs["Base Color"])
    nt.links.new(bsdf.outputs["BSDF"], outn.inputs["Surface"])

    made = 0
    for ri, r in enumerate(runs):
        V, C, F = [], [], []
        for o in r:
            x, y, z = struct.unpack_from("<3h", blob, o + 4)
            V.append((x * SCALE, y * SCALE, z * SCALE))
            C.append((blob[o] / 255.0, blob[o + 1] / 255.0, blob[o + 2] / 255.0, 1.0))
        for k in range(0, len(r) - 2, 3):
            F.append((k, k + 1, k + 2))
        me = bpy.data.meshes.new(f"run{ri:03d}")
        me.from_pydata(V, [], F)
        me.validate(verbose=False)
        try:
            ca = me.color_attributes.new(name="Col", type="BYTE_COLOR", domain="CORNER")
        except Exception:
            ca = me.color_attributes.new(name="Col", type="FLOAT_COLOR", domain="CORNER")
        for poly in me.polygons:
            for li in poly.loop_indices:
                ca.data[li].color = C[me.loops[li].vertex_index]
            poly.use_smooth = False
        me.materials.append(mat)
        ob = bpy.data.objects.new(f"run{ri:03d}_{len(V)}v", me)
        scene.collection.objects.link(ob)
        made += 1
    print(f"built {made} objects")

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
    cam_d.lens = 20
    cam = bpy.data.objects.new("Cam", cam_d)
    scene.collection.objects.link(cam)
    scene.camera = cam
    cam_d.clip_start = 0.01
    # frame everything
    mn = [1e9] * 3
    mx = [-1e9] * 3
    for ob in scene.objects:
        if ob.type != "MESH":
            continue
        for v in ob.data.vertices:
            for i in range(3):
                mn[i] = min(mn[i], v.co[i])
                mx[i] = max(mx[i], v.co[i])
    c = [(mn[i] + mx[i]) / 2 for i in range(3)]
    r = max(mx[i] - mn[i] for i in range(3)) or 1.0
    d = r * 1.6
    cam.location = (c[0] + d * 0.6, c[1] + d * 0.55, c[2] + d * 0.5)
    tgt = bpy.data.objects.new("T", None)
    scene.collection.objects.link(tgt)
    tgt.location = c
    con = cam.constraints.new(type="TRACK_TO")
    con.target = tgt
    con.track_axis = "TRACK_NEGATIVE_Z"
    con.up_axis = "UP_Y"

    bpy.ops.wm.save_as_mainfile(filepath=os.path.abspath(out))
    print("saved", out)


if __name__ == "__main__":
    main()
