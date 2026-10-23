"""show_objs.py -- import a folder of OBJs, lay them out in a grid, save a .blend and render.

    blender -b --factory-startup -P tools/show_objs.py -- --dir DIR --out X.blend --png Y.png
"""
import bpy
import math
import os
import sys


def main():
    argv = sys.argv[sys.argv.index("--") + 1:]
    src = out = png = None
    for i, a in enumerate(argv):
        if a == "--dir":
            src = argv[i + 1]
        elif a == "--out":
            out = argv[i + 1]
        elif a == "--png":
            png = argv[i + 1]

    bpy.ops.wm.read_factory_settings(use_empty=True)
    files = sorted(f for f in os.listdir(src) if f.endswith(".obj"))
    cols = 5
    for k, fn in enumerate(files):
        before = set(bpy.data.objects)
        bpy.ops.wm.obj_import(filepath=os.path.join(src, fn))
        new = [o for o in bpy.data.objects if o not in before]
        for ob in new:
            ob.location = ((k % cols) * 2.0, 0.0, -(k // cols) * 2.4)
            for slot in ob.material_slots:
                if slot.material:
                    slot.material.use_nodes = True
                    bsdf = slot.material.node_tree.nodes.get("Principled BSDF")
                    if bsdf:
                        bsdf.inputs["Base Color"].default_value = (0.75, 0.55, 0.5, 1)
                        bsdf.inputs["Roughness"].default_value = 0.8

    rows = (len(files) + cols - 1) // cols
    cam_data = bpy.data.cameras.new("cam")
    cam_data.type = "ORTHO"
    cam_data.ortho_scale = max(cols * 2.0, rows * 2.6) * 1.15
    cam = bpy.data.objects.new("cam", cam_data)
    cam.location = ((cols - 1) * 1.0, -14.0, -(rows - 1) * 1.2)
    cam.rotation_euler = (math.radians(90), 0, 0)
    bpy.context.collection.objects.link(cam)
    bpy.context.scene.camera = cam

    sun_data = bpy.data.lights.new("sun", type="SUN")
    sun_data.energy = 4.0
    sun = bpy.data.objects.new("sun", sun_data)
    sun.rotation_euler = (math.radians(45), math.radians(20), 0)
    bpy.context.collection.objects.link(sun)

    sc = bpy.context.scene
    sc.render.resolution_x = 1400
    sc.render.resolution_y = max(400, int(1400 * rows / cols))
    sc.render.image_settings.file_format = "PNG"
    if png:
        sc.render.filepath = os.path.abspath(png)
        bpy.ops.render.render(write_still=True)
    if out:
        bpy.ops.wm.save_as_mainfile(filepath=os.path.abspath(out))
    print("objects:", len(files), "saved", out, png)


main()
