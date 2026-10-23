"""Stage verified original source data for the UE project, without an editor.

Source binaries stay byte-identical. BMP -> PNG changes the container only;
RGBA bytes are checked after saving. This is not an Unreal import/build test.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import struct

from PIL import Image


def identity(path: Path):
    return {"path": str(path.resolve()), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}


def run(runtime: Path, project: Path):
    runtime, project = runtime.resolve(strict=True), project.resolve(strict=True)
    destination = project/"Content/SourceData"
    if destination.exists() and destination.is_symlink():
        raise ValueError("source staging destination cannot be a symlink")
    destination.mkdir(parents=True, exist_ok=True)
    inputs, outputs, textures = {}, {}, {}

    def copy_binary(relative: str, target: str):
        source, output = runtime/relative, destination/target
        output.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, output)
        source_id, output_id = identity(source), identity(output)
        if source_id["sha256"] != output_id["sha256"]:
            raise ValueError("binary changed during staging")
        inputs[relative], outputs[target] = source_id, output_id
        return source.read_bytes()

    def texture(relative: str):
        source = runtime/relative
        inputs[relative] = identity(source)
        with Image.open(source) as original:
            rgba = original.convert("RGBA")
            pixels, size = rgba.tobytes(), rgba.size
        digest = hashlib.sha256(struct.pack("<2I", *size)+pixels).hexdigest()
        target = f"textures/rgba_{digest[:24]}.png"
        if digest not in textures:
            output = destination/target
            output.parent.mkdir(parents=True, exist_ok=True)
            rgba.save(output, format="PNG")
            with Image.open(output) as check:
                if check.size != size or check.convert("RGBA").tobytes() != pixels:
                    raise ValueError("PNG staging changed RGBA/alpha bytes")
            resource = {"file": target, "asset": f"/Game/T3B/Textures/T_{digest[:24]}.T_{digest[:24]}",
                        "rgba_sha256": hashlib.sha256(pixels).hexdigest(),
                        "width": size[0], "height": size[1], "container": identity(output),
                        "srgb": False, "filter": "bilinear", "compression": "vector_displacement_uncompressed_rgba"}
            textures[digest] = resource
            outputs[target] = identity(output)
        return textures[digest]

    scene_relative = "assets/scenes/original_street/original_street.bin"
    scene_bytes = copy_binary(scene_relative, "scene/original_street.bin")
    h = struct.unpack_from("<8s4I8f", scene_bytes)
    if h[:5] != (b"T3BSCN1\0", 1, 140, 31656, 81):
        raise ValueError("unexpected verified street counts")
    if len(scene_bytes) != 56+h[2]*12+h[3]*24:
        raise ValueError("invalid street byte count")
    material_file = runtime/"assets/scenes/original_street/original_street_materials.txt"
    lines = [line.split() for line in material_file.read_text(encoding="utf-8").splitlines() if line.strip()]
    inputs[str(material_file.relative_to(runtime)).replace("\\", "/")] = identity(material_file)
    if lines[0] != ["T3BSCNM1", "81"] or len(lines) != 82:
        raise ValueError("incomplete street materials")
    scene_materials, limitations = [], []
    for index, line in enumerate(lines[1:]):
        if len(line) != 4 or any(flag not in ("0", "1") for flag in line[1:]):
            raise ValueError("unrecognized street material state")
        image = texture(line[0])
        blend, depth_write, cull = map(int, line[1:])
        material = {"asset": f"/Game/T3B/Materials/M_Street_{index:03d}.M_Street_{index:03d}",
                    "texture": image["file"], "texture_asset": image["asset"], "blend": blend,
                    "depth_write": depth_write, "cull": cull, "alpha_test": True,
                    "alpha_ref": 0, "rgb_scale": 1., "su": 1., "sv": 1., "ou": 0., "ov": 0.,
                    "wrap_s": 0, "wrap_t": 0, "color_policy": "original_vertex_RGBA"}
        scene_materials.append(material)
        if blend and depth_write:
            limitations.append({"material": material["asset"], "state": "source_alpha_blend_and_main_depth_write",
                                "reason": "Standard UE translucent material does not reproduce source main-pass depth writes; CustomDepth is not equivalent."})

    actors = []
    specs = [
        ("Aya", "assets/models/clips/aya_fire_reverse_capture.bin", "models/aya_fire.bin",
         "assets/materials/original_aya/aya_original_materials.txt", h[5:8], "aya_fire_reverse120"),
        ("Weapon", "assets/models/clips/weapon_fire_reverse_capture.bin", "models/weapon_fire.bin",
         "assets/materials/original_weapon/aya_original_weapon_materials.txt", h[5:8], "aya_fire_reverse120"),
        ("Twisted", "assets/models/original_actor_source.bin", "models/twisted.bin",
         "assets/materials/original_actor/original_actor_materials.txt", h[8:11], "original_actor_source_60"),
    ]
    group_times = {}
    for name, source, target, material_relative, spawn, group in specs:
        data = copy_binary(source, target)
        header = struct.unpack_from("<8s8I4f", data)
        if header[0:2] != (b"T3BSKN2\0", 2) or header[5] != 60:
            raise ValueError("expected a verified 60-sample source skin")
        _, _, bones, packets, vertices, frames, materials, flags, _, _, units, floor, _ = header
        if units != h[-2]:
            raise ValueError("scene/actor canonical units differ")
        time_start = 56+bones*4+packets*16+vertices*100
        expected_size = time_start+frames*4+frames*bones*48
        if len(data) != expected_size:
            raise ValueError("invalid source skin byte count")
        time_bytes = data[time_start:time_start+frames*4]
        if group in group_times and time_bytes != group_times[group]:
            raise ValueError("paired body/weapon source times differ")
        group_times[group] = time_bytes
        matpath = runtime/material_relative
        inputs[material_relative] = identity(matpath)
        rows = [line.split() for line in matpath.read_text(encoding="utf-8").splitlines() if line.strip()]
        if rows[0] != ["T3BMAT1", str(materials)] or len(rows) != materials+1:
            raise ValueError("incomplete actor materials")
        actor_materials = []
        for index, row in enumerate(rows[1:]):
            if len(row) != 10 or int(row[0]) != index:
                raise ValueError("actor material index/shape differs")
            image = texture(row[1])
            item = {"asset": f"/Game/T3B/Materials/M_{name}_{index:03d}.M_{name}_{index:03d}",
                    "texture": image["file"], "texture_asset": image["asset"],
                    "alpha_ref": int(row[2]), "blend": int(bool(flags & 4)), "source_material_blend": int(row[3]),
                    "su": float(row[4]), "sv": float(row[5]), "ou": float(row[6]), "ov": float(row[7]),
                    "wrap_s": int(row[8]), "wrap_t": int(row[9]), "cull": 0, "depth_write": 1,
                    "alpha_test": bool(flags & 8), "rgb_scale": 2. if flags & 2 else 1.,
                    "color_policy": "golden_C_source_local_face_shade_half_when_color_double"}
            actor_materials.append(item)
            if item["blend"] and item["depth_write"]:
                limitations.append({"material": item["asset"], "state": "source_alpha_blend_and_main_depth_write",
                                    "reason": "UE baseline translucency lacks the original main-pass depth-write state."})
        actors.append({"name": name, "binary": target, "spawn": list(spawn), "materials": actor_materials,
                       "bones": bones, "packets": packets, "vertices": vertices, "samples": frames,
                       "units": units, "floor": floor, "flags": flags, "playback": "clamp",
                       "synchronization_group": group, "duration": struct.unpack_from("<f", time_bytes, (frames-1)*4)[0]})

    manifest = {"schema": "t3b-ue-source-bundle/v1", "engine_baseline": "5.8",
                "coordinates": {"pc_to_ue": "(z,x,y)*100", "ue_centimetres_per_PC_unit": 100,
                                "uv_v_flip": False, "matrix_policy": "preserve_full_source_affine_rows; no FTransform decomposition"},
                "scene": {"binary": "scene/original_street.bin", "materials": scene_materials,
                          "draws": h[2], "vertices": h[3], "source_spawn_player": list(h[5:8]), "source_spawn_enemy": list(h[8:11])},
                "actors": actors, "textures": list(textures.values()), "inputs": inputs, "staged_outputs": outputs,
                "unsupported_render_states": limitations,
                "validation": {"binary_identity": True, "PNG_RGBA_lossless": True,
                               "aya_weapon_time_bytes_identical": True,
                               "ue_build_executed": False, "ue_import_executed": False, "ue_render_verified": False},
                "limits": ["This bundle contains original-resolution textures, not HD reconstruction.",
                           "Twisted capture is independent of the Aya/weapon capture; shared preview time does not prove same original frame.",
                           "Baseline shading follows the existing C reference; original GE lighting is not fully recovered.",
                           "UE texture sampling, winding, transparency order and output color must be verified in the real editor.",
                           "No recovered original AI, collision format or complete animation state machine is supplied."]}
    manifest_path = destination/"manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2, allow_nan=False)+"\n", encoding="utf-8")
    report = {"schema": "t3b-ue-staging-verification/v1", "passed": True, "scope": "source bundle staging only",
              "manifest": identity(manifest_path), "scene_draws": h[2], "scene_vertices": h[3],
              "scene_materials": len(scene_materials), "unique_RGBA_textures": len(textures),
              "actor_samples": {actor["name"]: actor["samples"] for actor in actors},
              "unsupported_render_materials": len(limitations), "ue_executed": False}
    report_path = project/"Validation/source_bundle_staging.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2)+"\n", encoding="utf-8")
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runtime-root", type=Path, default=Path(__file__).resolve().parents[2]/"t3b_hd")
    parser.add_argument("--project-root", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    print(json.dumps(run(args.runtime_root, args.project_root)))
