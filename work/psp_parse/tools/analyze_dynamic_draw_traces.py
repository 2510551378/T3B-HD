"""Summarize 0x8b5e3a8 draw-record traces and compare action stability."""
from __future__ import annotations

import json
from collections import Counter
from pathlib import Path


def main() -> None:
    import argparse
    ap = argparse.ArgumentParser(); ap.add_argument("trace_dir", type=Path); ap.add_argument("out_json", type=Path); ap.add_argument("out_md", type=Path); args = ap.parse_args()
    actions = {}
    for path in sorted(args.trace_dir.glob("AYA_DYNAMIC_DRAW_*.json")):
        data = json.loads(path.read_text(encoding="utf-8")); rows = data.get("rows", [])
        signatures = Counter()
        for row in rows:
            sig = (row["a0"], row["a1"], row["a2"], row["recordWords"][1], row["recordWords"][3])
            signatures[sig] += 1
        actions[path.stem.removeprefix("AYA_DYNAMIC_DRAW_")] = {"rows": len(rows), "signatures": [{"a0": a0, "a1_selector": a1, "a2": a2, "record_word1": w1, "record_word3": w3, "count": n} for (a0, a1, a2, w1, w3), n in signatures.items()], "s3_bases": sorted({row["s3"] for row in rows}), "s1_values": sorted({row["s1"] for row in rows})}
    result = {"schema": "aya-dynamic-draw-summary/v1", "target": "0x08b5e3a8", "actions": actions}
    args.out_json.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    lines = [
        "# `0x8b5e3a8` 逐 draw 动态路径",
        "",
        "该 callsite 的 live 参数来自 `s3` 的 0x10-byte record：`a0=*(s3+0)`, `a2=*(s3+8)`, `t0=*(s3+0xc)`, `a1=s1`。在本次六组姿态中，`a1` 是 selector，不是 Aya 骨骼矩阵地址；因此该路径目前只能证明逐 draw GE command 状态，不能直接命名为右手骨骼或 muzzle socket。",
        "",
    ]
    for name, item in actions.items():
        sig = ", ".join(f"(a0={x['a0']},a1=0x{x['a1_selector']:x},a2={x['a2']},w1=0x{x['record_word1']:x},w3=0x{x['record_word3']:x})×{x['count']}" for x in item["signatures"])
        lines.append(f"- `{name}`：{item['rows']} samples；s1={','.join(hex(x) for x in item['s1_values'])}；records={sig}")
    lines += ["", "右手、weapon mount 和 muzzle 的可验证关联仍来自 `arm_right_hand` GE weighted draw channel；本批动作姿态的 socket 误差见 `AYA_ACTION_POSE_ERROR.md`。"]
    args.out_md.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(args.out_md.read_text(encoding="utf-8"))


if __name__ == "__main__": main()
