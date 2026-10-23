"""Map dl_write_matrix paused samples to the 65 static wrapper callers."""
from __future__ import annotations

import json
from collections import Counter, defaultdict
from pathlib import Path

from disasm_aya_eboot import load_symbols


def main() -> None:
    import argparse
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
    for sample in trace["rows"]:
        saved = int(sample["savedCallerRa"])
        callsite = saved - 8
        static = call_map.get(callsite)
        if static is None:
            unmatched[callsite] += 1
        previous = [entry for entry in symbols if entry[0] <= callsite]
        symbol = previous[-1][2] if previous else "?"
        rows.append({**sample, "callsite": callsite, "callsite_hex": hex(callsite), "caller_symbol": symbol, "static_callsite": static})
    by_call = defaultdict(Counter)
    by_type = Counter()
    for row in rows:
        by_call[row["callsite_hex"]][row["a1"]] += 1
        by_type[row["a1"]] += 1
    summary = []
    for callsite, selectors in sorted(by_call.items(), key=lambda x: (-sum(x[1].values()), x[0])):
        row = next(item for item in rows if item["callsite_hex"] == callsite)
        summary.append({"callsite": callsite, "symbol": row["caller_symbol"], "events": sum(selectors.values()), "matrix_type_counts": dict(sorted(selectors.items())), "static": row["static_callsite"]})
    result = {
        "schema": "aya-matrix-paused-call-map/v1",
        "trace": str(args.trace),
        "samples": len(rows),
        "unique_callers": len(by_call),
        "unmatched_callers": {hex(k): v for k, v in unmatched.items()},
        "matrix_type_counts": dict(sorted(by_type.items())),
        "caller_summary": summary,
        "samples_detail": rows,
    }
    args.out_json.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    lines = [
        "# Aya `dl_write_matrix` 运行时 caller 映射",
        "",
        f"- 暂停采样：{len(rows)}；唯一 caller：{len(by_call)}；未匹配：{sum(unmatched.values())}。",
        "- `dl_write_matrix` 的 `a1` 类型计数：" + ", ".join(f"{k}:{v}" for k, v in sorted(by_type.items())),
        "- caller = wrapper 保存的 `$ra - 8`；矩阵类型取 writer 入口 `$a1`。",
        "",
        "## 已观察 caller",
    ]
    for item in summary:
        lines.append(f"- `{item['callsite']}` `{item['symbol']}`：{item['events']} 次，matrix types=" + ", ".join(f"{k}:{v}" for k, v in item["matrix_type_counts"].items()))
    args.out_md.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"samples={len(rows)} callers={len(by_call)} unmatched={sum(unmatched.values())}")
    print(f"wrote {args.out_json}")
    print(f"wrote {args.out_md}")


if __name__ == "__main__":
    main()
