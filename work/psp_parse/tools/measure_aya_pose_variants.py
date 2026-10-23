"""Measure socket and pose variation across additional PPSSPP input captures."""
from __future__ import annotations

import json
import math
from collections import defaultdict
from pathlib import Path

from measure_aya_socket_error import apply_pose, dot, norm, rot_y, sub, mix_matrix


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    timeline = json.loads((root / "out/AYA_POSE_VARIANTS.json").read_text(encoding="utf-8"))
    static = json.loads((root.parent / "t3b_hd/assets/models/aya_ge_matrices.json").read_text(encoding="utf-8"))
    sm = static["bones"]["bone4"]["matrix"]
    pivot = [.95, 1.90, 0.0]
    grip = [.09, 1.79, .13]
    muzzle = [.30, 1.795, .106]
    muzzle2 = [.30, 1.795, .306]
    correction = [.742355, .029960, -.252845]
    yaw = math.radians(155.0)
    by_pose = defaultdict(list)
    for fr in timeline["frames"]:
        ch = fr["channels"]["arm_right_hand"]
        m = mix_matrix(sm, ch["matrix"])
        g = apply_pose(rot_y(grip, grip, yaw), m, pivot)
        mz = apply_pose(rot_y(muzzle, grip, yaw), m, pivot)
        mz2 = apply_pose(rot_y(muzzle2, grip, yaw), m, pivot)
        g = [g[i] + correction[i] for i in range(3)]
        mz = [mz[i] + correction[i] for i in range(3)]
        mz2 = [mz2[i] + correction[i] for i in range(3)]
        direction = norm(sub(mz2, mz))
        hand_box = ch["bbox"]
        hand = [(hand_box[0][i] + hand_box[1][i]) * .5 for i in range(3)]
        hand_axis = norm([m[0][2], m[1][2], m[2][2]])
        by_pose[fr["pose"]].append({
            "frame": fr["frame"],
            "grip_error": math.sqrt(sum((g[i] - hand[i]) ** 2 for i in range(3))),
            "muzzle_forward_error_deg": math.degrees(math.acos(max(-1, min(1, dot(direction, hand_axis))))),
            "direction": direction,
        })
    report = {"schema": "aya-pose-variant-error/v1", "poses": {}}
    for pose, rows in by_pose.items():
        jitter = []
        for i in range(1, len(rows)):
            cosine = max(-1.0, min(1.0, dot(rows[i]["direction"], rows[i - 1]["direction"])))
            jitter.append(math.degrees(math.acos(cosine)))
        report["poses"][pose] = {
            "frames": len(rows),
            "grip_error_mean": sum(r["grip_error"] for r in rows) / len(rows),
            "grip_error_max": max(r["grip_error"] for r in rows),
            "muzzle_forward_error_mean_deg": sum(r["muzzle_forward_error_deg"] for r in rows) / len(rows),
            "muzzle_forward_error_max_deg": max(r["muzzle_forward_error_deg"] for r in rows),
            "muzzle_jitter_mean_deg": sum(jitter) / len(jitter) if jitter else 0.0,
            "muzzle_jitter_max_deg": max(jitter) if jitter else 0.0,
        }
    out = root / "out/AYA_POSE_VARIANT_ERROR.json"
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    lines = ["# Aya 多姿态交叉验证", "", "参考为 PPSSPP 每个姿态的 `arm_right_hand` weighted draw bbox；socket 误差仍是工程测量。", ""]
    for pose, item in report["poses"].items():
        lines.append(f"- `{pose}`：{item['frames']} 帧；grip 平均/最大 {item['grip_error_mean']:.5f}/{item['grip_error_max']:.5f}；枪口方向平均/最大 {item['muzzle_forward_error_mean_deg']:.3f}°/{item['muzzle_forward_error_max_deg']:.3f}°；连续帧抖动平均/最大 {item['muzzle_jitter_mean_deg']:.3f}°/{item['muzzle_jitter_max_deg']:.3f}°。")
    (root / "out/AYA_POSE_VARIANT_ERROR.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print((root / "out/AYA_POSE_VARIANT_ERROR.md").read_text(encoding="utf-8"))


if __name__ == "__main__":
    main()
