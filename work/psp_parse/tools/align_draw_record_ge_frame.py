"""Align 0x8b5e3a8 log intervals with the same-frame arm_right_hand GE draw."""
from __future__ import annotations

import json
import math
import re
from collections import Counter
from pathlib import Path

PATTERN = re.compile(r"draw-record a0=([0-9a-f]+) a1=([0-9a-f]+) a2=([0-9a-f]+) a3=([0-9a-f]+) t0=([0-9a-f]+) s3=([0-9a-f]+)")


def main() -> None:
    import argparse
    ap = argparse.ArgumentParser(); ap.add_argument("manifest", type=Path); ap.add_argument("hierarchy", type=Path); ap.add_argument("out_json", type=Path); ap.add_argument("out_md", type=Path); args = ap.parse_args()
    manifest = json.loads(args.manifest.read_text(encoding="utf-8")); hierarchy = json.loads(args.hierarchy.read_text(encoding="utf-8"))
    aligned = []
    previous = None
    for frame, ge in zip(manifest["frames"], hierarchy["frames"]):
        logs = manifest["logs"][frame["logStart"]:frame["logEnd"]]
        signatures = Counter()
        for item in logs:
            match = PATTERN.search(item["message"])
            if match:
                values = tuple(int(x, 16) for x in match.groups())
                signatures[values] += 1
        hand = ge["channels"]["arm_right_hand"]
        matrix = hand["matrix"]
        delta = None if previous is None else math.sqrt(sum((matrix[i] - previous[i]) ** 2 for i in range(9)))
        previous = matrix
        aligned.append({"frame": frame["frame"], "log_count": sum(signatures.values()), "record_signatures": [{"a0": a0, "a1": a1, "a2": a2, "a3": a3, "t0": t0, "s3": s3, "count": count} for (a0, a1, a2, a3, t0, s3), count in signatures.items()], "arm_right_hand_draw": hand["draw"], "arm_right_hand_palette_slots": hand["palette_slots"], "arm_right_hand_matrix_first9": matrix[:9], "arm_right_hand_matrix_delta": delta})
    result = {"schema": "aya-draw-record-ge-alignment/v1", "target": "0x08b5e3a8", "frames": aligned}
    args.out_json.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    lines = ["# `0x8b5e3a8` 与 arm_right_hand GE draw 对齐", "", "每行使用同一 `gpu.record.dump` frame 的 log 区间和 `arm_right_hand` weighted draw。若 record 是右手矩阵上传，其参数应随右手矩阵变化；本批样本中 record signature 保持不变，而右手矩阵显著变化。", ""]
    for row in aligned:
        sig = "; ".join(f"a0={x['a0']},a1=0x{x['a1']:x},a2={x['a2']},t0=0x{x['t0']:x},s3=0x{x['s3']:x}×{x['count']}" for x in row["record_signatures"])
        delta = "-" if row["arm_right_hand_matrix_delta"] is None else f"{row['arm_right_hand_matrix_delta']:.4f}"
        lines.append(f"- frame {row['frame']:02d}：records={row['log_count']} [{sig or 'none'}]；arm_right_hand draw={row['arm_right_hand_draw']} slot={row['arm_right_hand_palette_slots']} matrix_delta={delta}")
    lines += ["", "结论：`0x8b5e3a8` 的记录没有显示出右手矩阵或 weapon muzzle 的逐帧变化；它是逐 draw command state。M1 继续通过 `arm_right_hand` GE channel 驱动 weapon mount/muzzle，不能把该 record 直接当作右手骨骼矩阵。"]
    args.out_md.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(args.out_md.read_text(encoding="utf-8"))


if __name__ == "__main__": main()
