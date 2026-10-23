"""Compare generic GE command-emitter callers across shooting/aiming actions."""
from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from pathlib import Path

PATTERN = re.compile(r"BKP PC=([0-9a-f]+): matrix(?: pc=([0-9a-f]+))? a0=([0-9a-f]+) a1=([0-9a-f]+) a2=([0-9a-f]+) a3=([0-9a-f]+) ra=([0-9a-f]+)")

HINTS = {
    "0x8b2ce28": "vmmul 后提交 selector 0x19e；通用模型/变换 command 路径",
    "0x8b300d8": "遍历 0x50-byte 记录并提交 selector 0x81；对象/材质记录路径",
    "0x8b2dd70": "紧邻 CLUT pointer load 与 draw-record 循环；材质/绘制状态候选",
    "0x8b54c50": "写回 0x20-byte payload 后提交 type=6；动态资源上传候选",
    "0x8afa6b8": "使用对象表计数与 0x119 selector；索引对象状态候选",
    "0x8b5e3a8": "按 0x10-byte 记录循环，a0/a1/a2/t0 均来自运行时记录；最接近逐 draw 动态状态",
    "0x8bba20c": "低层 wrapper 转发 a2/a3；无法从静态参数命名语义资源",
}


def main() -> None:
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("out_dir", type=Path)
    ap.add_argument("calls", type=Path)
    ap.add_argument("out_json", type=Path)
    ap.add_argument("out_md", type=Path)
    args = ap.parse_args()
    calls = json.loads(args.calls.read_text(encoding="utf-8"))
    static = {int(x["callsite"], 0): x for x in calls["call_sites"]}
    result_actions = {}
    all_counts = Counter()
    for path in sorted(args.out_dir.glob("AYA_MATRIX_ACTION_*.json")):
        if path.name in {"AYA_MATRIX_ACTION_TRACE.json"}:
            continue
        action = path.stem.removeprefix("AYA_MATRIX_ACTION_")
        data = json.loads(path.read_text(encoding="utf-8"))
        counts = Counter(); types = Counter(); selectors = Counter()
        for item in data.get("logs", []):
            match = PATTERN.search(item.get("message", ""))
            if not match:
                continue
            a0, a1, a2, a3, ra = (int(x, 16) for x in match.groups()[2:])
            caller = ra - 8
            key = hex(caller)
            counts[key] += 1; types[a0] += 1; selectors[a1] += 1; all_counts[key] += 1
        result_actions[action] = {"logs": len(data.get("logs", [])), "caller_counts": dict(counts), "type_counts": dict(types), "selector_counts": dict(selectors)}
    result = {"schema": "aya-matrix-action-trace/v1", "actions": result_actions, "aggregate_caller_counts": dict(all_counts)}
    args.out_json.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    lines = [
        "# Aya 射击/瞄准动作的 GE command-emitter 交叉验证",
        "",
        "这些 caller 调用的是相邻的 `z_un_08bfff98` 通用 GE command emitter，不等同于骨骼编号；语义提示来自 caller 前后的静态指令，只作为候选。真正的骨骼语义仍以 GE `BONE` weighted draw 映射为准。",
        "",
        "## 各动作的 caller 计数",
    ]
    for action, item in result_actions.items():
        lines.append(f"- `{action}`（{item['logs']} 条 log）：" + ", ".join(f"{k}:{v}" for k, v in sorted(item["caller_counts"].items())))
    lines += ["", "## 观察到的 caller 证据"]
    observed = sorted(all_counts, key=lambda key: (-all_counts[key], key))
    for key in observed:
        numeric = int(key, 0)
        row = static.get(numeric)
        symbol = "?"
        if row:
            symbol = row.get("instructions", [{}])[0].get("op_str", "?")
        lines.append(f"- `{key}`：累计 {all_counts[key]} 次；{HINTS.get(key, '未建立可靠语义提示')}。静态首条 setup：{symbol}")
    lines += ["", "结论：动作输入改变了若干逐 draw 动态 caller 的频率（尤其 `0x8b5e3a8` 在 rtrigger/strafe 状态显著增加），但没有证据把某个 emitter caller 单独命名为 Aya 某根骨骼、weapon mount 或 muzzle。后者仍由 `arm_right_hand` GE channel、weapon transform 与枪口误差报告共同确定。"]
    args.out_md.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"actions={len(result_actions)} -> {args.out_json}")
    print(f"wrote {args.out_md}")


if __name__ == "__main__":
    main()
