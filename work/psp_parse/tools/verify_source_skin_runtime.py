"""Check the compiled C runtime against original poses and exported affine data."""
import argparse
import hashlib
import json
import struct
from pathlib import Path
import numpy as np
from export_aya_source_skin import decode_ge, pose_vertices


def read_binary(path):
    data = path.read_bytes()
    magic, version, bones, packets, vertices, frames, materials, flags, reserved, fps, units, floor, pad = struct.unpack_from("<8s8I4f", data)
    if magic != b"T3BSKN2\0" or version != 2:
        raise ValueError("unexpected asset header")
    offset = 56 + bones * 4 + packets * 16
    vs = [struct.unpack_from("<8fI8I8f", data, offset + i * 100) for i in range(vertices)]
    offset += vertices * 100
    times = np.frombuffer(data, dtype="<f4", count=frames, offset=offset)
    offset += frames * 4
    matrices = np.frombuffer(data, dtype="<f4", offset=offset).reshape(frames, bones, 3, 4)
    return vs, matrices, times


def binary_pose(vertices, matrices):
    result = []
    for v in vertices:
        p = np.asarray(v[:3], dtype=np.float32)
        q = np.zeros(3, dtype=np.float32)
        for j in range(v[8]):
            index, w = v[9 + j], v[17 + j]
            q += np.float32(w) * (matrices[index, :, :3] @ p + matrices[index, :, 3])
        result.append(q)
    return np.asarray(result)


def read_kv(path):
    result = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        k, v = line.split("=", 1)
        try:
            result[k] = int(v, 16) if v.lower().startswith("0x") else float(v)
        except ValueError:
            result[k] = v
    return result


def verify_clip(root, label, body_path, weapon_path, all_samples=False):
    body = json.loads(body_path.read_text(encoding="utf-8"))
    weapon = json.loads(weapon_path.read_text(encoding="utf-8"))
    metadata = json.loads(Path(body["inputs"]["metadata"]["path"]).read_text(encoding="utf-8"))
    manifest = json.loads(Path(body["inputs"]["manifest"]["path"]).read_text(encoding="utf-8"))
    source_vertices = [v for p in metadata["packets"] for v in p["vertices"]]
    result = {}
    for name, path, identity in [("aya", Path(body["output"]), body["sha256"]), ("weapon", Path(weapon["runtime_output"]), weapon["binary_sha256"])]:
        if hashlib.sha256(path.read_bytes()).hexdigest() != identity:
            raise ValueError(f"{label}/{name}: exported asset identity changed")
        vertices, matrices, times = read_binary(path)
        probe = np.loadtxt(root / "build" / f"{name}_{label}_cpu_probe.csv", delimiter=",")
        checked_samples = list(range(len(times))) if all_samples else [0, len(times)-1]
        if probe.shape != (len(vertices) * len(checked_samples), 5):
            raise ValueError("clip probe rows are incomplete")
        error = 0.0
        for f in checked_samples:
            rows = probe[probe[:, 0] == f]
            if len(rows) != len(vertices) or not np.array_equal(rows[:, 1], np.arange(len(vertices))):
                raise ValueError("clip probe vertex order mismatch")
            if name == "aya":
                original = np.asarray([decode_ge(r["matrix"]) for r in manifest["frames"][f]["records"]])
                expected = pose_vertices(source_vertices, original)
            else:
                expected = binary_pose(vertices, matrices[f])
            error = max(error, float(np.abs(rows[:, 2:] - expected).max()))
        if error > 0.0001:
            raise ValueError(f"{label}/{name}: CPU pose mismatch {error}")
        result[name] = {"samples": len(times), "verified_sample_indices": checked_samples, "vertices": len(vertices), "max_cpu_position_error_original_units": error}
    return result


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--runtime-root", type=Path, required=True)
    ap.add_argument("--body-report", type=Path, required=True)
    ap.add_argument("--clip", nargs=3, action="append", metavar=("LABEL", "BODY_REPORT", "WEAPON_REPORT"), default=[])
    ap.add_argument("--out", type=Path, required=True)
    a = ap.parse_args()
    root = a.runtime_root
    body = json.loads(a.body_report.read_text(encoding="utf-8"))
    source = json.loads(Path(body["inputs"]["metadata"]["path"]).read_text(encoding="utf-8"))
    manifest = json.loads(Path(body["inputs"]["manifest"]["path"]).read_text(encoding="utf-8"))
    source_vertices = [v for p in source["packets"] for v in p["vertices"]]
    results = {}
    for name, binary, probe in [("aya", "aya_source_skin.bin", "aya_source_cpu_probe.csv"), ("weapon", "aya_source_weapon.bin", "aya_weapon_cpu_probe.csv")]:
        path = root / "assets/models" / binary
        vertices, matrices, times = read_binary(path)
        observed = np.loadtxt(root / "build" / probe, delimiter=",")
        if observed.shape != (len(vertices) * 2, 5):
            raise ValueError("runtime probe has missing rows")
        error = 0.0
        for f in (0, len(times) - 1):
            rows = observed[observed[:, 0] == f]
            if len(rows) != len(vertices) or not np.array_equal(rows[:, 1], np.arange(len(vertices))):
                raise ValueError("probe vertex identity/order mismatch")
            if name == "aya":
                records = manifest["frames"][f]["records"]
                expected = pose_vertices(source_vertices, np.asarray([decode_ge(r["matrix"]) for r in records]))
            else:
                expected = binary_pose(vertices, matrices[f])
            error = max(error, float(np.abs(rows[:, 2:] - expected).max()))
        if error > 0.0001:
            raise ValueError(f"{name}: CPU skinning differs by {error} original units")
        results[name] = {"vertices": len(vertices), "samples": len(times), "verified_sample_indices": [0, len(times) - 1],
                         "max_cpu_position_error_original_units": error, "asset_sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
    battle = read_kv(root / "build/m1_test_result.txt")
    loaded = read_kv(root / "build/m1_source_skin_result.txt")
    required = {"enemy_dead": 1, "enemy_hp": 0, "collision_boundary": 1, "los_blocked": 1, "overdive_seen": 1, "overdive_return": 1}
    for key, value in required.items():
        if battle.get(key) != value:
            raise ValueError(f"battle regression: {key}={battle.get(key)}")
    for key, value in {"aya_source_skin_loaded": 1, "aya_source_bones": 44, "aya_source_packets": 106, "aya_source_vertices": 3456,
                       "weapon_source_loaded": 1, "weapon_source_vertices": 243, "legacy_weapon_enabled": 0,
                       "angle_hit_fallback": 0, "player_los_fallback": 0, "source_pair_sync_failures": 0}.items():
        if loaded.get(key) != value:
            raise ValueError(f"source asset regression: {key}")
    if loaded["muzzle_ray_hits"] != battle["shots_hit"] or loaded["muzzle_ray_shots"] != sum(loaded[k] for k in ("muzzle_ray_hits", "muzzle_ray_blocked", "muzzle_ray_misses")):
        raise ValueError("shot ray accounting mismatch")
    report = {"schema": "aya-c-runtime-source-skin-verification/v2", "passed": True, "numeric_verification": results,
              "action_clip_numeric_verification": {label: verify_clip(root, label, Path(b), Path(w)) for label, b, w in a.clip},
              "battle_smoke": {key: battle[key] for key in required}, "shots_hit": battle["shots_hit"], "runtime_assets": loaded,
              "limits": [("Shots use the current original posed triangle mesh and M1 vertical collision columns; original game hitboxes and level collision are not recovered."
                          if loaded.get("enemy_hit_geometry") == "posed_original_source_triangles" else
                          "Ray/capsule checks use an M1 guard.pmf proxy and vertical collision columns; original Twisted hitboxes and level collision are not recovered."),
                         "Captured poses do not establish a complete original recoil cycle or animation state machine.",
                         "Muzzle origin is a measured geometry tip, not yet the original game's socket data."]}
    a.out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report))


if __name__ == "__main__":
    main()
