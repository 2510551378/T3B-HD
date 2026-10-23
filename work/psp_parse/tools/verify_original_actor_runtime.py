"""Verify all compiled-C original actor samples and the explicit ranged fixture."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import numpy as np
from export_aya_source_skin import decode_ge, pose_vertices
from verify_source_skin_runtime import read_kv


def identity(path):
    return {"path": str(path.resolve()), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--runtime-root", type=Path, required=True)
    ap.add_argument("--export-report", type=Path, required=True)
    ap.add_argument("--archive", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--ray-log", type=Path)
    a = ap.parse_args()
    report = json.loads(a.export_report.read_text(encoding="utf-8"))
    model = Path(report["output"])
    if identity(model)["sha256"] != report["binary_sha256"]:
        raise ValueError("actor model identity changed")
    metadata = json.loads(Path(report["inputs"]["metadata"]["path"]).read_text(encoding="utf-8"))
    manifest = json.loads(Path(report["inputs"]["aligned_manifest"]["path"]).read_text(encoding="utf-8"))
    vertices = [v for p in metadata["packets"] for v in p["vertices"]]
    probe_path = a.runtime_root / "build/original_actor_cpu_probe.csv"
    probe = np.loadtxt(probe_path, delimiter=",")
    if probe.shape != (len(manifest["frames"])*len(vertices), 5):
        raise ValueError("actor probe must cover every sample and vertex")
    error = 0.0
    for f, frame in enumerate(manifest["frames"]):
        rows = probe[f*len(vertices):(f+1)*len(vertices)]
        if not np.all(rows[:, 0] == f) or not np.array_equal(rows[:, 1], np.arange(len(vertices))):
            raise ValueError("actor probe frame or vertex order changed")
        matrices = np.asarray([decode_ge(r["matrix"]) for r in frame["records"]])
        error = max(error, float(np.abs(pose_vertices(vertices, matrices)-rows[:, 2:]).max()))
    if error > .0001:
        raise ValueError(f"C pose differs from original source: {error}")
    runtime = read_kv(a.runtime_root/"build/m1_source_skin_result.txt")
    battle = read_kv(a.runtime_root/"build/m1_test_result.txt")
    required = {"original_enemy_enabled": 1, "original_enemy_bones": 11, "original_enemy_packets": 28,
                "original_enemy_vertices": 1800, "original_enemy_triangles": 600, "original_enemy_samples": 60,
                "original_enemy_render_hit_mesh_max_error": 0, "original_enemy_render_hit_mesh_sync_failures": 0,
                "angle_hit_fallback": 0, "player_los_fallback": 0, "enemy_hit_geometry": "posed_original_source_triangles"}
    for key, value in required.items():
        if runtime.get(key) != value:
            raise ValueError(f"runtime actor/mesh regression: {key}={runtime.get(key)}")
    if runtime["original_enemy_mesh_ray_queries"] < 1 or runtime["original_enemy_mesh_triangle_checks"] != 600*runtime["original_enemy_mesh_ray_queries"]:
        raise ValueError("actual original mesh was not checked for all rays")
    if battle.get("enemy_dead") != 1 or battle.get("shots_hit") != 4:
        raise ValueError("ranged fixture did not finish with four actual original-mesh hits")
    a.archive.mkdir(parents=True, exist_ok=True)
    archived = {}
    for file in (probe_path, a.runtime_root/"t3b_hd.exe", a.runtime_root/"build/m1_source_skin_result.txt", a.runtime_root/"build/m1_test_result.txt", a.ray_log or a.runtime_root/"build/m1_ranged_shot_rays.csv"):
        dest = a.archive / file.name
        shutil.copyfile(file, dest)
        archived[file.name] = identity(dest)
    result = {"schema": "original-actor-C-runtime-verification/v1", "passed": True,
              "export_report": identity(a.export_report), "all_samples": len(manifest["frames"]),
              "all_vertices_per_sample": len(vertices), "max_C_vs_original_position_error_original_units": error,
              "scope": "all actor source poses and explicit ranged battle fixture; not complete AI or normal-spawn completion",
              "runtime": runtime, "battle": battle, "archived": archived,
              "limits": ["Recorded actor motion clamps at its last sample.", "Original AI, hit and death state machines remain unrecovered."]}
    a.out.write_text(json.dumps(result, indent=2)+"\n", encoding="utf-8")
    print(json.dumps({"passed": True, "samples": result["all_samples"], "vertices": len(vertices), "max_position_error": error}))


if __name__ == "__main__":
    main()
