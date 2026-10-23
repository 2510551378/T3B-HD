"""Validate dense completed Aya source passes without labeling their actions."""
import argparse
import hashlib
import json
from pathlib import Path
import numpy as np
from export_aya_source_skin import decode_ge


def identity(path):
    return {"path": str(path.resolve()), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    for name in ("manifest", "metadata", "timing", "ge-audit", "out"):
        ap.add_argument("--" + name, type=Path, required=True)
    a = ap.parse_args()
    m = json.loads(a.manifest.read_text(encoding="utf-8"))
    meta = json.loads(a.metadata.read_text(encoding="utf-8"))
    timing = json.loads(a.timing.read_text(encoding="utf-8"))
    audit = json.loads(a.ge_audit.read_text(encoding="utf-8"))
    if not m.get("denseSource") or len(m["frames"]) < 3:
        raise ValueError("not a dense source capture")
    exact, max_steps, max_error, max_scaled_error = 0, 0, 0.0, 0.0
    largest_step_case = None
    parents, poses, blocks = [b["parent"] for b in meta["bones"]], [], []
    for frame in m["frames"]:
        path = a.manifest.parent / Path(frame["sourceBlock"]["file"]).name
        raw = path.read_bytes()
        if len(raw) != 44 * 0x130:
            raise ValueError("incomplete source block")
        blocks.append(identity(path))
        matrices = []
        if [r["index"] for r in frame["records"]] != list(range(44)):
            raise ValueError("source bone indices changed")
        for i, row in enumerate(frame["records"]):
            words = np.frombuffer(raw[i*0x130:(i+1)*0x130], dtype="<u4")
            expected_parent = 0 if parents[i] < 0 else frame["sourceBase"] + parents[i]*0x130
            if int(words[0x124//4]) != expected_parent:
                raise ValueError(f"bone {i}: parent pointer mismatch")
            payload = words[48:60]
            if payload.tolist() != row["matrix"] or not np.all(payload >> 24 == 0x2b):
                raise ValueError("manifest/source GE payload mismatch")
            left = words[16:32].view("<f4").reshape(4, 4, order="F")
            right = words[32:48].view("<f4").reshape(4, 4, order="F")
            product = (left @ right)[:3].flatten(order="F").astype("<f4")
            decoded = decode_ge(payload)
            if not np.all(np.isfinite(product)) or not np.all(np.isfinite(decoded)):
                raise ValueError("nonfinite matrix")
            packed = product.view("<u4") >> 8
            actual = payload & 0xffffff
            exact += int(np.sum(packed == actual))
            steps = np.abs(packed.astype(np.int64)-actual.astype(np.int64))
            if int(steps.max()) > max_steps:
                j = int(steps.argmax())
                max_steps = int(steps[j])
                largest_step_case = {"frame": frame["frame"], "bone": i, "component": j,
                                     "float32_product": float(product[j]), "ge_value": float(decoded.flatten(order="F")[j])}
            max_error = max(max_error, float(np.abs(product-decoded.flatten(order="F")).max()))
            # Float24 bit-distance is unstable near cancellation to zero.
            # Bound F32 dot-product roundoff by eight eps times |A|*|B|,
            # plus one relative float24 truncation step. Keep both raw errors.
            terms = (np.abs(left[:3].astype(np.float64)) @ np.abs(right.astype(np.float64))).flatten(order="F")
            # GE drops eight F32 low bits, retaining 15 fraction bits.
            bound = 8*np.finfo(np.float32).eps*terms + np.abs(decoded.flatten(order="F"))/32768 + np.finfo(np.float32).tiny
            scaled = float(np.max(np.abs(product-decoded.flatten(order="F"))/bound))
            max_scaled_error = max(max_scaled_error, scaled)
            if scaled > 1:
                j = int(np.argmax(np.abs(product-decoded.flatten(order="F"))/bound))
                raise ValueError(f"frame {frame['frame']} bone {i} component {j}: matrix40*80 exceeds F32/float24 error bound {scaled}; product={product[j]}, actual={decoded.flatten(order='F')[j]}, bound={bound[j]}")
            matrices.append(decoded)
        poses.append(matrices)
    dt = np.diff([f["ticks"] for f in m["frames"]]) / timing["cpu_hz"]
    if not np.all(dt > 0):
        raise ValueError("capture ticks not monotonic")
    median = float(np.median(dt))
    gaps = [{"after_sample": i, "seconds": float(x)} for i, x in enumerate(dt) if x > 1.5*median]
    signatures = {p["vertex_sha256"] for p in meta["packets"]}
    obs = [r for r in audit["observations"] if r["vertex_sha256"] in signatures]
    endpoint_frames = [f["frame"] for f in m["frames"] if f.get("dump")]
    if not obs or any(len(r["source_candidates"]) != 1 for r in obs):
        raise ValueError("original Aya endpoint GE payload mismatch")
    for frame in endpoint_frames:
        if len({r["vertex_sha256"] for r in obs if r["frame"] == frame}) != 106:
            raise ValueError("missing endpoint Aya draw geometry")
    poses = np.asarray(poses)
    changes = np.any(poses[1:] != poses[:-1], axis=(2, 3)).sum(axis=0).tolist()
    report = {
        "schema": "aya-dense-source-integrity/v1", "passed": True,
        "samples": len(poses), "source_bones": 44, "parent_pointer_checks": 44*len(poses),
        "cpu_hz_from_save": timing["cpu_hz"], "median_interval_seconds": median,
        "min_interval_seconds": float(dt.min()), "max_interval_seconds": float(dt.max()), "gaps": gaps,
        "duration_seconds": float(dt.sum()), "changed_adjacent_samples_per_bone": changes,
        "matrix40_times_80": {"exact_float24_components": exact, "total_components": int(poses.size),
                                 "max_float24_steps": max_steps, "largest_step_case": largest_step_case,
                                 "max_absolute_error": max_error, "max_error_over_roundoff_bound": max_scaled_error},
        "ge_endpoint_frames": endpoint_frames, "aya_exact_endpoint_influences": len(obs),
        "unmatched_aya_endpoint_influences": 0, "source_blocks": blocks,
        "inputs": {name: identity(getattr(a, name)) for name in ("manifest", "metadata", "timing", "ge_audit")},
        "limits": ["Only recorded GE cross-check samples are independently replayed; other source passes have no GE dump.",
                   "Timestamp gaps must remain unchanged." if gaps else "No interval exceeds 1.5 times the median; original timestamps remain unchanged.",
                   "Input-held combat capture may contain enemy contact or action transitions.",
                   "Weapon WORLD is present but requires its own geometry/GE validation." if m.get("worldSourceBinding") else
                   "Dense per-frame weapon WORLD transforms are not captured; this is not a body/weapon runtime clip yet."]}
    a.out.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: v for k, v in report.items() if k not in ("source_blocks", "inputs", "changed_adjacent_samples_per_bone")}))


if __name__ == "__main__":
    main()
