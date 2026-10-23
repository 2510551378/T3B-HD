"""Independent NumPy comparison of actual UE contact/barrel vertices over fire loops."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import struct

import numpy as np


def load(path):
    data = path.read_bytes()
    _, bones, packets, vertices, samples, _, _, _ = struct.unpack_from("<8I", data, 8)
    _, units, floor, _ = struct.unpack_from("<4f", data, 40)
    offset = 56 + bones * 4 + packets * 16
    dtype = np.dtype([("values", "<f4", 8), ("count", "<u4"), ("bone", "<u4", 8), ("weight", "<f4", 8)])
    v = np.frombuffer(data, dtype=dtype, count=vertices, offset=offset)
    offset += vertices * 100
    time = np.frombuffer(data, dtype="<f4", count=samples, offset=offset)
    m = np.frombuffer(data, dtype="<f4", offset=offset+samples*4).reshape(samples, bones, 3, 4)
    return v, time, m, units, floor


def pose(skin, index, seconds):
    vertices, times, matrices, _, _ = skin
    t = np.float32(min(max(seconds, 0), times[-1]))
    a = min(int(np.searchsorted(times, t, side="right")) - 1, len(times) - 1)
    b = min(a + 1, len(times) - 1)
    mix = np.float32(0 if a == b else (t-times[a])/(times[b]-times[a]))
    matrix = matrices[a]*(np.float32(1)-mix)+matrices[b]*mix
    v = vertices[index]
    point = np.zeros(3, dtype=np.float32)
    for influence in range(int(v["count"])):
        m = matrix[v["bone"][influence]]
        # Explicit sequential float32 arithmetic, independent of UE's component buffers.
        q = m[:, 0]*v["values"][0]+m[:, 1]*v["values"][1]+m[:, 2]*v["values"][2]+m[:, 3]
        point += v["weight"][influence]*q
    return point


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", type=Path, required=True)
    parser.add_argument("--probe-root", type=Path, required=True)
    args = parser.parse_args()
    bundle = args.project_root/"Content/SourceData"
    manifest = json.loads((bundle/"manifest.json").read_text(encoding="utf-8"))
    meta = json.loads((args.probe_root/"continuous_fire.json").read_text(encoding="utf-8"))
    assert meta["all_csv_written"] and meta["actual_component_CPU_readback"]
    files = {actor["name"]: actor["binary"] for actor in manifest["actors"]}
    assert all(actor["spawn"] == [0, 0, 0] for actor in manifest["actors"] if actor["name"] in ("Aya", "Weapon")), "Verifier requires the recorded pair origin"
    if meta["action_clip"] != "reference":
        clip = next(c for c in manifest["action_clips"] if c["label"] == meta["action_clip"])
        files.update(Aya=clip["body"], Weapon=clip["weapon"])
    body, weapon = load(bundle/files["Aya"]), load(bundle/files["Weapon"])
    assert np.array_equal(body[1], weapon[1])
    rows = np.genfromtxt(args.probe_root/"continuous_fire.csv", delimiter=",", names=True)
    assert len(rows) == meta["samples"] == 361
    assert np.array_equal(rows["sample"], np.arange(361))
    maximum = 0.
    expected_directions, actual_directions = [], []
    seam_rows = 0
    for row in rows:
        elapsed = float(np.float32(row["elapsed"]))
        duration, seam = float(body[1][-1]), float(np.float32(meta["seam_seconds"]))
        phase = elapsed % (duration+seam)
        u = max(0., min(1., (phase-duration)/seam))
        blend = np.float32(u*u*(3-2*u))
        first = np.float32(min(phase, duration))
        assert abs(row["source_time"]-first) < 1e-5 and abs(row["seam_alpha"]-blend) < 1e-5
        seam_rows += blend > 0
        expected = {}
        for label, skin, index in (("body", body, meta["body_contact_vertex"]),
                                   ("grip", weapon, meta["weapon_contact_vertex"]),
                                   ("tip", weapon, meta["barrel_tip_vertex"]),
                                   ("base", weapon, meta["barrel_base_vertex"])):
            p = pose(skin, index, first)
            if blend > 0:
                p += (pose(skin, index, 0)-p)*blend
            pc = p*np.float32(skin[3]); pc[1] = np.float32(p[1]-np.float32(skin[4]))*np.float32(skin[3])
            ue = pc[[2, 0, 1]]*np.array([100, -100, 100], dtype=np.float32)
            actual = np.array([row[f"{label}_{axis}"] for axis in "xyz"])
            maximum = max(maximum, float(abs(ue-actual).max()))
            expected[label] = ue.astype(float)
        predicted = expected["tip"]-expected["base"]
        actual = np.array([row[f"tip_{a}"]-row[f"base_{a}"] for a in "xyz"])
        expected_directions.append(predicted/np.linalg.norm(predicted))
        actual_directions.append(actual/np.linalg.norm(actual))
    assert maximum < .002 and seam_rows > 10
    contacts = np.sqrt(sum((rows[f"body_{a}"]-rows[f"grip_{a}"])**2 for a in "xyz"))
    assert contacts.max() < 2.0, "same-capture mesh contact candidate detached"
    angles = np.degrees(np.arccos(np.clip(np.sum(np.array(expected_directions)*actual_directions, axis=1), -1, 1)))
    assert angles.max() < .01
    output = {"schema": "t3b-m1-continuous-fire-verification/v1", "passed": True,
        "clip": meta["action_clip"], "samples": len(rows), "elapsed_seconds": float(rows["elapsed"][-1]),
        "loop_seam_samples": int(seam_rows), "max_component_error_cm": maximum,
        "contact_candidate_distance_cm": {"min": float(contacts.min()), "max": float(contacts.max())},
        "max_barrel_direction_error_degrees": float(angles.max()), "anchor_indices": meta,
        "inputs": {name: {"file": path, "sha256": hashlib.sha256((bundle/path).read_bytes()).hexdigest()}
                   for name, path in files.items() if name in ("Aya", "Weapon")},
        "csv_sha256": hashlib.sha256((args.probe_root/"continuous_fire.csv").read_bytes()).hexdigest(),
        "scope": "actual procedural CPU vertices, shared-clock/seam and geometry-derived contact/barrel candidates",
        "named_original_socket_recovered": False, "original_loop_timing_recovered": False}
    (args.probe_root/"motion_verification.json").write_text(json.dumps(output, indent=2)+"\n", encoding="utf-8")
    print(json.dumps(output))


if __name__ == "__main__":
    main()
