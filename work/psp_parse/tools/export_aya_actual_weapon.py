"""Export the independently identified original weapon, using per-frame GE WORLD.

No hand/socket anatomy is invented. T3BSKN2 uses one virtual root and the exact
captured relative-world timeline; source weights are folded into local positions
before relative WORLD translation, preserving original GE transform order.
"""
import argparse
import hashlib
import json
import shutil
import struct
from pathlib import Path

import numpy as np
from PIL import Image

from exact_aya_materials import (decode_texture, iter_material_draws,
                                 material_parameters, write_rgba_bmp)
from extract_runtime_character import layout, read_ppdmp
from export_aya_source_skin import (calibrated_scene_conversion, decode_ge, pose_vertices,
                                    resolve_output_model, scene_conversion)


WEAPON_SHA = "168578abca4c4f5d22d5994ebced6b93a25d5167428bfd47f1a1150a8d42e65a"


def sha(data):
    return hashlib.sha256(data).hexdigest()


def affine(words):
    values = np.asarray(words, dtype="<u4") << 8
    result = np.eye(4, dtype=np.float64)
    result[:3] = values.view("<f4").reshape(3, 4, order="F")
    return result


def matrix_draws(commands, push):
    """Replay explicit matrix writes only, stopping exactly at each PRIM."""
    matrices = {"world": [None] * 12, "view": [None] * 12, "bones": [None] * 96}
    cursors = dict(world=0, view=0, bones=0)
    cursor_commands = {0x3a: "world", 0x3c: "view", 0x2a: "bones"}
    data_commands = {0x3b: "world", 0x3d: "view", 0x2b: "bones"}
    vtype = vertices = None
    for ordinal, (kind, size, pointer) in enumerate(commands):
        if pointer + size > len(push):
            raise ValueError("record outside push buffer")
        if kind == 2:
            vertices = ordinal, size, pointer
        elif kind == 1:
            for offset in range(0, size, 4):
                word = struct.unpack_from("<I", push, pointer + offset)[0]
                cmd, value = word >> 24, word & 0xffffff
                if cmd == 0x12:
                    vtype = value
                elif cmd in cursor_commands:
                    key = cursor_commands[cmd]
                    cursors[key] = value & (127 if key == "bones" else 15)
                elif cmd in data_commands:
                    key = data_commands[cmd]
                    cursor = cursors[key]
                    if cursor < len(matrices[key]):
                        matrices[key][cursor] = value
                    cursors[key] = (cursor + 1) & (127 if key == "bones" else 15)
                elif cmd == 4 and vertices is not None and vtype is not None:
                    yield {"vertex_record": vertices[0], "size": vertices[1], "pointer": vertices[2],
                           "register_record": ordinal, "register_word": offset // 4,
                           "primitive": (value >> 16) & 7, "count": value & 0xffff, "vtype": vtype,
                           "sha256": sha(struct.pack("<I", vtype) + push[vertices[2]:vertices[2] + vertices[1]]),
                           **{key: list(values) for key, values in matrices.items()}}


def vertices_from_raw(raw, vtype):
    if vtype != 0x522:
        raise ValueError("weapon VTYPE does not equal independently identified 0x522")
    stride, offsets = layout(vtype)
    if stride != 16 or len(raw) != 243 * stride:
        raise ValueError("weapon geometry size/stride mismatch")
    vertices = []
    for at in range(0, len(raw), stride):
        weight = struct.unpack_from("<H", raw, at + offsets["wt"][0])[0]
        uv = list(struct.unpack_from("<2H", raw, at + offsets["uv"][0]))
        normal = list(struct.unpack_from("<3b", raw, at + offsets["nrm"][0]))
        pos = list(struct.unpack_from("<3h", raw, at + offsets["pos"][0]))
        if weight != 32767:
            raise ValueError("weapon source weight differs from verified 32767")
        vertices.append({"position_raw": pos, "uv_raw": uv, "normal_raw": normal,
                         "weight_raw": weight, "weight": weight / 32768,
                         "source_vertex_hex": raw[at:at + stride].hex()})
    return vertices


def sample_times(frames, timing):
    ticks = [frame["ticks"] for frame in frames]
    if len(frames) < 2 or any(y <= x for x, y in zip(ticks, ticks[1:])):
        raise ValueError("requires at least two chronological original weapon samples")
    if not np.isfinite(timing["cpu_hz"]) or timing["cpu_hz"] <= 0:
        raise ValueError("invalid saved CPU clock")
    times = np.asarray([(t - ticks[0]) / timing["cpu_hz"] for t in ticks], dtype="<f4")
    if not np.all(np.isfinite(times)) or np.any(np.diff(times) <= 0):
        raise ValueError("sample times must remain finite and strictly increasing after float32 packing")
    return times


def validate_body_capture(body, metadata_path, manifest_path, timing_path, frames, times):
    """Reject a stale/cross-clip body report, including an unverified floor calibration."""
    expected_inputs = {"metadata": metadata_path, "manifest": manifest_path, "timing": timing_path}
    for name, path in expected_inputs.items():
        identity = body["inputs"][name]
        if Path(identity["path"]).resolve() != path.resolve() or identity["sha256"] != sha(path.read_bytes()):
            raise ValueError(f"body report {name} identity differs from this capture")
    timing = json.loads(timing_path.read_text(encoding="utf-8"))
    if body["samples"] != len(frames) or body["sample_times_seconds"] != times.tolist():
        raise ValueError("body and weapon sample count/time coordinates differ")
    if body["saved_cpu_hz"] != timing["cpu_hz"]:
        raise ValueError("body and weapon saved CPU clocks differ")
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    rows = {r["index"]: r["matrix"] for r in frames[0]["records"]}
    if set(rows) != set(range(44)):
        raise ValueError("body first sample must contain exactly 44 original source matrices")
    original = np.asarray([decode_ge(rows[i]) for i in range(44)], dtype="<f4")
    reference = pose_vertices([v for p in metadata["packets"] for v in p["vertices"]], original)
    actual_units, actual_floor = scene_conversion(metadata, reference)
    calibration = body.get("reference_scale_calibration")
    if calibration is None:
        if "reference_scale_report" in body["inputs"]:
            raise ValueError("body calibration identity exists without a declared calibration")
        units, floor = actual_units, actual_floor
    else:
        reference_identity = body["inputs"].get("reference_scale_report")
        if reference_identity is None:
            raise ValueError("body calibration lacks its reference report identity")
        reference_path = Path(reference_identity["path"])
        if reference_identity["sha256"] != sha(reference_path.read_bytes()):
            raise ValueError("body canonical scale report SHA256 changed")
        units, floor, expected_calibration = calibrated_scene_conversion(metadata_path, actual_units, actual_floor, reference_path)
        if calibration != expected_calibration:
            raise ValueError("body scale calibration declaration differs from verified reference report")
    if (body["pc_units_per_original_unit"] != units or body["reference_floor"] != floor
            or body.get("actual_reference_floor", body["reference_floor"]) != actual_floor):
        raise ValueError("body scene units/floor do not match this capture and its declared calibration")
    return units, floor, actual_floor, calibration


def geometry_measurements(vertices):
    raw = np.asarray([v["position_raw"] for v in vertices], dtype=np.int32)
    unique = np.unique(raw, axis=0)
    normalized = unique.astype(np.float64) / 32768
    center = normalized.mean(axis=0)
    eigenvalues, eigenvectors = np.linalg.eigh(np.cov((normalized - center).T))
    major = eigenvectors[:, -1]
    if major[np.argmax(np.abs(major))] > 0:
        major = -major  # PCA sign is arbitrary; use negative dominant coordinate consistently.
    result = {"unique_positions": len(unique),
              "normalized_raw_bbox": [normalized.min(axis=0).tolist(), normalized.max(axis=0).tolist()],
              "normalized_raw_extents": np.ptp(normalized, axis=0).tolist(),
              "pca_center": center.tolist(), "pca_principal_axis": major.tolist(),
              "pca_eigenvalues_ascending": eigenvalues.tolist(),
              "pca_sign_convention": "dominant coordinate is negative; PCA sign has no anatomical meaning"}
    # Visual side/top projections confirm the slender protruding barrel is at -X.
    # Validate its triangular cross-section at the end and the next identical section.
    minimum = unique[:, 0].min()
    tip = unique[unique[:, 0] == minimum]
    if len(tip) != 3 or np.ptp(tip[:, 1]) <= 0 or np.ptp(tip[:, 2]) <= 0:
        result["muzzle_geometry_candidate"] = {"status": "unresolved tip cross-section"}
        return result
    tip_yz = {tuple(point[1:]) for point in tip}
    matches = []
    for x in np.unique(unique[:, 0]):
        if x <= minimum:
            continue
        section = unique[unique[:, 0] == x]
        selected = np.asarray([point for point in section if tuple(point[1:]) in tip_yz])
        if len(selected) == 3:
            matches.append(selected)
    if not matches:
        result["muzzle_geometry_candidate"] = {"status": "unresolved matching barrel cross-section"}
        return result
    base = matches[0]
    tip_mean = tip.mean(axis=0) / 32768
    base_mean = base.mean(axis=0) / 32768
    direction = tip_mean - base_mean
    direction /= np.linalg.norm(direction)
    weights = {v["weight"] for v in vertices}
    if len(weights) != 1:
        raise ValueError("geometry tip weighting needs a uniform verified source weight")
    source_weight = weights.pop()
    end_vertices = [i for i, point in enumerate(raw) if point[0] == minimum]
    cap_triangles = [i // 3 for i in range(0, len(raw), 3) if np.all(raw[i:i + 3, 0] == minimum)]
    result["muzzle_geometry_candidate"] = {
        "status": "geometry-derived candidate only, not a recovered original muzzle/socket datum",
        "basis": "negative-X barrel end triangle and next section with the same three YZ coordinates; confirmed in side/top mesh projections",
        "tip_unique_positions_raw": tip.tolist(), "barrel_base_positions_raw": base.tolist(),
        "tip_vertex_records": end_vertices, "tip_cap_triangles": cap_triangles,
        "tip_normalized_raw": tip_mean.tolist(), "barrel_base_normalized_raw": base_mean.tolist(),
        "direction_local": direction.tolist(),
        "runtime_local_position": (tip_mean * source_weight).tolist(),
        "runtime_local_direction": direction.tolist(),
        "runtime_formula": "actor_tip = exported_actor_matrix * [runtime_local_position,1]; PC world conversion uses same body unit scale/floor",
        "original_socket_claim": False}
    return result


def recover(args):
    metadata = json.loads(args.metadata.read_text(encoding="utf-8"))
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    timing = json.loads(args.timing.read_text(encoding="utf-8"))
    frames = manifest["frames"]
    times = sample_times(frames, timing)
    frame_count = len(frames)
    body = None
    runtime_model = None
    if not args.analysis_only:
        runtime_model = resolve_output_model(args.runtime_root, args.output_model)
        body = json.loads(args.body_report.read_text(encoding="utf-8"))
        units, floor, actual_floor, calibration = validate_body_capture(body, args.metadata, args.manifest, args.timing, frames, times)
    packet_by_sha = {packet["vertex_sha256"]: packet for packet in metadata["packets"]}
    if len(packet_by_sha) != 106 or WEAPON_SHA in packet_by_sha:
        raise ValueError("weapon identity overlaps Aya mesh or Aya packet identities are ambiguous")
    args.out.mkdir(parents=True, exist_ok=True)
    rows, transforms, body_source15 = [], [], []
    reference_geometry = reference_rgba = reference_params = None
    material_info = None
    for frame in frames:
        capture = args.manifest.parent / Path(frame["dump"]["file"]).name
        commands, push = read_ppdmp(str(capture))
        body, weapons, observed_source15 = [], [], []
        for draw in matrix_draws(commands, push):
            if draw["sha256"] in packet_by_sha:
                packet = packet_by_sha[draw["sha256"]]
                body.append(draw)
                for slot in packet["active_palette_indices"]:
                    if packet["palette_state"][str(slot)] == 15:
                        observed_source15.append(draw["bones"][slot * 12:slot * 12 + 12])
            if draw["sha256"] == WEAPON_SHA:
                weapons.append(draw)
        if len(body) != 106 or len({d["sha256"] for d in body}) != 106 or len(weapons) != 1:
            raise ValueError("each capture must have all 106 Aya packets and exactly one weapon")
        if any(None in d["world"] or None in d["view"] for d in body + weapons):
            raise ValueError("WORLD/VIEW not fully established by explicit commands")
        if any(d["world"] != body[0]["world"] or d["view"] != body[0]["view"] for d in body):
            raise ValueError("Aya WORLD/VIEW changes within 106 verified mesh packets")
        weapon = weapons[0]
        if weapon["view"] != body[0]["view"]:
            raise ValueError("body/weapon VIEW mismatch")
        if weapon["primitive"] != 3 or weapon["count"] != 243:
            raise ValueError("weapon primitive/count mismatch")
        bone_bits = weapon["bones"][:12]
        if None in bone_bits:
            raise ValueError("weapon bone0 is not fully established")
        bone = affine(bone_bits)
        expected = np.eye(4)
        expected[:3, :3] *= 59.2998046875
        if not np.array_equal(bone, expected):
            raise ValueError("weapon bone differs from 59.2998046875 I with zero translation")
        if not observed_source15 or any(bits != observed_source15[0] for bits in observed_source15):
            raise ValueError("Aya source15 not consistently represented in actual GE draws")
        body_source15.append(affine(observed_source15[0]))
        original_world = affine(weapon["world"])
        body_world = affine(body[0]["world"])
        relative_world = np.linalg.inv(body_world) @ original_world
        transform = relative_world @ bone
        transforms.append(transform)
        raw = push[weapon["pointer"]:weapon["pointer"] + weapon["size"]]
        if reference_geometry is None:
            reference_geometry = raw
        elif reference_geometry != raw:
            raise ValueError("weapon vertex bytes changed across captures")
        material_draws = [d for d in iter_material_draws(commands, push)
                          if d["vertices"]["record"] == weapon["vertex_record"]
                          and d["register_record"] == weapon["register_record"]
                          and d["register_word"] == weapon["register_word"]]
        if len(material_draws) != 1:
            raise ValueError("weapon PRIM material replay cannot be uniquely aligned")
        material = material_draws[0]
        texture = material["texture0"]
        if texture is None or texture["framebuffer"]:
            raise ValueError("weapon texture is not ordinary TEXTURE0 bytes")
        rgba, facts = decode_texture(texture["raw"], material["registers"], material["clut"], material["clut_known"])
        params = material_parameters(material["registers"])
        if facts["width"] != 64 or facts["height"] != 64 or facts["format_id"] != 5:
            raise ValueError("weapon texture does not match independently identified CLUT8 64x64")
        if reference_rgba is None:
            reference_rgba, reference_params = rgba, params
            material_info = {**facts, "parameters": params, "texture_sha256": texture["sha256"],
                             "clut_sha256": sha(material["clut"][:1024]),
                             "texture_record": texture["record"], "clut_records": material["clut_records"],
                             "runtime_material_index": 0}
            (args.out / "weapon.texture.bin").write_bytes(texture["raw"])
            (args.out / "weapon.clut.bin").write_bytes(material["clut"][:1024])
        elif rgba != reference_rgba or params != reference_params or texture["sha256"] != material_info["texture_sha256"] or sha(material["clut"][:1024]) != material_info["clut_sha256"]:
            raise ValueError("weapon material changed across capture timeline")
        rows.append({"frame": frame["frame"], "ticks": frame["ticks"], "capture": str(capture.resolve()),
                     "capture_sha256": sha(capture.read_bytes()), "aya_packet_count": len(body),
                     "weapon_vertex_record": weapon["vertex_record"],
                     "weapon_register_record": weapon["register_record"], "weapon_register_word": weapon["register_word"],
                     "body_world_float24": body[0]["world"], "weapon_world_float24": weapon["world"],
                     "shared_view_float24": weapon["view"], "weapon_bone_float24": bone_bits,
                     "source15_float24": observed_source15[0],
                     "relative_world": relative_world.tolist(), "actor_space_matrix": transform.tolist(),
                     "material_state": {f"0x{k:02x}": value for k, value in sorted(material["registers"].items())},
                     "texture_sha256": texture["sha256"], "clut_sha256": sha(material["clut"][:1024])})
    vertices = vertices_from_raw(reference_geometry, 0x522)
    (args.out / "weapon.vertices.bin").write_bytes(reference_geometry)
    stem = "aya_weapon_" + material_info["rgba_sha256"][:16]
    png, bmp = args.out / (stem + ".png"), args.out / (stem + ".bmp")
    Image.frombytes("RGBA", (64, 64), reference_rgba).save(png)
    write_rgba_bmp(bmp, 64, 64, reference_rgba)
    material_info.update(png=str(png.resolve()), bmp=str(bmp.resolve()), png_sha256=sha(png.read_bytes()), bmp_sha256=sha(bmp.read_bytes()))
    params = reference_params
    if (params["uv_map_mode"] != 0 or params["uv_storage_type"] != 2
            or params["uv_through_mode"] or params["alpha_test_function"] != 6
            or params["alpha_test_mask"] != 255 or not params["alpha_test_enabled"]
            or [params["blend_src_factor"], params["blend_dst_factor"], params["blend_equation"]] != [2, 3, 0]):
        raise ValueError("weapon state cannot be represented by current M1 material interchange")
    material_manifest = args.out / "aya_original_weapon_materials.txt"
    values = [0, "assets/materials/original_weapon/" + bmp.name, params["alpha_test_ref"], int(params["alpha_blend_enabled"]),
              *params["uv_scale"], *params["uv_offset"], int(params["wrap_u"] == "clamp"), int(params["wrap_v"] == "clamp")]
    material_manifest.write_text("T3BMAT1 1\n" + " ".join(map(str, values)) + "\n", encoding="utf-8")
    # Quantify export packing independently against the original GE operation order.
    local = np.asarray([v["position_raw"] for v in vertices], dtype=np.float64) / 32768
    source_weights = np.asarray([v["weight"] for v in vertices], dtype=np.float64)
    packed_positions = np.asarray(local * source_weights[:, None], dtype="<f4")
    packed_matrices = np.asarray([matrix[:3] for matrix in transforms], dtype="<f4")
    max_errors = []
    fixed_source15 = np.linalg.inv(body_source15[0]) @ transforms[0]
    attachment_errors = []
    posed = []
    for i, (row, transform) in enumerate(zip(rows, transforms)):
        world = affine(row["weapon_world_float24"])
        inv_body = np.linalg.inv(affine(row["body_world_float24"]))
        bone = affine(row["weapon_bone_float24"])
        bone_positions = local @ bone[:3, :3].T + bone[:3, 3]
        weighted = bone_positions * source_weights[:, None]
        original = weighted @ world[:3, :3].T + world[:3, 3]
        original_actor = original @ inv_body[:3, :3].T + inv_body[:3, 3]
        exported = packed_positions @ packed_matrices[i, :, :3].T + packed_matrices[i, :, 3]
        max_errors.append(float(np.linalg.norm(original_actor - exported, axis=1).max()))
        posed.append(exported)
        predicted_matrix = body_source15[i] @ fixed_source15
        predicted = (local * source_weights[:, None]) @ predicted_matrix[:3, :3].T + predicted_matrix[:3, 3]
        attachment_errors.append(float(np.linalg.norm(original_actor - predicted, axis=1).max()))
    if max(max_errors) > 0.0001:
        raise ValueError("T3BSKN2 float32 packing exceeds weapon position tolerance")
    report = {"schema": "aya-actual-weapon-export/v1", "geometry_sha256": WEAPON_SHA,
              "vertex_bytes_sha256": sha(reference_geometry), "geometry_excludes_aya_106_packets": True,
              "packets": 1, "vertices": 243, "triangles": 81, "virtual_bones": 1,
              "samples": frame_count, "sample_times_seconds": times.tolist(), "saved_cpu_hz": timing["cpu_hz"],
              "weight_preservation": "source u16/32768 is folded into local position before relative WORLD translation; virtual bone weight is 1",
              "geometry_measurements": geometry_measurements(vertices),
              "source_vertices": vertices, "material": material_info, "frames": rows,
              "position_validation": {"max_error_by_frame_original_units": max_errors,
                                      "max_error_original_units": max(max_errors), "tolerance_original_units": 0.0001},
              "source15_candidate_only": {"constant_frame0_attachment": fixed_source15.tolist(),
                                          "max_vertex_error_by_frame_original_units": attachment_errors,
                                          "max_vertex_error_original_units": max(attachment_errors),
                                          "status": "candidate only; not used by export and no anatomical name assigned"},
              "inputs": {name: {"path": str(path.resolve()), "sha256": sha(path.read_bytes())} for name, path in
                         [("metadata", args.metadata), ("manifest", args.manifest), ("timing", args.timing)]},
              "analysis_only": args.analysis_only,
              "limitations": ["Sparse original runtime poses, not a recovered complete animation clip.",
                              "Weapon geometry identity is byte exact; no original weapon asset name or muzzle/grip landmark is invented.",
                              "Relative WORLD is captured per frame rather than approximated by an anatomical socket.",
                              "Source15 is an attachment candidate only; no anatomical assignment is made.",
                              "Saved CPU_HZ is verified at save time; later unrecorded CPU clock changes remain an input limitation."]}
    if not args.analysis_only:
        flags = 1 | (2 if params["color_double"] else 0) | (4 if params["alpha_blend_enabled"] else 0) | (8 if params["alpha_test_enabled"] else 0)
        content = bytearray(struct.pack("<8s8I4f", b"T3BSKN2\0", 2, 1, 1, 243, frame_count, 1, flags, 0, 0, units, floor, 0))
        content.extend(struct.pack("<i4I", -1, 0, 243, 0, 3))
        for vertex, position in zip(vertices, packed_positions):
            uv = [v / 32768 for v in vertex["uv_raw"]]
            normal = [v / 128 for v in vertex["normal_raw"]]
            content.extend(struct.pack("<8fI8I8f", *position, *uv, *normal, 1, *([0] * 8), 1.0, *([0.0] * 7)))
        content.extend(times.tobytes())
        content.extend(packed_matrices.tobytes())
        expected_size = 76 + 24300 + frame_count * (4 + 48)
        if len(content) != expected_size:
            raise ValueError("T3BSKN2 output byte size mismatch")
        exported_path = args.out / args.output_model.name
        exported_path.write_bytes(content)
        binary = exported_path.read_bytes()
        header = struct.unpack_from("<8s8I4f", binary)
        if header[:9] != (b"T3BSKN2\0", 2, 1, 1, 243, frame_count, 1, flags, 0):
            raise ValueError("binary header readback mismatch")
        decoded_positions = []
        for i in range(243):
            vertex = struct.unpack_from("<8fI8I8f", binary, 76 + 100 * i)
            if vertex[8] != 1 or any(vertex[9:17]) or vertex[17] != 1 or any(vertex[18:25]):
                raise ValueError("binary influence readback mismatch")
            decoded_positions.append(vertex[:3])
        if not np.array_equal(np.asarray(decoded_positions, dtype="<f4"), packed_positions):
            raise ValueError("binary position readback mismatch")
        decoded_times = np.frombuffer(binary, dtype="<f4", count=frame_count, offset=76 + 24300)
        decoded_matrices = np.frombuffer(binary, dtype="<f4", count=frame_count * 12, offset=76 + 24300 + frame_count * 4).reshape(frame_count, 3, 4)
        if not np.array_equal(decoded_times, times) or not np.array_equal(decoded_matrices, packed_matrices):
            raise ValueError("binary timeline/matrix readback mismatch")
        runtime_model.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(exported_path, runtime_model)
        runtime_materials = args.runtime_root / "assets/materials/original_weapon"
        runtime_materials.mkdir(parents=True, exist_ok=True)
        for source in (png, bmp, material_manifest):
            shutil.copyfile(source, runtime_materials / source.name)
        # Reference mesh is a diagnostic only; M1 consumes the binary above.
        obj_lines = ["# Exact original weapon geometry posed in Aya actor space, sample 0"]
        obj_lines.extend("v " + " ".join(map(str, point)) for point in posed[0])
        obj_lines.extend("vt " + " ".join(str(x / 32768) for x in v["uv_raw"]) for v in vertices)
        obj_lines.extend(f"f {i+1}/{i+1} {i+2}/{i+2} {i+3}/{i+3}" for i in range(0, 243, 3))
        (args.out / "aya_weapon_actor_reference.obj").write_text("\n".join(obj_lines) + "\n", encoding="utf-8")
        report.update(output=str(exported_path.resolve()), runtime_output=str(runtime_model.resolve()),
                      binary_sha256=sha(content), binary_bytes=len(content), flags=flags,
                      pc_units_per_original_unit=units, reference_floor=floor,
                      actual_body_reference_floor=actual_floor, reference_scale_calibration=calibration,
                      binary_layout_readback_verified=True,
                      reference_bbox_original_units=[posed[0].min(axis=0).tolist(), posed[0].max(axis=0).tolist()])
        report["inputs"]["body_report"] = {"path": str(args.body_report.resolve()), "sha256": sha(args.body_report.read_bytes())}
        report["position_validation"]["max_error_pc_units"] = max(max_errors) * units
    report_path = args.out / "weapon.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: report[k] for k in ("schema", "samples", "vertices", "analysis_only", "position_validation", "source15_candidate_only")}, ensure_ascii=False))
    return report


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--metadata", type=Path, required=True)
    ap.add_argument("--manifest", type=Path, required=True)
    ap.add_argument("--timing", type=Path, required=True)
    ap.add_argument("--body-report", type=Path)
    ap.add_argument("--runtime-root", type=Path)
    ap.add_argument("--output-model", type=Path, default=Path("assets/models/aya_source_weapon.bin"),
                    help="runtime-root-relative destination; original reference path remains the default")
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--analysis-only", action="store_true")
    args = ap.parse_args(argv)
    if not args.analysis_only and (args.body_report is None or args.runtime_root is None):
        ap.error("--body-report and --runtime-root are required for final binary export")
    recover(args)


if __name__ == "__main__":
    main()
