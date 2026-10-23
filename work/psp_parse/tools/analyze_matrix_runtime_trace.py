"""Map runtime matrix wrapper traces back to static callers and type IDs."""
from __future__ import annotations

import argparse
import json
import re
from collections import Counter, defaultdict
from pathlib import Path

from disasm_aya_eboot import load_symbols, BASE

PATTERN = re.compile(r"BKP PC=([0-9a-f]+): matrix(?: pc=([0-9a-f]+))? a0=([0-9a-f]+) a1=([0-9a-f]+) a2=([0-9a-f]+) a3=([0-9a-f]+) ra=([0-9a-f]+)")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("trace", type=Path)
    ap.add_argument("calls", type=Path)
    ap.add_argument("map", type=Path)
    ap.add_argument("out_json", type=Path)
    ap.add_argument("out_md", type=Path)
    args = ap.parse_args()

    trace = json.loads(args.trace.read_text(encoding="utf-8"))
    calls = json.loads(args.calls.read_text(encoding="utf-8"))
    call_map = {int(row["callsite"], 0): row for row in calls["call_sites"]}
    symbols = load_symbols(args.map)
    rows = []
    unmatched = Counter()
    for item in trace.get("logs", []):
        match = PATTERN.search(item.get("message", ""))
        if not match:
            continue
        pc_text, logged_pc_text, a0_text, a1_text, a2_text, a3_text, ra_text = match.groups()
        pc = int(pc_text, 16)
        logged_pc = int(logged_pc_text, 16) if logged_pc_text else pc
        a0, a1, a2, a3, ra = (int(x, 16) for x in (a0_text, a1_text, a2_text, a3_text, ra_text))
        caller = ra - 8
        row = call_map.get(caller)
        if row is None:
            unmatched[caller] += 1
        symbol = "?"
        previous = [entry for entry in symbols if entry[0] <= caller]
        if previous:
            symbol = previous[-1][2]
        rows.append({
            "pc": pc,
            "wrapper_callsite": caller,
            "wrapper_callsite_hex": hex(caller),
            "return_address": ra,
            "a0_type": a0,
            "a1_matrix_selector": a1,
            "a2_aux": a2,
            "a3_aux": a3,
            "caller_symbol": symbol,
            "static_callsite": row,
            "timestamp": item.get("timestamp"),
        })

    by_call = defaultdict(Counter)
    by_type = Counter()
    by_selector = Counter()
    for row in rows:
        by_call[row["wrapper_callsite_hex"]][row["a0_type"]] += 1
        by_type[row["a0_type"]] += 1
        by_selector[row["a1_matrix_selector"]] += 1
    caller_summary = []
    for caller, counts in sorted(by_call.items(), key=lambda pair: (-sum(pair[1].values()), pair[0])):
        caller_summary.append({"callsite": caller, "events": sum(counts.values()), "type_counts": dict(sorted(counts.items()))})
    result = {
        "schema": "aya-matrix-runtime-call-map/v1",
        "trace": str(args.trace),
        "events": len(rows),
        "unique_callers": len(by_call),
        "unmatched_return_addresses": {hex(k): v for k, v in unmatched.items()},
        "type_counts": dict(sorted(by_type.items())),
        "matrix_selector_counts": dict(sorted(by_selector.items())),
        "caller_summary": caller_summary,
        "events_detail": rows,
    }
    args.out_json.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    lines = [
        "# Aya 矩阵上传运行时调用映射",
        "",
        f"- 断点事件：{len(rows)}；唯一 caller：{len(by_call)}；未匹配 `$ra-8`：{sum(unmatched.values())}。",
        f"- `a0` 上传类型：" + ", ".join(f"{k}:{v}" for k, v in sorted(by_type.items())),
        f"- `a1` selector：" + ", ".join(f"0x{k:x}:{v}" for k, v in sorted(by_selector.items())),
        "",
        "`wrapper_callsite = $ra - 8`；每一行再与静态调用点的寄存器来源和最近符号关联。",
        "",
        "## 运行时可见调用者",
    ]
    for item in caller_summary:
        lines.append(f"- `{item['callsite']}`：{item['events']} 次，types=" + ", ".join(f"{k}:{v}" for k, v in item["type_counts"].items()))
    args.out_md.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"events={len(rows)} callers={len(by_call)} unmatched={sum(unmatched.values())}")
    print(f"wrote {args.out_json}")
    print(f"wrote {args.out_md}")


if __name__ == "__main__":
    main()
