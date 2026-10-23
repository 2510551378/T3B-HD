"""Independently check the PC static-surface adapter and actual movement probes.

Capsule distance is solved as a constrained convex least-squares problem by
enumerating active constraints, independent of C's closest-region geometry.
"""
import argparse
import csv
import hashlib
import itertools
import json
from pathlib import Path
import shutil
import struct

import numpy as np
from verify_ranged_source_rays import original_scene_collision_mesh
from verify_source_skin_runtime import read_kv


def capsule_distance2(x, z, triangle, radius=.22, height=1.84):
    a, b, c = np.asarray(triangle, dtype=float)
    low = np.array([x, radius, z])
    axis = np.array([0, height-2*radius, 0])
    matrix = np.column_stack((axis, a-b, a-c))
    offset = low-a
    h, linear = matrix.T@matrix, matrix.T@offset
    constraints = [(np.array([1., 0, 0]), 0), (np.array([1., 0, 0]), 1),
                   (np.array([0., 1, 0]), 0), (np.array([0., 0, 1]), 0),
                   (np.array([0., 1, 1]), 1)]
    best = float("inf")
    for n in range(4):
        for selected in itertools.combinations(range(5), n):
            equality = np.array([constraints[i][0] for i in selected]).reshape(n, 3)
            values = np.array([constraints[i][1] for i in selected])
            kkt = np.block([[h, equality.T], [equality, np.zeros((n, n))]])
            solution = np.linalg.lstsq(kkt, np.r_[-linear, values], rcond=None)[0][:3]
            t, u, v = solution
            if not (-1e-9 <= t <= 1+1e-9 and u >= -1e-9 and v >= -1e-9 and u+v <= 1+1e-9):
                continue
            if n and np.max(np.abs(equality@solution-values)) > 1e-8:
                continue
            delta = matrix@solution+offset
            best = min(best, float(delta@delta))
    if not np.isfinite(best):
        raise ValueError("capsule/triangle convex distance failed to find a feasible solution")
    return best


def floor_contains(x, z, floors):
    a = floors[:, 0][:, [0, 2]]
    u, v = floors[:, 1][:, [0, 2]]-a, floors[:, 2][:, [0, 2]]-a
    p = np.array([x, z])-a
    uu, uv, vv = np.sum(u*u, axis=1), np.sum(u*v, axis=1), np.sum(v*v, axis=1)
    pu, pv = np.sum(p*u, axis=1), np.sum(p*v, axis=1)
    determinant = uu*vv-uv*uv
    valid = determinant > 0
    s, t = np.full(len(floors), np.inf), np.full(len(floors), np.inf)
    s[valid] = (pu[valid]*vv[valid]-pv[valid]*uv[valid])/determinant[valid]
    t[valid] = (pv[valid]*uu[valid]-pu[valid]*uv[valid])/determinant[valid]
    return bool(np.any(valid & (s >= -1e-10) & (t >= -1e-10) & (s+t <= 1+1e-10)))


def movement_probe(x, z, triangles, floor_mask):
    radius = .22
    directions = [(0, 0), (1, 0), (-1, 0), (0, 1), (0, -1),
                  (.70710678, .70710678), (-.70710678, .70710678),
                  (.70710678, -.70710678), (-.70710678, -.70710678)]
    covered = [floor_contains(x+radius*dx, z+radius*dz, triangles[floor_mask]) for dx, dz in directions]
    lo, hi = triangles.min(axis=1), triangles.max(axis=1)
    candidates = (~floor_mask & (x+radius >= lo[:, 0]) & (x-radius <= hi[:, 0]) &
                  (z+radius >= lo[:, 2]) & (z-radius <= hi[:, 2]) & (hi[:, 1] >= 0) & (lo[:, 1] <= 1.84))
    distances = [capsule_distance2(x, z, triangle) for triangle in triangles[candidates]]
    distance = min(distances) if distances else float("inf")
    return {"position_xz": [x, z], "floor_coverage": covered,
            "nearby_nonfloor_triangles": int(candidates.sum()),
            "minimum_axis_triangle_squared_distance": distance if np.isfinite(distance) else None,
            "blocked_by_wall": distance < radius*radius,
            "walkable": all(covered) and distance >= radius*radius}


def identity(path):
    return {"path": str(path.resolve()), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--runtime-root", type=Path, required=True)
    ap.add_argument("--archive", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()
    root = args.runtime_root
    points, alpha_proof = original_scene_collision_mesh(root)
    triangles = points.astype(float).reshape(-1, 3, 3)
    normal = np.cross(triangles[:, 1]-triangles[:, 0], triangles[:, 2]-triangles[:, 0])
    floor_mask = ((normal[:, 1] > 0) & (normal[:, 1]**2 >= .5*np.sum(normal*normal, axis=1)) &
                  (np.max(np.abs(triangles[:, :, 1]), axis=1) <= .05))
    probe_path = root/"build/original_scene_solid_triangles.csv"
    with probe_path.open(encoding="utf-8", newline="") as source:
        probe = list(csv.DictReader(source))
    actual_indices = [int(row["triangle"]) for row in probe]
    digest = hashlib.sha256(struct.pack("<"+str(len(probe))+"I", *actual_indices)).hexdigest()
    if len(probe) != len(triangles) or digest != alpha_proof["triangle_indices_sha256"]:
        raise ValueError("C collision selection differs from independent source texture/vertex proof")
    if [int(row["ground_adapter"]) for row in probe] != floor_mask.astype(int).tolist():
        raise ValueError("C ground subset differs from independent geometry classification")
    check_path = root/"build/m1_source_collision_checks.txt"
    checks = read_kv(check_path)
    for key, value in {"source_collision_checks": 13, "source_collision_failures": 0,
                       "source_spawn_player_capsule_free": 1, "source_spawn_enemy_capsule_free": 1,
                       "source_spawn_los_clear": 1, "legacy_collision_poison_ignored": 1,
                       "source_actual_wall_capsule_blocked": 1}.items():
        if checks.get(key) != value:
            raise ValueError(f"C actual scene geometry check failed: {key}={checks.get(key)}")
    scene = root/"assets/scenes/original_street/original_street.bin"
    spawn = struct.unpack_from("<6f", scene.read_bytes(), 24)
    wall = [float(v) for v in checks["source_actual_wall_probe_xz"].split(",")]
    probes = {"player": movement_probe(*spawn[:2], triangles, floor_mask),
              "enemy": movement_probe(*spawn[3:5], triangles, floor_mask),
              "wall": movement_probe(*wall, triangles, floor_mask)}
    if not probes["player"]["walkable"] or not probes["enemy"]["walkable"]:
        raise ValueError("source spawns do not pass independent movement geometry")
    if not all(probes["wall"]["floor_coverage"]) or not probes["wall"]["blocked_by_wall"]:
        raise ValueError("real wall probe was not independently distinguished from unsupported floor")
    runtime_path = root/"build/m1_source_skin_result.txt"
    runtime = read_kv(runtime_path)
    if runtime.get("collision_adapter_source") != "original_visible_static_triangles" or runtime.get("collision_recovered") != 0:
        raise ValueError("actual runtime did not select the explicitly limited source surface adapter")
    args.archive.mkdir(parents=True, exist_ok=True)
    archived = {}
    for path in (root/"t3b_hd.exe", probe_path, check_path, runtime_path, root/"build/m1_test_result.txt", root/"build/m1_shot_rays.csv"):
        dest = args.archive/path.name
        shutil.copyfile(path, dest)
        archived[path.name] = identity(dest)
    report = {"schema": "original-visible-static-collision-verification/v1", "passed": True,
              "scope": "PC visible-surface adapter; original game collision remains unrecovered",
              "scene": identity(scene), "solid_triangles": len(triangles), "floor_triangles": int(floor_mask.sum()),
              "triangle_indices_sha256": digest, "movement_probes": probes,
              "distance_method": "independent constrained least squares with active-constraint enumeration",
              "legacy_poison_fixture_passed": True, "archived": archived,
              "limits": ["722 cutout triangles, blended and non-depth-writing states are excluded.",
                         "Ground union uses nine footprint samples and a fixed 1.84-unit capsule.",
                         "Original stairs, navigation, camera collision and dynamic actor collision remain unrecovered."]}
    args.out.write_text(json.dumps(report, indent=2, allow_nan=False)+"\n", encoding="utf-8")
    print(json.dumps({k: v for k, v in report.items() if k not in ("archived", "limits")}))


if __name__ == "__main__":
    main()
