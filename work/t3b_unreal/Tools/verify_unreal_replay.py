"""Verify actual UE procedural CPU-world probes after running T3B.Replay.Probe.

Does not accept the standalone source_probe CSV schema as UE execution and
does not certify pixels, materials, collision or playable battle behavior.
"""
import argparse
import csv
import hashlib
import json
from pathlib import Path
import struct
import sys

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2]/"psp_parse/tools"))
from verify_source_skin_runtime import read_binary, binary_pose


def identity(path):
    return {"path": str(path.resolve()), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}


def pc_pose(source, units, floor, spawn):
    p = source.astype(np.float32).copy()
    p[:, 0] *= np.float32(units)
    p[:, 1] = (p[:, 1]-np.float32(floor))*np.float32(units)
    p[:, 2] *= np.float32(units)
    sn, cs = np.sin(np.float32(spawn[2])), np.cos(np.float32(spawn[2]))
    q = p.copy()
    q[:, 0] = np.float32(spawn[0])+p[:, 0]*cs+p[:, 2]*sn
    q[:, 2] = np.float32(spawn[1])-p[:, 0]*sn+p[:, 2]*cs
    return q


def read_probe(path):
    with path.open(encoding="utf-8", newline="") as source:
        reader = csv.DictReader(source)
        names = reader.fieldnames
    required = ["sample", "time", "index", "source_x", "source_y", "source_z", "pc_x", "pc_y", "pc_z",
                "ue_x", "ue_y", "ue_z", "world_x", "world_y", "world_z"]
    if names != required:
        raise ValueError(f"Not an actual UE component world-position probe: {path}")
    rows = np.loadtxt(path, delimiter=",", skiprows=1)
    if rows.ndim != 2 or rows.shape[1] != 15 or not np.isfinite(rows).all():
        raise ValueError("Incomplete/nonfinite UE world probe")
    return rows


def verify(project, tolerance):
    manifest_path = project/"Content/SourceData/manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    probes = project/"Saved/SourceReplay"
    meta_path = probes/"probe_metadata.json"
    if not meta_path.exists():
        raise RuntimeError("No actual UE probe exists. Build/run the project and execute T3B.Replay.Probe first.")
    metadata = json.loads(meta_path.read_text(encoding="utf-8"))
    if metadata.get("schema") != "t3b-ue-procedural-probe/v1" or not metadata.get("all_csv_written") or not metadata.get("run_id"):
        raise ValueError("UE probe metadata is missing, incomplete or from another producer")
    if not metadata.get("engine_version", "").startswith("5.8.") or metadata.get("scope") != "actual_procedural_component_CPU_world_positions":
        raise ValueError("UE engine version/probe scope differs from selected baseline")
    data_root = project/"Content/SourceData"
    scene_path = data_root/manifest["scene"]["binary"]
    scene = scene_path.read_bytes()
    magic, version, draws, vertices, materials = struct.unpack_from("<8s4I", scene)
    if (magic, version) != (b"T3BSCN1\0", 1) or len(scene) != 56+draws*12+vertices*24:
        raise ValueError("Invalid street reference")
    offset = 56+draws*12
    positions = np.asarray([struct.unpack_from("<3f", scene, offset+i*24) for i in range(vertices)], dtype=np.float32)
    expected = positions[:, [2, 0, 1]]*np.float32([100, -100, 100])
    street_probe = probes/"Street_world.csv"
    actual = read_probe(street_probe)
    if len(actual) != vertices or not np.all(actual[:, 0] == 0) or not np.array_equal(actual[:, 2], np.arange(vertices)):
        raise ValueError("UE street probe coverage/order differs")
    error = float(np.abs(actual[:, 12:15]-expected).max())
    if error > tolerance:
        raise ValueError(f"UE street component world-position error: {error}cm")
    results = {"Street": {"vertices": vertices, "max_world_position_error_cm": error,
                           "source": identity(scene_path), "actual_probe": identity(street_probe)}}
    for actor in manifest["actors"]:
        skin_path = data_root/actor["binary"]
        vs, matrices, times = read_binary(skin_path)
        units, floor = struct.unpack_from("<2f", skin_path.read_bytes(), 44)
        actual_path = probes/(actor["name"]+"_world.csv")
        actual = read_probe(actual_path)
        if len(actual) != len(vs)*len(times):
            raise ValueError("UE actor probe must cover every original source sample and vertex")
        source_error = world_error = 0.
        for sample, time in enumerate(times):
            rows = actual[sample*len(vs):(sample+1)*len(vs)]
            if not np.all(rows[:, 0] == sample) or not np.array_equal(rows[:, 2], np.arange(len(vs))) or not np.allclose(rows[:, 1], time, rtol=0, atol=1e-7):
                raise ValueError("UE actor sample/vertex/time identity mismatch")
            original = binary_pose(vs, matrices[sample])
            pc = pc_pose(original, units, floor, actor["spawn"])
            ue = pc[:, [2, 0, 1]]*np.float32([100, -100, 100])
            source_error = max(source_error, float(np.abs(rows[:, 3:6]-original).max()))
            world_error = max(world_error, float(np.abs(rows[:, 12:15]-ue).max()))
        if source_error > .0001 or world_error > tolerance:
            raise ValueError(f"UE actor {actor['name']} differs: source {source_error}, world {world_error}cm")
        results[actor["name"]] = {"samples": len(times), "vertices_per_sample": len(vs),
                                   "max_source_position_error_original_units": source_error,
                                   "max_world_position_error_cm": world_error,
                                   "synchronization_group": actor["synchronization_group"],
                                   "source": identity(skin_path), "actual_probe": identity(actual_path)}
    return {"schema": "t3b-actual-UE-procedural-CPU-verification/v1", "passed": True,
            "scope": "actual procedural component CPU vertex buffer/world positions only",
            "probe_metadata": identity(meta_path), "engine_version": metadata["engine_version"], "run_id": metadata["run_id"],
            "manifest": identity(manifest_path), "tolerance_cm": tolerance, "geometry": results,
            "gpu_pixels_verified": False, "materials_verified": False, "gameplay_verified": False}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--max-world-error-cm", type=float, default=.002)
    args = parser.parse_args()
    if not np.isfinite(args.max_world_error_cm) or args.max_world_error_cm <= 0:
        parser.error("error bound must be finite and positive")
    report = verify(args.project_root, args.max_world_error_cm)
    output = args.project_root/"Validation/actual_ue_cpu_geometry.json"
    output.write_text(json.dumps(report, indent=2)+"\n", encoding="utf-8")
    print(json.dumps(report))
