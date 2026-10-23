"""Summarize the render-relevant Aya bone/socket mapping used by M1."""
from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    timeline = json.loads((root / "out/aya_ge_hierarchy_timeline.json").read_text(encoding="utf-8"))
    pose = json.loads((root / "out/AYA_POSE_VARIANTS.json").read_text(encoding="utf-8"))
    channels = defaultdict(lambda: {"draw": set(), "slots": set()})
    for frame in timeline["frames"]:
        for name, item in frame["channels"].items():
            channels[name]["draw"].add(item["draw"])
            channels[name]["slots"].update(item["palette_slots"])
    pose_channels = defaultdict(lambda: {"draw": set(), "slots": set()})
    for frame in pose["frames"]:
        for name, item in frame["channels"].items():
            pose_channels[name]["draw"].add(item["draw"])
            pose_channels[name]["slots"].update(item["palette_slots"])
    lines = [
        "# Aya 骨骼层级、武器挂点与枪口映射",
        "",
        "映射单位是 PPSSPP draw-local weighted palette；draw/slot 不是跨 draw 的全局骨骼编号。11 个通道是当前可验证的渲染层级。",
        "",
        "| 通道 | 24 帧代表 draw | 24 帧 palette slot | 40 帧姿态 draw 范围 | 作用 |",
        "|---|---:|---|---|---|",
    ]
    roles = {
        "spine_lower": "下脊柱",
        "spine_upper": "上脊柱",
        "head": "头部",
        "arm_left_upper": "左上臂",
        "arm_left_forearm": "左前臂",
        "arm_left_hand": "左手",
        "arm_right_upper": "右上臂",
        "arm_right_forearm": "右前臂",
        "arm_right_hand": "右手；weapon mount 与 muzzle 的驱动通道",
        "leg_left": "左腿",
        "leg_right": "右腿",
    }
    for name in timeline["channels"]:
        base = channels[name]; extra = pose_channels[name]
        lines.append(f"| `{name}` | {min(base['draw'])}–{max(base['draw'])} | {','.join(str(x) for x in sorted(base['slots']))} | {min(extra['draw'])}–{max(extra['draw'])} | {roles[name]} |")
    lines += [
        "",
        "## Weapon socket",
        "",
        "- `grip=(0.090, 1.790, 0.130)`；`muzzle=(0.300, 1.795, 0.106)`；第二枪口点 `muzzle2=(0.300, 1.795, 0.306)`。",
        "- 三个点都使用 `arm_right_hand` 的同一 posed matrix，再应用 `weapon yaw correction=155°` 和 `mount correction=(+0.742355,+0.029960,-0.252845)`。",
        "- 枪口方向为 `normalize(muzzle2-muzzle)`；射线、遮挡测试和 muzzle flash 使用同一方向。",
        "- 24 帧基准误差：grip 平均/最大 `0.09901/0.30511`，枪口方向平均/最大 `9.592°/20.678°`。40 帧输入姿态报告见 `AYA_POSE_VARIANT_ERROR.md`。",
        "",
        "这些名称是由 weighted draw 的空间区域和连续 GE 矩阵稳定性恢复的工程语义，不是 EBOOT 中可直接读出的原始骨骼字符串。",
    ]
    out = root / "out/AYA_SOCKET_BONE_MAPPING.md"
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(out.read_text(encoding="utf-8"))


if __name__ == "__main__":
    main()
