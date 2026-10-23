from __future__ import annotations

import json
import struct
from pathlib import Path

path = Path(__file__).resolve().parents[1] / "out/AYA_BONE_PAYLOAD_PAUSED.json"
data = json.loads(path.read_text(encoding="utf-8"))
seen = set()
for row in data["rows"]:
    key = (row["a0"], row["sourceBase"], row["a2"])
    if key in seen:
        continue
    seen.add(key)
    vals = [struct.unpack("<f", struct.pack("<I", x & 0xFFFFFFFF))[0] for x in row["matrixBlock"]]
    print(f"a0=0x{row['a0']:x} sourceBase=0x{row['sourceBase']:x} a2=0x{row['a2']:x}")
    print("  boneMeta=" + " ".join(f"0x{x & 0xffffffff:x}" for x in (row.get("boneMeta") or [])))
    for start in range(0, len(vals), 16):
        print("  " + " ".join(f"{x:.4f}" for x in vals[start:start + 16]))
