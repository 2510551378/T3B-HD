"""Export geometry-verified dense WORLD samples without fitting a hand/socket.

Only a new clip is written. The canonical weapon's geometry, folded source
weights, UVs, normals and material are validated and copied byte for byte.
At least two independently replayed GE captures must exactly match dense source
palettes plus body/weapon WORLD before any runtime output is produced.
"""
import argparse
import copy
import hashlib
import json
import struct
from pathlib import Path

import numpy as np

from exact_aya_materials import decode_texture, iter_material_draws, material_parameters
from export_aya_actual_weapon import (WEAPON_SHA, affine, matrix_draws, sample_times,
                                     validate_body_capture)
from export_aya_source_skin import decode_ge, resolve_output_model
from extract_runtime_character import read_ppdmp


GEOMETRY_END = 76 + 24300
XYZ_INDICES = [0, 1, 2, 4, 5, 6, 8, 9, 10, 12, 13, 14]


def sha(data):
    return hashlib.sha256(data).hexdigest()


def load(path):
    return json.loads(path.read_text(encoding="utf-8"))


def identity(path):
    return {"path": str(path.resolve()), "sha256": sha(path.read_bytes())}


def verified_file(record, field="path"):
    path = Path(record[field])
    if sha(path.read_bytes()) != record["sha256"]:
        raise ValueError(f"evidence file SHA256 changed: {path}")
    return path


def read_skin(data):
    if len(data) < 56:
        raise ValueError("truncated skin header")
    h = struct.unpack_from("<8s8I4f", data)
    if h[0] != b"T3BSKN2\0" or h[1] != 2 or not h[7] & 1:
        raise ValueError("requires timed T3BSKN2 asset")
    bones, packets, vertices, frames = h[2:6]
    if not 1 <= bones <= 64 or not 1 <= packets or not 1 <= vertices or frames < 2:
        raise ValueError("invalid skin counts")
    start = 56 + bones * 4 + packets * 16
    geometry_end = start + vertices * 100
    expected = geometry_end + frames * 4 + frames * bones * 48
    if len(data) != expected:
        raise ValueError("skin binary length disagrees with counts")
    times = np.frombuffer(data, dtype="<f4", count=frames, offset=geometry_end)
    matrices = np.frombuffer(data, dtype="<f4", offset=geometry_end + frames * 4).reshape(frames, bones, 3, 4)
    if not np.all(np.isfinite(times)) or np.any(np.diff(times) <= 0) or not np.all(np.isfinite(matrices)):
        raise ValueError("invalid skin timeline or matrices")
    return h, start, geometry_end, times, matrices


def reference_weapon(report_path):
    report = load(report_path)
    if report["geometry_sha256"] != WEAPON_SHA or report.get("analysis_only"):
        raise ValueError("reference weapon report is not the independently verified original mesh")
    binary_path = Path(report["runtime_output"])
    data = binary_path.read_bytes()
    if sha(data) != report["binary_sha256"]:
        raise ValueError("canonical weapon binary SHA256 changed")
    header, start, geometry_end, _, _ = read_skin(data)
    if header[2:5] != (1, 1, 243) or header[6] != 1 or start != 76 or geometry_end != GEOMETRY_END:
        raise ValueError("canonical weapon layout changed")
    if struct.unpack_from("<i4I", data, 56) != (-1, 0, 243, 0, 3):
        raise ValueError("canonical weapon parent/packet layout changed")
    source = report["source_vertices"]
    if len(source) != 243:
        raise ValueError("canonical source vertex count changed")
    raw = b"".join(bytes.fromhex(v["source_vertex_hex"]) for v in source)
    if len(raw) != 3888 or sha(struct.pack("<I", 0x522) + raw) != WEAPON_SHA or sha(raw) != report["vertex_bytes_sha256"]:
        raise ValueError("canonical raw weapon geometry identity changed")
    for i, v in enumerate(source):
        if v["weight_raw"] != 32767 or v["weight"] != 32767 / 32768:
            raise ValueError("canonical original weapon source weight changed")
        packed = struct.unpack_from("<8fI8I8f", data, start + i * 100)
        expected = [x / 32768 * v["weight"] for x in v["position_raw"]]
        expected += [x / 32768 for x in v["uv_raw"]] + [x / 128 for x in v["normal_raw"]]
        if not np.array_equal(np.asarray(packed[:8], dtype="<f4"), np.asarray(expected, dtype="<f4")):
            raise ValueError("canonical packed position/UV/normal differs from original geometry")
        if packed[8] != 1 or any(packed[9:17]) or packed[17] != 1 or any(packed[18:25]):
            raise ValueError("canonical virtual influence differs from weight-fold contract")
    for extension in ("png", "bmp"):
        path = Path(report["material"][extension])
        if sha(path.read_bytes()) != report["material"][extension + "_sha256"]:
            raise ValueError("canonical weapon material file changed")
    expected_flags = 1 | (2 if report["material"]["parameters"]["color_double"] else 0)
    expected_flags |= 4 if report["material"]["parameters"]["alpha_blend_enabled"] else 0
    expected_flags |= 8 if report["material"]["parameters"]["alpha_test_enabled"] else 0
    if header[7] != expected_flags:
        raise ValueError("canonical weapon material/header flags differ")
    return report, binary_path, data, raw


def validate_alignment_source(manifest):
    alignment = manifest.get("geAlignment")
    if alignment is None or len(alignment.get("matches", [])) < 2:
        raise ValueError("requires at least two exact aligned GE endpoints")
    path = verified_file({"path": alignment["source_manifest"], "sha256": alignment["source_sha256"]})
    original = load(path)
    if len(original["frames"]) != len(manifest["frames"]):
        raise ValueError("aligned/runtime manifest sample counts differ")
    for key in original:
        if key != "frames" and original[key] != manifest.get(key):
            raise ValueError(f"aligned/runtime manifest differs outside dump assignment: {key}")
    for a, b in zip(original["frames"], manifest["frames"]):
        a, b = copy.deepcopy(a), copy.deepcopy(b)
        a.pop("dump", None)
        b.pop("dump", None)
        if a != b:
            raise ValueError("aligned manifest changed runtime sample data")
    matches = alignment["matches"]
    if len({row["actual_source_sample"] for row in matches}) != len(matches):
        raise ValueError("GE endpoints do not identify distinct samples")
    if len({Path(row["dump"]).resolve() for row in matches}) != len(matches):
        raise ValueError("GE endpoints reuse the same dump")
    return path


def world_payload(words):
    if len(words) != 16 or any(not isinstance(x, int) or not 0 <= x <= 0xffffffff for x in words):
        raise ValueError("WORLD source must contain sixteen u32 F32 words")
    floats = np.asarray(words, dtype="<u4").view("<f4")
    if not np.all(np.isfinite(floats)) or not np.array_equal(floats[[3, 7, 11, 15]], [0, 0, 0, 1]):
        raise ValueError("WORLD source is not a finite column-major affine F32 matrix")
    return [(words[index] >> 8) & 0xffffff for index in XYZ_INDICES]


def validate_world_sample(frame, binding, manifest_dir):
    world = frame["worldSource"]
    geometry = world["weaponIdentity"]
    if geometry["geometry_sha256"] != WEAPON_SHA:
        raise ValueError("dense sample weapon geometry SHA256 differs")
    if (world["caller"] != binding["caller"] or world["uploader"] != binding["world_uploader"]
            or frame["object"] != binding["aya_object"] or world["weaponObject"] != binding["weapon_object"]
            or geometry["object"] != world["weaponObject"]
            or world["weaponMatrixPointer"] != world["weaponObject"] + binding["object_matrix_offset"]):
        raise ValueError("dense WORLD callsite/object binding differs from verified contract")
    if any(not isinstance(geometry[k], int) or geometry[k] <= 0 or geometry[k] & 3 for k in ("metadata", "drawTable")):
        raise ValueError("dense weapon metadata/draw-table identity is invalid")
    for actor in ("body", "weapon"):
        if world_payload(world[actor + "Words"]) != world[actor + "Payload"]:
            raise ValueError(f"{actor} F32 to GE float24 payload recomputation differs")
    records = {r["index"]: r["matrix"] for r in frame["records"]}
    if set(records) != set(range(44)) or len(frame["records"]) != 44:
        raise ValueError("dense sample does not contain exactly 44 source records")
    block = frame["sourceBlock"]
    source_path = manifest_dir / Path(block["file"]).name
    data = source_path.read_bytes()
    if len(data) != 44 * 0x130 or block["bytes"] != len(data):
        raise ValueError("dense original source block size differs")
    for index in range(44):
        original = list(struct.unpack_from("<12I", data, index * 0x130 + 0xc0))
        if original != records[index]:
            raise ValueError("dense source block and JSON palette words differ")
    return {"file": str(source_path.resolve()), "sha256": sha(data)}


def captured_weapon_bone(frame, manifest_dir):
    """Read the actual selected weapon source; legacy captures explicitly return None."""
    world = frame["worldSource"]
    geometry = world["weaponIdentity"]
    source = world.get("weaponBoneSource")
    if source is None:
        if "boneCount" in geometry or "sourceIndex" in geometry:
            raise ValueError("weapon metadata selection was recorded but its source record is missing")
        return None
    if geometry.get("boneCount") != 3 or geometry.get("sourceIndex") != 0 or source["index"] != geometry["sourceIndex"]:
        raise ValueError("selected weapon source does not match verified three-bone metadata palette0 -> source0")
    if (not isinstance(source["base"], int) or source["base"] <= 0 or source["base"] & 3
            or source["address"] != source["base"] + source["index"] * 0x130):
        raise ValueError("weapon source address/stride disagrees with selected metadata index")
    path = manifest_dir / Path(source["file"]).name
    raw = path.read_bytes()
    if len(raw) != 0x130 or source["bytes"] != len(raw):
        raise ValueError("weapon source record must contain exactly 0x130 bytes")
    words = list(struct.unpack_from("<12I", raw, 0xc0))
    if any(word >> 24 != 0x2b for word in words):
        raise ValueError("weapon source +0xc0 is not a complete original GE BONE command block")
    payload = [word & 0xffffff for word in words]
    if payload != source["payload"]:
        raise ValueError("weapon raw +0xc0 words and captured payload differ")
    matrix = affine(payload)
    if not np.all(np.isfinite(matrix)) or np.any(matrix[:3, 3] != 0):
        raise ValueError("selected weapon bone violates finite/zero-translation weight-fold contract")
    skeleton_proof = None
    skeleton = world.get("weaponSkeletonSource")
    if skeleton is not None:
        full_path = manifest_dir / Path(skeleton["file"]).name
        full = full_path.read_bytes()
        if (skeleton["base"] != source["base"] or skeleton["bytes"] != len(full)
                or skeleton.get("boneCount") != geometry["boneCount"]
                or len(full) != geometry["boneCount"] * 0x130
                or full[source["index"] * 0x130:(source["index"] + 1) * 0x130] != raw):
            raise ValueError("complete weapon skeleton block disagrees with selected source record")
        skeleton_proof = identity(full_path)
    return {"file": str(path.resolve()), "sha256": sha(raw), "base": source["base"],
            "address": source["address"], "index": source["index"], "metadata_bone_count": geometry["boneCount"],
            "payload": payload, "parent_record_pointer": struct.unpack_from("<I", raw, 0x124)[0],
            "matrix_40_f32_words": list(struct.unpack_from("<16I", raw, 0x40)),
            "matrix_80_f32_words": list(struct.unpack_from("<16I", raw, 0x80)),
            "full_skeleton_block": skeleton_proof}


def analyze_weapon_metadata(path, frames, canonical, units):
    """Describe numeric hierarchy/geometry evidence without naming source1/2 sockets."""
    snapshot = load(path)
    first = frames[0]["worldSource"]
    if (snapshot.get("schema") != "original-actor-metadata-snapshot/v1" or snapshot["boneCount"] != 3
            or snapshot["object"] != first["weaponObject"] or snapshot["metadata"] != first["weaponIdentity"]["metadata"]
            or snapshot["sourceBase"] != first["weaponBoneSource"]["base"]):
        raise ValueError("weapon metadata snapshot identity differs from the captured three-bone actor")
    header = snapshot["header"]
    if (len(header) != 16 or header[1] >> 16 != 3 or header[6] != snapshot["descriptors"]
            or header[13] != snapshot["drawTable"] or snapshot["drawTable"] != first["weaponIdentity"]["drawTable"]):
        raise ValueError("weapon metadata header count/table pointers disagree")
    descriptors = struct.pack("<12I", *snapshot["descriptorWords"])
    descriptor_rows = [list(struct.unpack_from("<8h", descriptors, i * 16)) for i in range(3)]
    draw = struct.pack(f"<{len(snapshot['drawWords'])}I", *snapshot["drawWords"])
    count = struct.unpack_from("<H", draw)[0]
    vertices, _ = struct.unpack_from("<Hh", draw, 4)
    updates, halfwords = draw[9], draw[10]
    vtype = struct.unpack_from("<I", draw, 12)[0]
    palette = [list(struct.unpack_from("<hh", draw, 16 + i * 4)) for i in range(updates)]
    start = 16 + updates * 4
    vertex_bytes = draw[start:start + vertices * halfwords * 2]
    if count != 1 or vertices != 243 or vtype != 0x522 or palette != [[0, 0]] or sha(struct.pack("<I", vtype) + vertex_bytes) != WEAPON_SHA:
        raise ValueError("weapon snapshot draw/palette/geometry does not match the original source0-only mesh")
    records = {r["index"]: r["words"] for r in snapshot["records"]}
    if set(records) != {0, 1, 2}:
        raise ValueError("weapon metadata snapshot lacks all three source records")
    scale = struct.unpack("<f", struct.pack("<I", header[15]))[0]
    bone0 = affine([word & 0xffffff for word in records[0][48:60]])
    tip_raw = np.asarray(canonical["geometry_measurements"]["muzzle_geometry_candidate"]["runtime_local_position"])
    tip = bone0[:3, :3] @ tip_raw + bone0[:3, 3]
    forward = bone0[:3, :3] @ np.asarray([-1., 0., 0.])
    forward /= np.linalg.norm(forward)
    facts = []
    full_blocks = []
    for frame in frames:
        source = frame["worldSource"].get("weaponSkeletonSource")
        if source is not None:
            full_blocks.append((frame, (path.parent / Path(source["file"]).name).read_bytes()))
    pointer_checks = 0
    for index in range(3):
        parent = descriptor_rows[index][7]
        if parent < -1 or parent >= 3 or parent == index:
            raise ValueError("invalid original weapon parent index")
        expected_parent = 0 if parent == -1 else snapshot["sourceBase"] + parent * 0x130
        raw = struct.pack("<76I", *records[index])
        if struct.unpack_from("<I", raw, 0x124)[0] != expected_parent:
            raise ValueError("weapon descriptor parent differs from runtime parent pointer")
        a = np.asarray(records[index][16:32], dtype="<u4").view("<f4").reshape(4, 4, order="F")
        b = np.asarray(records[index][32:48], dtype="<u4").view("<f4").reshape(4, 4, order="F")
        offset = a[:3, 3].astype(np.float64) - tip
        z = a[:3, 2].astype(np.float64)
        z /= np.linalg.norm(z)
        matrices, payloads, origins = [], [], []
        for frame, full in full_blocks:
            if len(full) != 3 * 0x130:
                raise ValueError("full weapon skeleton record count differs")
            record = full[index * 0x130:(index + 1) * 0x130]
            # Allocations may change between captures, but each sample must retain its own hierarchy.
            base = frame["worldSource"]["weaponSkeletonSource"]["base"]
            wanted = 0 if parent == -1 else base + parent * 0x130
            if struct.unpack_from("<I", record, 0x124)[0] != wanted:
                raise ValueError("dense weapon parent pointer differs from original descriptor hierarchy")
            pointer_checks += 1
            matrices.append(record[0x40:0x80])
            payloads.append(record[0xc0:0xf0])
            origins.append(np.asarray(struct.unpack_from("<16f", record, 0x40)).reshape(4, 4, order="F")[:3, 3])
        facts.append({"source_index": index, "descriptor_raw_s16": descriptor_rows[index], "parent_index": parent,
                      "parent_record_pointer": expected_parent, "matrix_40_f32": a.tolist(), "matrix_80_f32": b.tolist(),
                      "skin_payload_float24": [word & 0xffffff for word in records[index][48:60]],
                      "matrix_40_origin_model_units": a[:3, 3].tolist(), "matrix_40_local_positive_z": z.tolist(),
                      "origin_distance_to_geometry_tip_model_units": float(np.linalg.norm(offset)),
                      "origin_distance_to_geometry_tip_pc_units": float(np.linalg.norm(offset)) * units,
                      "tip_plane_signed_axial_distance_model_units": float(offset @ forward),
                      "tip_center_radial_distance_model_units": float(np.linalg.norm(offset - (offset @ forward) * forward)),
                      "positive_z_dot_geometry_barrel_forward": float(z @ forward),
                      "dense_unique_matrix_40": len(set(matrices)), "dense_unique_skin_payload": len(set(payloads)),
                      "dense_matrix_40_origin_bbox": None if not origins else [np.min(origins, axis=0).tolist(), np.max(origins, axis=0).tolist()],
                      "semantic_name": None})
    return {"snapshot": identity(path), "bone_count": 3, "metadata_scale_raw_f32": scale,
            "metadata_header_low16_at_4_raw": header[1] & 0xffff, "parents": [row[7] for row in descriptor_rows],
            "draw_palette_source_mapping": palette, "weighted_sources": [0], "unweighted_sources": [1, 2],
            "geometry_tip_model_units": tip.tolist(), "dense_parent_pointer_checks": pointer_checks,
            "full_skeleton_samples": len(full_blocks), "bones": facts,
            "limits": ["Spatial agreement and local axes do not establish an original muzzle/grip/socket consumer.",
                       "Node origins use record+0x40; bind-compensated skin payload origins must not be substituted.",
                       "No independent grip landmark is verified here, so no source is named a grip.",
                       "Supplied header/descriptor snapshots contain numeric fields and pointers; no original name string or semantic flag mapping has been recovered."]}


def endpoint_check(frame, capture, metadata, canonical, raw_geometry):
    commands, push = read_ppdmp(str(capture))
    packets = {p["vertex_sha256"]: p for p in metadata["packets"]}
    draws = list(matrix_draws(commands, push))
    body = [d for d in draws if d["sha256"] in packets]
    weapon = [d for d in draws if d["sha256"] == WEAPON_SHA]
    if len(body) != 106 or len({d["sha256"] for d in body}) != 106 or len(weapon) != 1:
        raise ValueError("endpoint GE lacks complete unique Aya/weapon geometry")
    gun = weapon[0]
    w = frame["worldSource"]
    if any(draw["world"] != w["bodyPayload"] for draw in body) or gun["world"] != w["weaponPayload"]:
        raise ValueError("endpoint GE body/weapon WORLD does not exactly match dense sample")
    if any(draw["view"] != gun["view"] or None in draw["view"] for draw in body):
        raise ValueError("endpoint body/weapon VIEW differs or is incomplete")
    source = {r["index"]: [word & 0xffffff for word in r["matrix"]] for r in frame["records"]}
    checks = 0
    for draw in body:
        packet = packets[draw["sha256"]]
        if draw["primitive"] != 3 or draw["count"] != packet["vertex_count"]:
            raise ValueError("endpoint Aya primitive/count mismatch")
        for slot in packet["active_palette_indices"]:
            if draw["bones"][slot * 12:slot * 12 + 12] != source[packet["palette_state"][str(slot)]]:
                raise ValueError("endpoint GE palette differs from exact dense source index")
            checks += 1
    if gun["primitive"] != 3 or gun["count"] != 243 or gun["vtype"] != 0x522:
        raise ValueError("endpoint original weapon primitive/count/VTYPE differs")
    if push[gun["pointer"]:gun["pointer"] + gun["size"]] != raw_geometry:
        raise ValueError("endpoint raw weapon vertices differ from canonical original bytes")
    bone_words = gun["bones"][:12]
    if None in bone_words:
        raise ValueError("endpoint weapon bone0 lacks explicit complete GE writes")
    bone = affine(bone_words)
    expected = np.eye(4)
    expected[:3, :3] *= 59.2998046875
    if not np.array_equal(bone, expected):
        raise ValueError("endpoint weapon bone must equal 59.2998046875 I with zero translation")
    captured_bone = captured_weapon_bone(frame, capture.parent)
    if captured_bone is not None and captured_bone["payload"] != bone_words:
        raise ValueError("endpoint GE weapon bone differs from the actual captured selected weapon source")
    for reference_frame in canonical["frames"]:
        if reference_frame["weapon_bone_float24"] != bone_words:
            raise ValueError("endpoint weapon bone differs from independently verified canonical weapon")
    materials = [d for d in iter_material_draws(commands, push)
                 if d["vertices"]["record"] == gun["vertex_record"]
                 and d["register_record"] == gun["register_record"] and d["register_word"] == gun["register_word"]]
    if len(materials) != 1:
        raise ValueError("endpoint weapon material PRIM cannot be uniquely replayed")
    material = materials[0]
    texture = material["texture0"]
    if texture is None or texture["framebuffer"]:
        raise ValueError("endpoint weapon texture backing is unresolved")
    rgba, facts = decode_texture(texture["raw"], material["registers"], material["clut"], material["clut_known"])
    for key in ("width", "height", "buffer_width", "format_id", "swizzled", "clut_format_id", "clut_shift", "clut_mask", "clut_start"):
        if facts[key] != canonical["material"][key]:
            raise ValueError(f"endpoint weapon material format/state differs: {key}")
    if (texture["sha256"] != canonical["material"]["texture_sha256"]
            or sha(material["clut"][:1024]) != canonical["material"]["clut_sha256"]
            or facts["rgba_sha256"] != canonical["material"]["rgba_sha256"]
            or material_parameters(material["registers"]) != canonical["material"]["parameters"]):
        raise ValueError("endpoint weapon material differs from canonical original material")
    return gun, {"frame": frame["frame"], "capture": identity(capture),
                 "exact_body_packets": 106, "exact_active_palette_references": checks,
                 "body_world_exact_components": 12, "weapon_world_exact_components": 12,
                 "body_weapon_view_equal": True, "weapon_bone_float24": bone_words,
                 "geometry_sha256": WEAPON_SHA, "weapon_vertex_record": gun["vertex_record"],
                 "texture_sha256": texture["sha256"], "rgba_sha256": sha(rgba)}


def positions_original(source, body_world, weapon_world, bone):
    positions = np.asarray([v["position_raw"] for v in source], dtype=np.float64) / 32768
    weights = np.asarray([v["weight"] for v in source], dtype=np.float64)
    weighted = (positions @ bone[:3, :3].T + bone[:3, 3]) * weights[:, None]
    world = weighted @ weapon_world[:3, :3].T + weapon_world[:3, 3]
    inverse = np.linalg.inv(body_world)
    return world @ inverse[:3, :3].T + inverse[:3, 3]


def recover(args):
    manifest, metadata, timing, body = load(args.manifest), load(args.metadata), load(args.timing), load(args.body_report)
    times = sample_times(manifest["frames"], timing)
    units, floor, actual_floor, calibration = validate_body_capture(body, args.metadata, args.manifest, args.timing, manifest["frames"], times)
    source_manifest_path = validate_alignment_source(manifest)
    binding_path = verified_file(manifest["worldSourceBinding"], "file")
    binding = load(binding_path)
    if (binding.get("passed") is not True or binding["weapon_geometry_sha256"] != WEAPON_SHA
            or binding["world_selector"] != 2 or binding["object_matrix_offset"] != 0x220
            or manifest["target"] != binding["caller"] or manifest["condition"] != "a0 == 2"):
        raise ValueError("WORLD source binding/selector/callsite contract is unresolved")
    if binding["inputs"]["metadata"] != identity(args.metadata):
        raise ValueError("WORLD binding metadata identity differs")
    verified_file(binding["inputs"]["trace"])
    canonical, canonical_binary_path, canonical_data, raw_geometry = reference_weapon(args.reference_weapon_report)
    output = resolve_output_model(args.runtime_root, args.output_model)
    local_output = args.out / output.name
    report_path = args.out / "weapon.json"
    if (output.resolve() == canonical_binary_path.resolve() or local_output.resolve() == canonical_binary_path.resolve()
            or report_path.resolve() == args.reference_weapon_report.resolve()):
        raise ValueError("dense export cannot overwrite canonical weapon binary/report")
    body_binary_path = Path(body["output"])
    body_data = body_binary_path.read_bytes()
    if sha(body_data) != body["sha256"]:
        raise ValueError("body clip binary SHA256 changed")
    body_header, _, _, body_times, body_matrices = read_skin(body_data)
    if body_header[2:5] != (44, 106, 3456) or not np.array_equal(body_times, times):
        raise ValueError("body binary geometry counts/times differ from dense capture")
    if body_header[10:12] != (float(np.float32(units)), float(np.float32(floor))):
        raise ValueError("body binary calibrated units/floor differ from its verified report")
    rows = []
    for i, frame in enumerate(manifest["frames"]):
        block_identity = validate_world_sample(frame, binding, args.manifest.parent)
        expected_body = np.asarray([decode_ge(r["matrix"]) for r in sorted(frame["records"], key=lambda r: r["index"])])
        if not np.array_equal(body_matrices[i], expected_body):
            raise ValueError("body binary matrices differ from dense source records")
        rows.append({"frame": frame["frame"], "ticks": frame["ticks"], "source_block": block_identity,
                     "weapon_bone_source": captured_weapon_bone(frame, args.manifest.parent),
                     "geometry_sha256": frame["worldSource"]["weaponIdentity"]["geometry_sha256"],
                     "body_world_float24": frame["worldSource"]["bodyPayload"],
                     "weapon_world_float24": frame["worldSource"]["weaponPayload"]})
    by_frame = {frame["frame"]: frame for frame in manifest["frames"]}
    if len(by_frame) != len(manifest["frames"]):
        raise ValueError("dense frame identifiers are not unique")
    direct_bone = [row["weapon_bone_source"] is not None for row in rows]
    if any(direct_bone) and not all(direct_bone):
        raise ValueError("dense capture mixes actual weapon source records with missing legacy samples")
    endpoint_rows, endpoints = [], {}
    for declared in manifest["geAlignment"]["matches"]:
        frame = by_frame[declared["actual_source_sample"]]
        capture = Path(declared["dump"])
        if frame.get("dump") is None or Path(frame["dump"]["file"]).resolve() != capture.resolve():
            raise ValueError("GE endpoint assignment disagrees with aligned sample dump")
        gun, proof = endpoint_check(frame, capture, metadata, canonical, raw_geometry)
        if declared["exact_active_influences"] != proof["exact_active_palette_references"]:
            raise ValueError("GE alignment declared palette count differs from independent replay")
        endpoints[frame["frame"]] = gun
        endpoint_rows.append(proof)
    for row in rows:
        row["weapon_bone_float24"] = (row["weapon_bone_source"]["payload"] if all(direct_bone)
                                       else endpoint_rows[0]["weapon_bone_float24"])
    transforms = np.asarray([(np.linalg.inv(affine(row["body_world_float24"])) @ affine(row["weapon_world_float24"]) @ affine(row["weapon_bone_float24"]))[:3]
                             for row in rows], dtype="<f4")
    if not np.all(np.isfinite(transforms)):
        raise ValueError("dense relative WORLD transform is not finite")
    count = len(times)
    header = struct.unpack_from("<8s8I4f", canonical_data)
    content = bytearray(struct.pack("<8s8I4f", *header[:5], count, *header[6:10], units, floor, header[12]))
    content.extend(canonical_data[56:GEOMETRY_END])
    content.extend(times.tobytes())
    content.extend(transforms[:, None].tobytes())
    decoded_header, start, geometry_end, decoded_times, decoded_matrices = read_skin(content)
    if (bytes(content[56:geometry_end]) != canonical_data[56:GEOMETRY_END]
            or decoded_header[5] != count or not np.array_equal(decoded_times, times)
            or not np.array_equal(decoded_matrices[:, 0], transforms)):
        raise ValueError("independent dense binary readback differs from canonical geometry/timeline/matrices")
    packed_positions = np.asarray([struct.unpack_from("<3f", content, start + i * 100) for i in range(243)], dtype="<f4")
    errors = []
    endpoint_by_frame = {row["frame"]: row for row in endpoint_rows}
    for i, row in enumerate(rows):
        expected = positions_original(canonical["source_vertices"], affine(row["body_world_float24"]), affine(row["weapon_world_float24"]), affine(row["weapon_bone_float24"]))
        matrix = decoded_matrices[i, 0]
        observed = packed_positions @ matrix[:, :3].T + matrix[:, 3]
        error = float(np.linalg.norm(expected - observed, axis=1).max())
        errors.append(error)
        if error >= 0.0001:
            raise ValueError("dense weapon float32 readback pose error exceeds 1e-4 original units")
        if row["frame"] in endpoints:
            gun = endpoints[row["frame"]]
            ge_expected = positions_original(canonical["source_vertices"], affine(row["body_world_float24"]), affine(gun["world"]), affine(gun["bones"][:12]))
            endpoint_error = float(np.linalg.norm(ge_expected - observed, axis=1).max())
            if endpoint_error >= 0.0001:
                raise ValueError("dense weapon differs from independent endpoint GE vertices")
            endpoint_by_frame[row["frame"]]["max_vertex_error_original_units"] = endpoint_error
    report = {"schema": "aya-dense-world-weapon-export/v1", "output": str(local_output.resolve()),
              "runtime_output": str(output), "binary_sha256": sha(content), "binary_bytes": len(content),
              "geometry_sha256": WEAPON_SHA, "vertex_bytes_sha256": canonical["vertex_bytes_sha256"],
              "geometry_payload_sha256": sha(content[56:GEOMETRY_END]), "canonical_geometry_bytes_preserved": True,
              "geometry_measurements": canonical["geometry_measurements"], "source_vertices": canonical["source_vertices"],
              "material": canonical["material"], "weight_preservation": canonical["weight_preservation"],
              "packets": 1, "vertices": 243, "triangles": 81, "virtual_bones": 1,
              "samples": count, "sample_times_seconds": times.tolist(), "saved_cpu_hz": timing["cpu_hz"],
              "flags": header[7], "pc_units_per_original_unit": units, "reference_floor": floor,
              "actual_body_reference_floor": actual_floor, "reference_scale_calibration": calibration,
              "weapon_bone_observation": {"mode": "actual_selected_source_every_sample" if all(direct_bone) else "legacy_endpoint_constant_reuse",
                                          "actual_record_samples": sum(direct_bone), "total_samples": count,
                                          "selected_source_indices": sorted({row["weapon_bone_source"]["index"] for row in rows if row["weapon_bone_source"] is not None}),
                                          "unique_bone_payloads": len({tuple(row["weapon_bone_float24"]) for row in rows})},
              "binary_layout_readback_verified": True, "frames": rows, "exact_ge_endpoints": endpoint_rows,
              "position_validation": {"max_error_by_frame_original_units": errors, "max_error_original_units": max(errors),
                                      "max_error_pc_units": max(errors) * units, "tolerance_original_units": 0.0001},
              "inputs": {name: identity(path) for name, path in [("metadata", args.metadata), ("manifest", args.manifest),
                         ("timing", args.timing), ("body_report", args.body_report), ("reference_weapon_report", args.reference_weapon_report),
                         ("canonical_weapon_binary", canonical_binary_path), ("binding", binding_path), ("runtime_source_manifest", source_manifest_path)]},
              "limitations": ["Input-held samples can include nearby melee/damage/action transitions; this is not certified as a pure fire/recoil clip.",
                              "Every sample has geometry-verified runtime WORLD and exact source bytes; only the listed GE endpoints have independent full GE cross-checks.",
                              ("Weapon bone is read directly from the metadata-selected original source record at every sample; source1/2 semantics remain unassigned."
                               if all(direct_bone) else "Legacy capture: weapon bone is constant in canonical captures and listed GE endpoints; intermediate samples reuse that observed constant."),
                              "No source15 fitting, anatomical socket assignment, recovered original muzzle datum or runtime clip activation is performed.",
                              "Saved CPU frequency is verified at save time; unrecorded later clock changes remain an input limitation."]}
    snapshot_path = args.manifest.parent / "weapon_metadata_snapshot.json"
    if snapshot_path.is_file():
        report["weapon_metadata_analysis"] = analyze_weapon_metadata(snapshot_path, manifest["frames"], canonical, units)
    args.out.mkdir(parents=True, exist_ok=True)
    output.parent.mkdir(parents=True, exist_ok=True)
    local_output.write_bytes(content)
    output.write_bytes(content)
    if output.read_bytes() != bytes(content) or local_output.read_bytes() != bytes(content):
        raise ValueError("written dense weapon binary differs from validated readback")
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"runtime_output": str(output), "binary_sha256": report["binary_sha256"],
                      "samples": count, "binary_bytes": len(content), "max_position_error_original_units": max(errors),
                      "exact_ge_endpoints": [{"frame": e["frame"], "max_vertex_error_original_units": e["max_vertex_error_original_units"]}
                                             for e in endpoint_rows]}, ensure_ascii=False))
    return report


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    for name in ("manifest", "metadata", "timing", "body-report", "reference-weapon-report", "runtime-root", "output-model", "out"):
        ap.add_argument("--" + name, type=Path, required=True)
    return recover(ap.parse_args(argv))


if __name__ == "__main__":
    main()
