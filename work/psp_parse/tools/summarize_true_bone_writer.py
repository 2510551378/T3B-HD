from __future__ import annotations

import json
from pathlib import Path

root = Path(__file__).resolve().parents[1]
trace = json.loads((root / "out/AYA_BONE_PAYLOAD_PAUSED.json").read_text(encoding="utf-8"))
objects = {}
for row in trace["rows"]:
    key = (row["a0"], row["sourceBase"])
    objects[key] = {
        "object": hex(row["a0"]),
        "source_base": hex(row["sourceBase"]),
        "bone_count": row.get("boneCount"),
        "record_offset": hex(row["a2"]),
        "matrix_block_first32": row.get("matrixBlock", [])[:32],
    }
report = {
    "schema": "aya-true-bone-writer/v1",
    "static": {
        "per_draw_caller": "0x08b46e1c",
        "per_draw_caller_target": "0x08b4f618",
        "bone_build_payload_caller": "0x08b4f6e8",
        "bone_build_payload_target": "0x08b5230c",
        "bone_batch_payload_caller": "0x08b5430c",
        "bone_slot_writer": "0x08b4f77c",
        "bone_matrix_read_entry": "0x08b52330",
        "bone_matrix_commit": "0x08b5251c",
        "bone_flag_writer": "0x08b52554",
        "bone_payload_function_cluster": "0x08b5230c",
        "source_object_fields": {
            "bone_record_table": "object+0x3c4",
            "bone_table_meta": "object+0x3e8",
            "record_stride": "0x130",
            "matrix_offsets": ["+0x40", "+0x80"],
        },
    },
    "runtime_objects": list(objects.values()),
    "aya_mapping": {
        "aya_object_evidence": "runtime object with bone_count=44",
        "weapon_or_auxiliary_evidence": "runtime object with bone_count=3",
        "right_hand_ge_draw": 1037,
        "right_hand_palette_slot": 12,
        "socket_source": "right_hand GE channel; weapon mount and muzzle use same posed transform",
    },
}
(root / "out/AYA_TRUE_BONE_WRITER_ANALYSIS.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
lines = [
    "# 原版 GE BONE 真正写入路径",
    "",
    "静态代码已经从通用 command emitter 区分出真正的 BONE 路径：",
    "",
    "- `0x08b46e1c` 是逐对象/逐 draw caller，将对象指针放入 `$a0` 后调用 `0x08b4f618`；",
    "- `0x08b4f6e8` 是 BONE build 内部的矩阵 build caller，调用 `0x08b5230c`，最终在 `0x08b5251c` 完成 record payload；",
    "- 另有 `0x08b5430c` 批处理路径调用同一个 `0x08b5230c`，但它不是本次右手逐 draw 绑定所使用的 caller；",
    "- `0x08b4f77c`：构造 `0x2A` bone-slot command；它位于 `z_un_08b4f618` 的 per-bone record loop。",
    "- `0x08b52330`：读取 `object+0x3c4` 的 record，stride 为 `0x130`，矩阵输入位于 `+0x40/+0x80`；`0x08b5251c` 完成该 record 的 `0x2B` float24 写入到 `record+0xc0`。",
    "- `0x08b52554` 是后续 flag/clear 分支，不是本次矩阵 payload writer。",
    "- runtime breakpoint 在 `0x08b52554` 看到两个源对象：一个 `bone_count=44`，另一个 `bone_count=3`。前者对应 Aya，后者是武器/附属对象候选。",
    "- 同帧 GE weighted draw 对齐确认 Aya 右手为 draw `1037`、palette slot `12`；M1 的 weapon mount/grip/muzzle 继续统一使用该右手通道。",
    "",
    "右手的原版 slot 语义由 GE draw/palette 证据确认；44-bone source object 的 record index 36 是实际右手矩阵数据源。`0x8b5e3a8` 的 selector record 不参与右手矩阵绑定。",
]
(root / "out/AYA_TRUE_BONE_WRITER_ANALYSIS.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
print((root / "out/AYA_TRUE_BONE_WRITER_ANALYSIS.md").read_text(encoding="utf-8"))
