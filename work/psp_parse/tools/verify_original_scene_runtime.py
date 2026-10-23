"""Verify compiled street loading against every exported vertex bit and draw.

This establishes C import/render submission, not original collision or complete
level recovery. Original GE/texture verification belongs to verify_original_scene.
"""
import argparse
import csv
import hashlib
import json
from pathlib import Path
import shutil
import struct

from verify_source_skin_runtime import read_kv


def identity(path):
    return {"path": str(path.resolve()), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}


def verify(root):
    asset = root / "assets/scenes/original_street/original_street.bin"
    manifest = asset.with_name("original_street_materials.txt")
    data = asset.read_bytes()
    header = struct.unpack_from("<8s4I8f", data)
    if header[:5] != (b"T3BSCN1\0", 1, 140, 31656, 81):
        raise ValueError("unexpected verified street identity/counts")
    _, _, draws, vertices, materials, *_ = header
    aya_units, aya_floor = struct.unpack_from("<2f", (root/"assets/models/aya_source_skin.bin").read_bytes(), 44)
    if tuple(header[-2:]) != (aya_units, aya_floor):
        raise ValueError("scene and Aya do not share the exact canonical units/floor")
    if len(data) != 56 + 12*draws + 24*vertices:
        raise ValueError("truncated or extra original scene bytes")
    packets = [struct.unpack_from("<3I", data, 56 + i*12) for i in range(draws)]
    vertex_start = 56 + draws*12
    with (root / "build/original_scene_probe.csv").open(encoding="utf-8", newline="") as source:
        rows = list(csv.DictReader(source))
    if len(rows) != vertices:
        raise ValueError("compiled probe must cover all original street vertices")
    next_vertex = nonwhite = nonopaque = repeating = 0
    for draw, (first, count, material) in enumerate(packets):
        if first != next_vertex or not count or count % 3 or first+count > vertices or material >= materials:
            raise ValueError("invalid ordered scene packet")
        for i in range(first, first+count):
            row = rows[i]
            if [int(row[k]) for k in ("vertex", "draw", "material")] != [i, draw, material]:
                raise ValueError("C draw, material or vertex order changed")
            off = vertex_start + i*24
            expected_bits = struct.unpack_from("<5I", data, off)
            actual_bits = tuple(int(row[k], 16) for k in ("xbits", "ybits", "zbits", "ubits", "vbits"))
            if actual_bits != expected_bits:
                raise ValueError(f"C float position/UV bits changed at vertex {i}")
            rgba = struct.unpack_from("<4B", data, off+20)
            if tuple(int(row[k]) for k in ("r", "g", "b", "a")) != rgba:
                raise ValueError(f"C vertex RGBA changed at vertex {i}")
            nonwhite += rgba[:3] != (255, 255, 255)
            nonopaque += rgba[3] != 255
            u, v = struct.unpack_from("<2f", data, off+12)
            repeating += not (0 <= u <= 1 and 0 <= v <= 1)
        next_vertex += count
    if next_vertex != vertices:
        raise ValueError("incomplete ordered scene packets")
    lines = [line.split() for line in manifest.read_text(encoding="utf-8").splitlines() if line.strip()]
    if lines[0] != ["T3BSCNM1", "81"] or len(lines) != 82:
        raise ValueError("material manifest does not contain all original states")
    textures = {}
    for line in lines[1:]:
        if len(line) != 4 or any(x not in ("0", "1") for x in line[1:]):
            raise ValueError("unexpected street material state")
        texture = root / line[0]
        textures[line[0]] = identity(texture)
    if len(textures) != 73:
        raise ValueError("original street must retain its 73 unique texture resources")
    result_path = root / "build/m1_source_skin_result.txt"
    runtime = read_kv(result_path)
    required = {"original_scene_enabled": 1, "original_scene_draws": draws,
                "original_scene_vertices": vertices, "original_scene_triangles": vertices//3,
                "original_scene_materials": materials, "original_scene_probe_vertices": vertices,
                "original_scene_nonwhite_vertices": nonwhite, "original_scene_nonopaque_vertices": nonopaque,
                "collision_recovered": 0,
                "original_scene_source_winding_preserved": 1,
                "original_scene_context_gl_errors": 0,
                "original_scene_fog_supported": 0, "original_scene_stencil_supported": 0}
    source_adapter = runtime.get("collision_adapter_source") == "original_visible_static_triangles"
    required["scene_render_only"] = 0 if source_adapter else 1
    if source_adapter:
        required.update(original_scene_behavior_recovered=0, collision_solid_materials=63, collision_solid_triangles=8551)
    for key, value in required.items():
        if runtime.get(key) != value:
            raise ValueError(f"original street C runtime regression: {key}={runtime.get(key)}")
    frames = runtime.get("original_scene_rendered_frames", 0)
    if frames < 1 or runtime.get("original_scene_rendered_draws") != frames*draws:
        raise ValueError("renderer did not submit every draw in original order each frame")
    return {"schema": "original-scene-C-runtime-verification/v1", "passed": True,
            "scope": "all C-imported vertex bits, draw/material order, resources and render submission",
            "asset": identity(asset), "manifest": identity(manifest), "textures": textures,
            "draws": draws, "vertices": vertices, "triangles": vertices//3, "material_states": materials,
            "original_nonwhite_vertices": nonwhite, "original_nonopaque_vertices": nonopaque,
            "raw_uv_outside_unit_square_vertices": repeating,
            "float_bit_differences": 0, "vertex_color_byte_differences": 0,
            "rendered_frames": frames, "rendered_draws": frames*draws,
            "runtime_mode": runtime.get("test_mode_name"),
            "limits": ["Visible static main-camera street subset; not a complete level.",
                       "Original fog and stencil are retained in metadata but not rendered.",
                       "Original collision, events and navigation are not recovered.",
                       "Textures preserve original resolution; HD texture reconstruction remains open."]}


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--runtime-root", type=Path, required=True)
    ap.add_argument("--archive", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--executable", type=Path)
    a = ap.parse_args()
    report = verify(a.runtime_root)
    a.archive.mkdir(parents=True, exist_ok=True)
    report["archived"] = {}
    for path in (a.executable or a.runtime_root/"t3b_hd.exe",
                 a.runtime_root/"build/original_scene_probe.csv",
                 a.runtime_root/"build/m1_source_skin_result.txt",
                 a.runtime_root/"build/m1_test_result.txt"):
        dest = a.archive / path.name
        shutil.copyfile(path, dest)
        report["archived"][path.name] = identity(dest)
    a.out.write_text(json.dumps(report, indent=2)+"\n", encoding="utf-8")
    print(json.dumps({k: v for k, v in report.items() if k not in ("textures", "archived", "limits")}))


if __name__ == "__main__":
    main()
