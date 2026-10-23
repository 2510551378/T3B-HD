"""Measure socket error over the additional movement/aiming action capture."""
from __future__ import annotations

import json
import math
from collections import defaultdict
from pathlib import Path

from measure_aya_socket_error import apply_pose, dot, mix_matrix, norm, rot_y, sub


def main() -> None:
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("pose_json", type=Path)
    ap.add_argument("out_json", type=Path)
    ap.add_argument("out_md", type=Path)
    args = ap.parse_args()
    root = Path(__file__).resolve().parents[1]
    timeline = json.loads(args.pose_json.read_text(encoding="utf-8"))
    static = json.loads((root.parent / "t3b_hd/assets/models/aya_ge_matrices.json").read_text(encoding="utf-8"))
    sm = static["bones"]["bone4"]["matrix"]
    pivot = [.95, 1.90, 0.0]; grip = [.09, 1.79, .13]; muzzle = [.30, 1.795, .106]; muzzle2 = [.30, 1.795, .306]
    correction = [.742355, .029960, -.252845]; yaw = math.radians(155.0)
    by_pose = defaultdict(list)
    for fr in timeline["frames"]:
        ch = fr["channels"]["arm_right_hand"]; m = mix_matrix(sm, ch["matrix"])
        g = apply_pose(rot_y(grip, grip, yaw), m, pivot); mz = apply_pose(rot_y(muzzle, grip, yaw), m, pivot); mz2 = apply_pose(rot_y(muzzle2, grip, yaw), m, pivot)
        g = [g[i] + correction[i] for i in range(3)]; mz = [mz[i] + correction[i] for i in range(3)]; mz2 = [mz2[i] + correction[i] for i in range(3)]
        direction = norm(sub(mz2, mz)); box = ch["bbox"]; hand = [(box[0][i] + box[1][i]) * .5 for i in range(3)]; axis = norm([m[0][2], m[1][2], m[2][2]])
        by_pose[fr["pose"]].append({"grip": math.sqrt(sum((g[i] - hand[i]) ** 2 for i in range(3))), "forward": math.degrees(math.acos(max(-1, min(1, dot(direction, axis))))), "direction": direction})
    report = {"schema": "aya-action-pose-error/v1", "poses": {}}
    for pose, rows in by_pose.items():
        jitter = []
        for i in range(1, len(rows)):
            cosine = max(-1.0, min(1.0, dot(rows[i]["direction"], rows[i - 1]["direction"])))
            jitter.append(math.degrees(math.acos(cosine)))
        report["poses"][pose] = {"frames": len(rows), "grip_mean": sum(x["grip"] for x in rows) / len(rows), "grip_max": max(x["grip"] for x in rows), "forward_mean_deg": sum(x["forward"] for x in rows) / len(rows), "forward_max_deg": max(x["forward"] for x in rows), "jitter_mean_deg": sum(jitter) / len(jitter) if jitter else 0.0, "jitter_max_deg": max(jitter) if jitter else 0.0}
    args.out_json.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    lines = ["# Aya 移动/瞄准/射击姿态 socket 误差", "", "参考仍是每帧 `arm_right_hand` weighted draw bbox；误差用于重制版 socket 校准，不等同原版私有 metadata。", ""]
    for pose, r in report["poses"].items(): lines.append(f"- `{pose}`：{r['frames']} 帧；grip 平均/最大 {r['grip_mean']:.5f}/{r['grip_max']:.5f}；枪口方向平均/最大 {r['forward_mean_deg']:.3f}°/{r['forward_max_deg']:.3f}°；抖动平均/最大 {r['jitter_mean_deg']:.3f}°/{r['jitter_max_deg']:.3f}°。")
    args.out_md.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(args.out_md.read_text(encoding="utf-8"))


if __name__ == "__main__": main()
