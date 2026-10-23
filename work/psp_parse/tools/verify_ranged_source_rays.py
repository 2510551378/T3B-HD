"""Check actual M1 shot logs against their measured mesh or legacy proxy.

This verifies the straight ray path and continued source-clip playback, not
original-game hitbox data or a complete recoil animation.
"""
import argparse
import csv
import hashlib
import json
import math
import struct
from pathlib import Path
import numpy as np
from PIL import Image
from verify_source_skin_runtime import read_binary, binary_pose, read_kv


def nearest_mesh(origin, direction, points, max_t=9):
    """Plane intersection + Gram-system barycentrics, independent of C Moller."""
    tri = points.astype(np.float64).reshape(-1, 3, 3)
    a, b, c = tri[:, 0], tri[:, 1], tri[:, 2]
    u, v = b-a, c-a
    n = np.cross(u, v)
    denom = n @ direction
    valid = np.abs(denom) > 1e-15
    t = np.full(len(tri), np.inf)
    t[valid] = np.sum(n[valid]*(a[valid]-origin), axis=1)/denom[valid]
    with np.errstate(invalid="ignore"):
        q = origin + t[:, None]*direction - a
        uu, uv, vv = np.sum(u*u, axis=1), np.sum(u*v, axis=1), np.sum(v*v, axis=1)
        qu, qv = np.sum(q*u, axis=1), np.sum(q*v, axis=1)
        det = uu*vv-uv*uv
        s = np.full(len(tri), np.inf)
        r = s.copy()
        good = det > 0
        s[good] = (qu[good]*vv[good]-qv[good]*uv[good])/det[good]
        r[good] = (qv[good]*uu[good]-qu[good]*uv[good])/det[good]
    valid &= good & (s >= -1e-8) & (r >= -1e-8) & (s+r <= 1+1e-8) & (t >= 0) & (t <= max_t)
    return float(t[valid].min()) if np.any(valid) else math.inf


def wall_distance(origin, direction, boundary, boxes, max_t=9):
    if not (boundary[0] <= origin[0] <= boundary[2] and boundary[1] <= origin[2] <= boundary[3]):
        return 0.0
    result = math.inf
    for axis, lo, hi in ((0, boundary[0], boundary[2]), (2, boundary[1], boundary[3])):
        if direction[axis]:
            t = ((hi if direction[axis] > 0 else lo)-origin[axis])/direction[axis]
            if 0 <= t <= max_t:
                result = min(result, t)
    for box in boxes:
        enter, leave = 0.0, max_t
        for axis, lo, hi in ((0, box[0], box[2]), (2, box[1], box[3])):
            if direction[axis] == 0:
                if not lo <= origin[axis] <= hi:
                    enter = math.inf
                continue
            p, q = sorted(((lo-origin[axis])/direction[axis], (hi-origin[axis])/direction[axis]))
            enter, leave = max(enter, p), min(leave, q)
        if enter <= leave:
            result = min(result, enter)
    return result


def original_scene_collision_mesh(root):
    """Conservative visible surface adapter, independently selected from bytes."""
    scene = root/"assets/scenes/original_street/original_street.bin"
    material_path = scene.with_name("original_street_materials.txt")
    data = scene.read_bytes()
    magic, version, draws, vertices, materials = struct.unpack_from("<8s4I", data)
    if (magic, version) != (b"T3BSCN1\0", 1) or len(data) != 56+12*draws+24*vertices:
        raise ValueError("invalid original street collision source")
    lines = [s.split() for s in material_path.read_text(encoding="utf-8").splitlines() if s.strip()]
    if lines[0] != ["T3BSCNM1", str(materials)] or len(lines) != materials+1:
        raise ValueError("incomplete static surface material proof")
    eligible, proofs = [], []
    for line in lines[1:]:
        texture = root/line[0]
        with Image.open(texture) as image:
            alpha = np.asarray(image.convert("RGBA"))[:, :, 3]
            no_holes = bool(np.all(alpha > 0))
        accepted = line[1] == "0" and line[2] == "1" and no_holes
        eligible.append(accepted)
        proofs.append({"texture": str(texture.resolve()), "sha256": hashlib.sha256(texture.read_bytes()).hexdigest(),
                       "all_texels_alpha_positive": no_holes, "solid_material": accepted})
    vertex_start = 56+12*draws
    selected, indices = [], []
    for draw in range(draws):
        first, count, material = struct.unpack_from("<3I", data, 56+12*draw)
        if first+count > vertices or count % 3 or material >= materials:
            raise ValueError("invalid static triangle packet")
        if not eligible[material]:
            continue
        for i in range(first, first+count, 3):
            triangle = [struct.unpack_from("<5f4B", data, vertex_start+(i+j)*24) for j in range(3)]
            if any(v[8] == 0 for v in triangle):
                continue
            selected.extend(v[:3] for v in triangle)
            indices.append(i//3)
    if not selected:
        raise ValueError("no proven visible static triangles")
    return np.asarray(selected, dtype=np.float32), {
        "scene_sha256": hashlib.sha256(data).hexdigest(),
        "material_manifest_sha256": hashlib.sha256(material_path.read_bytes()).hexdigest(),
        "solid_triangles": len(indices), "triangle_indices_sha256": hashlib.sha256(struct.pack("<"+str(len(indices))+"I", *indices)).hexdigest(),
        "material_alpha_proofs": proofs}


def verify_original_mesh(root, path, rows, allow_incomplete, original_scene_collision=False):
    model = root/"assets/models/original_actor_source.bin"
    vertices, matrices, times = read_binary(model)
    units, floor = struct.unpack_from("<2f", model.read_bytes(), 44)
    boundary, boxes = None, []
    collision = root/"assets/scene/nyc_block.col.txt"
    for line in collision.read_text(encoding="utf-8").splitlines():
        tokens = line.split()
        if tokens and tokens[0] in ("boundary", "box"):
            values = [float(x) for x in tokens[1:]]
            if tokens[0] == "boundary":
                boundary = values
            else:
                boxes.append(values)
    static, static_proof = original_scene_collision_mesh(root) if original_scene_collision else (None, None)
    checks, hits, blocks, max_error = [], 0, 0, 0.0
    for row in rows:
        t = np.float32(row["enemy_source_time"])
        a = max(0, min(len(times)-1, int(np.searchsorted(times, t, side="right"))-1))
        b = min(len(times)-1, a+1)
        f = np.float32(0 if a == b else (t-times[a])/(times[b]-times[a]))
        pose = binary_pose(vertices, matrices[a]*(np.float32(1)-f)+matrices[b]*f)
        pose[:, 0] *= np.float32(units)
        pose[:, 1] = (pose[:, 1]-np.float32(floor))*np.float32(units)
        pose[:, 2] *= np.float32(units)
        yaw = np.float32(row["enemy_yaw"])
        sn, cs = np.sin(yaw), np.cos(yaw)
        points = pose.copy()
        points[:, 0] = np.float32(row["ex"])+pose[:, 0]*cs+pose[:, 2]*sn
        points[:, 2] = np.float32(row["ez"])-pose[:, 0]*sn+pose[:, 2]*cs
        o = np.array([float(row[k]) for k in ("ox", "oy", "oz")])
        d = np.array([float(row[k]) for k in ("dx", "dy", "dz")])
        max_t = float(row.get("range", 9))
        expected_adapter = "original_visible_static_triangles" if original_scene_collision else "legacy_columns"
        if row.get("collision_adapter", expected_adapter) != expected_adapter:
            raise ValueError("shot adapter disagrees with selected independent collision proof")
        if not np.all(np.isfinite(o)) or not np.all(np.isfinite(d)) or abs(d@d-1) > 1e-5:
            raise ValueError("invalid original-mesh shot ray")
        if not math.isfinite(max_t) or max_t <= 0:
            raise ValueError("invalid original-mesh shot range")
        mesh_t = nearest_mesh(o, d, points, max_t)
        wall_t = nearest_mesh(o, d, static, max_t) if original_scene_collision else float(wall_distance(o, d, boundary, boxes, max_t))
        hit, blocked = mesh_t < wall_t and mesh_t <= max_t, wall_t <= mesh_t and wall_t <= max_t
        distance = min(mesh_t, wall_t, max_t)
        error = abs(distance-float(row["distance"]))
        if int(row["hit"]) != hit or int(row["blocked"]) != blocked or error > .0005:
            raise ValueError(f"shot frame {row['frame']} disagrees with independent mesh/wall intersection: {mesh_t}, {wall_t}, {error}")
        hits += int(hit)
        blocks += int(blocked)
        max_error = max(max_error, error)
        checks.append({"frame": int(row["frame"]), "enemy_sample_time": float(t), "range": max_t, "hit": hit, "blocked": blocked,
                       "mesh_distance": mesh_t if math.isfinite(mesh_t) else None, "wall_distance": wall_t if math.isfinite(wall_t) else None,
                       "distance_error": error})
    if not rows or (not allow_incomplete and hits != 4):
        raise ValueError("battle fixture must finish with four mesh hits")
    return {"schema": "m1-original-weapon-mesh-ray-check/v3", "passed": True,
            "scope": "independent geometry/occlusion checks; kill required" if not allow_incomplete else "independent geometry/occlusion only; normal-spawn kill may be incomplete",
            "shots": len(rows), "hits": hits, "blocked": blocks, "four_hit_kill_proven": hits == 4,
            "max_distance_difference_PC_units": max_error, "checks": checks,
            "shot_log": str(path.resolve()), "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "model_sha256": hashlib.sha256(model.read_bytes()).hexdigest(), "collision_sha256": hashlib.sha256(collision.read_bytes()).hexdigest(),
            "scene_collision": "original_visible_static_triangles" if original_scene_collision else "legacy_columns",
            "static_surface_proof": static_proof,
            "limits": ["Actual posed original mesh is used; original game hitbox data remains unrecovered.",
                       "Only proven no-hole static render triangles occlude; alpha-hole/blended surfaces are excluded." if original_scene_collision else
                       "Occlusion columns belong to the current M1 approximation, not original collision.",
                       "Original game collision has not been recovered."]}


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--runtime-root", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--ray-log", type=Path)
    ap.add_argument("--allow-incomplete", action="store_true")
    ap.add_argument("--original-scene-collision", action="store_true")
    args = ap.parse_args()
    path = args.ray_log or args.runtime_root / "build/m1_ranged_shot_rays.csv"
    with path.open(encoding="utf-8", newline="") as source:
        rows = list(csv.DictReader(source))
    if "enemy_source_time" in (rows[0] if rows else {}):
        report = verify_original_mesh(args.runtime_root, path, rows, args.allow_incomplete, args.original_scene_collision)
        args.out.write_text(json.dumps(report, indent=2)+"\n", encoding="utf-8")
        print(json.dumps({k: v for k, v in report.items() if k not in ("checks", "static_surface_proof")}))
        return
    if len(rows) != 4:
        raise ValueError("ranged fixture must complete with exactly four hits")
    errors, distances, times = [], [], []
    for row in rows:
        if row["clip"] != "fire" or int(row["hit"]) != 1 or int(row["blocked"]) != 0:
            raise ValueError("ranged shot was not a fire-clip capsule hit")
        o = [float(row[k]) for k in ("ox", "oy", "oz")]
        d = [float(row[k]) for k in ("dx", "dy", "dz")]
        t = float(row["distance"])
        if not all(math.isfinite(x) for x in o + d + [t]) or abs(sum(x*x for x in d)-1) > 1e-5 or t < .5:
            raise ValueError("invalid ray or muzzle starts too close to target")
        # Fixture faces the stationary proxy toward Aya along world -X.
        cx, cz = float(row["ex"]) - .20, float(row["ez"])
        p = [a+b*t for a, b in zip(o, d)]
        y = min(1.45, max(.30, p[1]))
        error = abs(math.sqrt((p[0]-cx)**2 + (p[1]-y)**2 + (p[2]-cz)**2) - .30)
        if error > 2e-5:
            raise ValueError(f"ray endpoint does not lie on proxy surface: {error}")
        errors.append(error)
        distances.append(t)
        times.append(float(row["time"]))
    if times[0] != 0 or not all(t > .25 for t in times[1:]):
        raise ValueError("fixture did not exercise both first and clamped fire samples")
    report = {
        "schema": "m1-original-weapon-ranged-ray-check/v1", "passed": True,
        "shot_log": str(path.resolve()), "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "hits": len(rows), "distances_after_muzzle_world_units": distances,
        "fire_clip_times_seconds": times, "max_proxy_surface_residual": max(errors),
        "limits": ["Proxy dimensions belong to M1 guard.pmf, not original Twisted collision.",
                   "Later shots hold the last captured pose; this is not complete continuous recoil."]}
    args.out.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report))


if __name__ == "__main__":
    main()
