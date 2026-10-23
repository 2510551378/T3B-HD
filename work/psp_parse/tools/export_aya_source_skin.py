"""Export original source-index skinning to the PC runtime, without region rigs.

T3BSKN2: 8-byte magic; 8*u32; 4*f32; parents (i32); draw records
(first,count,material,primitive:4*u32); vertices (8*f32,u32,8*u32,8*f32);
sample times (f32); affine matrices (frame,bone,row,column: f32[3][4]).
All integers/floats are little endian. No matrix translation is discarded.
"""
import argparse
import hashlib
import json
import shutil
import struct
from pathlib import Path
import numpy as np
from extract_ge_timeline import float24


def decode_ge(words):
    return np.asarray([float24(x) for x in words], dtype=np.float32).reshape(3, 4, order="F")


def pose_vertices(vertices, matrices):
    result = []
    for vertex in vertices:
        point = np.asarray(vertex["position_raw"], dtype=np.float32) / np.float32(32768)
        transformed = np.zeros(3, dtype=np.float32)
        for index, weight in vertex["influences"]:
            transformed += np.float32(weight) * (matrices[index, :, :3] @ point + matrices[index, :, 3])
        result.append(transformed)
    return np.asarray(result)


def resolve_output_model(runtime_root, output_model):
    """Keep an independently named clip inside the requested runtime checkout."""
    root = runtime_root.resolve()
    relative = Path(output_model)
    if relative.is_absolute() or relative.drive or not relative.name:
        raise ValueError("--output-model must be a runtime-root-relative file path")
    output = (root / relative).resolve()
    if output == root or not output.is_relative_to(root):
        raise ValueError("--output-model escapes runtime-root")
    return output


def reference_obj_path(runtime_root, output, explicit=None):
    if explicit is not None:
        path = Path(explicit)
        return path.resolve() if path.is_absolute() else resolve_output_model(runtime_root, path)
    if output == (runtime_root.resolve() / "assets/models/aya_source_skin.bin"):
        return output.with_name("aya_source_reference.obj")
    return output.with_name(output.stem + "_reference.obj")


def scene_conversion(metadata, reference):
    # Explicit PC scene sizing; this is not a claim about PSP physical units.
    bind_words = metadata["bones"][0]["matrix_80_words"]
    bind_scale = struct.unpack("<f", struct.pack("<I", bind_words[0]))[0]
    if not np.isfinite(bind_scale) or bind_scale <= 0:
        raise ValueError("invalid original bind scale")
    return 1.84 / bind_scale, float(reference[:, 1].min())


def calibrated_scene_conversion(metadata_path, actual_units, actual_floor, reference_report=None):
    if reference_report is None:
        return actual_units, actual_floor, None
    calibration = json.loads(reference_report.read_text(encoding="utf-8"))
    identity = calibration["inputs"]["metadata"]
    if identity["sha256"] != hashlib.sha256(metadata_path.read_bytes()).hexdigest():
        raise ValueError("reference scale report uses different Aya geometry metadata")
    units, floor = calibration["pc_units_per_original_unit"], calibration["reference_floor"]
    if not np.isfinite(units) or not np.isfinite(floor) or units != actual_units:
        raise ValueError("reference scale report has incompatible units or nonfinite floor")
    evidence = {"path": str(reference_report.resolve()), "sha256": hashlib.sha256(reference_report.read_bytes()).hexdigest(),
                "pc_units_per_original_unit": units, "reference_floor": floor,
                "actual_clip_reference_floor": actual_floor, "reference_model": calibration.get("output")}
    return units, floor, evidence


def validate_matrix_convention(snapshot):
    snap = json.loads(snapshot.read_text(encoding="utf-8"))
    if snap.get("boneIndex") != 43:
        raise ValueError("matrix convention check needs a completed bone-43 pass")
    exact = 0
    max_steps = 0
    max_error = 0.0
    for row in snap["records"]:
        words = row["words"]
        a = np.asarray(struct.unpack("<16f", struct.pack("<16I", *words[16:32])), dtype=np.float32).reshape(4, 4, order="F")
        b = np.asarray(struct.unpack("<16f", struct.pack("<16I", *words[32:48])), dtype=np.float32).reshape(4, 4, order="F")
        product = (a @ b)[:3, :].flatten(order="F").astype("<f4")
        packed = product.view("<u4") >> 8
        actual = np.asarray(words[48:60], dtype=np.uint32) & 0xffffff
        exact += int(np.sum(packed == actual))
        steps = int(np.abs(packed.astype(np.int64) - actual.astype(np.int64)).max())
        max_steps = max(max_steps, steps)
        max_error = max(max_error, float(np.abs(product - decode_ge(words[48:60]).flatten(order="F")).max()))
        if steps > 1:
            raise ValueError(f"bone {row['index']} violates column-major A40*B80 -> GE within one float24 step")
    return {"snapshot": str(snapshot.resolve()), "snapshot_sha256": hashlib.sha256(snapshot.read_bytes()).hexdigest(),
            "exact_float24_components": exact, "total_components": 44 * 12, "max_float24_steps": max_steps,
            "max_float_error": max_error, "convention": "GE column-major 3x4 = record40(column-major4x4) * record80(column-major4x4)"}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--metadata", type=Path, required=True)
    ap.add_argument("--manifest", type=Path, required=True)
    ap.add_argument("--timing", type=Path, required=True)
    ap.add_argument("--completed-snapshot", type=Path, required=True)
    ap.add_argument("--materials", type=Path, required=True)
    ap.add_argument("--runtime-root", type=Path, required=True)
    ap.add_argument("--output-model", type=Path, default=Path("assets/models/aya_source_skin.bin"),
                    help="runtime-root-relative model path; custom clip exports leave the reference model intact")
    ap.add_argument("--reference-obj", type=Path,
                    help="optional absolute or runtime-root-relative diagnostic OBJ; custom model defaults to same stem")
    ap.add_argument("--reference-scale-report", type=Path,
                    help="reuse canonical scene units/floor while retaining this clip's actual pose floor/bbox in the report")
    ap.add_argument("--report", type=Path, required=True)
    a = ap.parse_args(argv)
    output = resolve_output_model(a.runtime_root, a.output_model)
    obj_path = reference_obj_path(a.runtime_root, output, a.reference_obj)
    if a.reference_scale_report is not None and a.reference_scale_report.resolve() == a.report.resolve():
        raise ValueError("clip report must not overwrite its canonical reference scale report")
    metadata = json.loads(a.metadata.read_text(encoding="utf-8"))
    manifest = json.loads(a.manifest.read_text(encoding="utf-8"))
    timing = json.loads(a.timing.read_text(encoding="utf-8"))
    materials = json.loads(a.materials.read_text(encoding="utf-8"))
    convention = validate_matrix_convention(a.completed_snapshot)
    packets = metadata["packets"]
    vertices = [v for p in packets for v in p["vertices"]]
    material_by_packet = {p["packet"]: p for p in materials["packets"]}
    if any(len(material_by_packet[p["draw"]]["runtime_material_indices"]) != 1 for p in packets):
        raise ValueError("packet has ambiguous materials")
    frames = manifest["frames"]
    ticks = [frame["ticks"] for frame in frames]
    if len(frames) < 2 or any(y <= x for x, y in zip(ticks, ticks[1:])):
        raise ValueError("timeline must have strictly increasing ticks")
    times = np.asarray([(t - ticks[0]) / timing["cpu_hz"] for t in ticks], dtype="<f4")
    if not np.all(np.isfinite(times)) or np.any(np.diff(times) <= 0):
        raise ValueError("sample times must remain finite and strictly increasing after float32 packing")
    matrices = []
    for frame in frames:
        rows = {r["index"]: r["matrix"] for r in frame["records"]}
        if set(rows) != set(range(44)):
            raise ValueError("source pass does not contain exactly 44 indices")
        matrices.append(np.asarray([decode_ge(rows[i]) for i in range(44)], dtype="<f4"))
    matrices = np.asarray(matrices, dtype="<f4")
    if not np.all(np.isfinite(matrices)):
        raise ValueError("nonfinite source matrices")
    reference = pose_vertices(vertices, matrices[0])
    actual_units, actual_floor = scene_conversion(metadata, reference)
    unit_scale, floor, calibration = calibrated_scene_conversion(a.metadata, actual_units, actual_floor, a.reference_scale_report)
    if calibration is not None and calibration["reference_model"] is not None and Path(calibration["reference_model"]).resolve() == output:
        raise ValueError("calibrated clip output must not overwrite its canonical reference model")
    root = a.runtime_root.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    params = materials["materials"][0]["parameters"]
    flags = 1 | (2 if params["color_double"] else 0) | (4 if params["alpha_blend_enabled"] else 0) | (8 if params["alpha_test_enabled"] else 0)
    content = bytearray(struct.pack("<8s8I4f", b"T3BSKN2\0", 2, 44, len(packets), len(vertices), len(frames), len(materials["materials"]), flags, 0, 0.0, unit_scale, floor, 0.0))
    content.extend(struct.pack("<44i", *[b["parent"] for b in metadata["bones"]]))
    first = 0
    for packet in packets:
        if packet["vertex_count"] % 3:
            raise ValueError("non-triangle-list packet")
        mat = material_by_packet[packet["draw"]]
        if mat["vertex_sha256"] != packet["vertex_sha256"]:
            raise ValueError("material/geometry identity mismatch")
        content.extend(struct.pack("<4I", first, packet["vertex_count"], mat["runtime_material_indices"][0], 3))
        first += packet["vertex_count"]
    for packet in packets:
        if (packet["vtype"] & 3) != 2 or (packet["vtype"] >> 7) & 3 != 2 or (packet["vtype"] >> 5) & 3 != 1:
            raise ValueError("this verified asset requires UV16, POS16 and normal8")
        for vertex in packet["vertices"]:
            influences = vertex["influences"]
            if not 0 < len(influences) <= 8:
                raise ValueError("invalid influence count")
            pos = [v / 32768 for v in vertex["position_raw"]]
            uv = [v / 32768 for v in vertex["uv_raw"]]
            normal = [v / 128 for v in vertex["normal_raw"]]
            ids = [int(i) for i, w in influences] + [0] * (8 - len(influences))
            weights = [float(w) for i, w in influences] + [0.0] * (8 - len(influences))
            content.extend(struct.pack("<8fI8I8f", *pos, *uv, *normal, len(influences), *ids, *weights))
    content.extend(times.tobytes())
    content.extend(matrices.tobytes())
    output.write_bytes(content)
    mat_dir = root / "assets/materials/original_aya"
    mat_dir.mkdir(parents=True, exist_ok=True)
    for material in materials["materials"]:
        source = Path(material["bmp"])
        shutil.copyfile(source, mat_dir / source.name)
        source = Path(material["png"])
        shutil.copyfile(source, mat_dir / source.name)
    shutil.copyfile(a.materials.parent / "aya_original_materials.txt", mat_dir / "aya_original_materials.txt")
    # Independent inspection asset, already posed exactly once.
    obj_path.parent.mkdir(parents=True, exist_ok=True)
    lines = ["# Original GE source matrices and explicit source-index weights; reference sample"]
    lines += ["v " + " ".join(f"{x:.9g}" for x in p) for p in reference]
    lines += [f"vt {v['uv_raw'][0] / 32768:.9g} {v['uv_raw'][1] / 32768:.9g}" for v in vertices]
    lines += [f"f {i+1}/{i+1} {i+2}/{i+2} {i+3}/{i+3}" for i in range(0, len(vertices), 3)]
    obj_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    report = {"schema": "aya-source-skin-export/v2", "output": str(output), "reference_obj": str(obj_path), "sha256": hashlib.sha256(content).hexdigest(),
              "packets": len(packets), "vertices": len(vertices), "triangles": len(vertices) // 3,
              "bones": 44, "samples": len(frames), "sample_times_seconds": times.tolist(), "saved_cpu_hz": timing["cpu_hz"],
              "matrix_convention_validation": convention, "pc_units_per_original_unit": unit_scale, "reference_floor": floor,
              "actual_reference_floor": actual_floor, "reference_scale_calibration": calibration,
              "reference_bbox_original_units": [reference.min(0).tolist(), reference.max(0).tolist()],
              "materials": len(materials["materials"]), "weights_renormalized": False,
              "limitations": ["Timeline is sparse captured poses, not a recovered full original animation clip.",
                              "Times use save-verified CPU_HZ; subsequent clock changes are not recorded by legacy manifests.",
                              "Matrix interpolation between captured poses is a PC presentation choice.",
                              "Anatomical names and the weapon/muzzle socket remain separate validation tasks."],
              "inputs": {name: {"path": str(p.resolve()), "sha256": hashlib.sha256(p.read_bytes()).hexdigest()} for name, p in
                         [("metadata", a.metadata), ("manifest", a.manifest), ("timing", a.timing), ("materials", a.materials)]}}
    if calibration is not None:
        report["inputs"]["reference_scale_report"] = {"path": calibration["path"], "sha256": calibration["sha256"]}
    a.report.parent.mkdir(parents=True, exist_ok=True)
    a.report.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps({k: report[k] for k in ("output", "packets", "vertices", "triangles", "bones", "samples", "materials")}))


if __name__ == "__main__":
    main()
