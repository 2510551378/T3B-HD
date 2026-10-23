"""dump_blend.py -- build one .blend containing every decodable VERTICES block of a frame dump.

    blender -b --factory-startup -P tools/dump_blend.py -- --src dump.ppdmp --out X.blend [--grid]
"""
import os
import struct
import sys

import bpy
import math
import numpy as np

sys.path.insert(0, r"work\psp_parse\archive")
from ppdmp2 import read  # noqa: E402

SC = 3.125 / 32768.0


def score(P):
    if len(P) < 24:
        return None
    if not np.isfinite(P).all() or np.abs(P).max() > 100:
        return None
    d = np.linalg.norm(np.diff(P, axis=0), axis=1)
    med = float(np.median(d))
    if not (0.0005 <= med <= 0.45):
        return None
    ext = np.sort(P.max(axis=0) - P.min(axis=0))
    if ext[2] < 0.2:
        return None
    good = float(np.mean((d > 1e-6) & (d < max(0.2, med * 5))))
    if good < 0.6:
        return None
    return good, med, ext


def best_layout(blk):
    best = None
    for dt, size in (("h", 2), ("f", 4)):
        usable = (len(blk) // size) * size
        raw = np.frombuffer(blk[:usable], dtype="<i2" if dt == "h" else "<f4")
        total = len(raw)
        for stride in range(8, 65):
            if stride % size:
                continue
            step = stride // size
            for off in range(0, stride - 3 * size + 1, size):
                base = off // size
                cnt = (total - base) // step
                if cnt < 24:
                    continue
                w = raw[base:base + cnt * step].reshape(cnt, step)[:, :3]
                P = w.astype(np.float64)
                if dt == "h":
                    P *= SC
                sc = score(P)
                if not sc:
                    continue
                good, med, ext = sc
                rank = (good, -med)
                if best is None or rank > best[0]:
                    best = (rank, stride, dt, off, cnt, med, ext, P)
    return best


def main():
    argv = sys.argv[sys.argv.index("--") + 1:]
    src = out = None
    for i, a in enumerate(argv):
        if a == "--src":
            src = argv[i + 1]
        elif a == "--out":
            out = argv[i + 1]

    cmds, buf = read(src)
    bpy.ops.wm.read_factory_settings(use_empty=True)
    mat = bpy.data.materials.new("vcol")
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes["Principled BSDF"]
    vc = mat.node_tree.nodes.new("ShaderNodeVertexColor")
    vc.layer_name = "Col"
    mat.node_tree.links.new(vc.outputs["Color"], bsdf.inputs["Base Color"])

    cols = 10
    made = 0
    for i, (t, sz, ptr) in enumerate(cmds):
        if t != 2 or sz < 96 or ptr + sz > len(buf):
            continue
        blk = buf[ptr:ptr + sz]
        r = best_layout(blk)
        if not r:
            continue
        rank, stride, dt, off, cnt, med, ext, P = r
        colors = None
        if stride == 20 and sz % 20 == 0:
            colors = [(blk[k * 20 + 8] / 255.0, blk[k * 20 + 9] / 255.0,
                       blk[k * 20 + 10] / 255.0, 1.0) for k in range(cnt)]
        me = bpy.data.meshes.new(f"d{i}")
        me.from_pydata([tuple(p) for p in P], [],
                       [(k, k + 1, k + 2) for k in range(0, cnt - 2, 3)])
        me.update()
        if colors:
            ca = me.color_attributes.new(name="Col", type="FLOAT_COLOR", domain="POINT")
            for k, c in enumerate(colors[: len(me.vertices)]):
                ca.data[k].color = c
        ob = bpy.data.objects.new(f"cmd{i:04d}_{cnt}v_s{stride}{dt}", me)
        ob.data.materials.append(mat)
        ob.location = ((made % cols) * 2.0, 0.0, -(made // cols) * 2.2)
        bpy.context.collection.objects.link(ob)
        made += 1

    rows = max(1, (made + cols - 1) // cols)
    cd = bpy.data.cameras.new("cam")
    cd.type = "ORTHO"
    cd.ortho_scale = max(cols * 2.0, rows * 2.2) * 1.1
    cam = bpy.data.objects.new("cam", cd)
    cam.location = ((cols - 1) * 1.0, -20.0, -(rows - 1) * 1.1)
    tgt = bpy.data.objects.new("aim", None)
    tgt.location = cam.location + __import__("mathutils").Vector((0, 20, 0))
    bpy.context.collection.objects.link(tgt)
    con = cam.constraints.new("TRACK_TO")
    con.target = tgt
    con.track_axis = "TRACK_NEGATIVE_Z"
    con.up_axis = "UP_Y"
    bpy.context.collection.objects.link(cam)
    bpy.context.scene.camera = cam

    bpy.context.scene.render.engine = "BLENDER_WORKBENCH"
    bpy.ops.wm.save_as_mainfile(filepath=os.path.abspath(out))
    print(f"built {made} objects -> {out}")


main()
