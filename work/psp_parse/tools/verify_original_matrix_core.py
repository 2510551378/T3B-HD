from __future__ import annotations

import hashlib
import json
import struct
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
EXE = ROOT / "work/t3b_unreal/Validation/ge_original_matrix_probe_new.exe"
OUT = ROOT / "work/t3b_unreal/Validation/original_matrix_core_v1/verification.json"


def f32(value: float) -> float:
    return struct.unpack("<f", struct.pack("<f", float(value)))[0]


def bits(value: float) -> int:
    return struct.unpack("<I", struct.pack("<f", f32(value)))[0]


def multiply(a: list[float], b: list[float]) -> list[float]:
    out = [0.0] * 16
    for col in range(4):
        for row in range(4):
            total = 0.0
            for k in range(4):
                total = f32(total + f32(a[k * 4 + row] * b[col * 4 + k]))
            out[col * 4 + row] = total
    return out


def expected() -> list[str]:
    scalar = f32(0.625)
    p30 = [f32(2.0), f32(3.0), f32(4.0)]
    input_matrix = [f32((int((i * 7 + 3) % 11) - 5) / 3) for i in range(16)]
    parent = [f32((int((i * 5 + 1) % 13) - 6) / 4) for i in range(16)]
    global_matrix = [f32((int((i * 3 + 2) % 17) - 8) / 5) for i in range(16)]

    scaled = input_matrix[:]
    for col in range(3):
        for row in range(4):
            scaled[col * 4 + row] = f32(scaled[col * 4 + row] * scalar)
    mode0 = multiply(parent, scaled)

    mode1 = [0.0] * 16
    for col in range(3):
        for row in range(3):
            total = 0.0
            for k in range(3):
                scaled_value = f32(f32(input_matrix[col * 4 + k] * scalar) * p30[col])
                total = f32(total + f32(global_matrix[k * 4 + row] * scaled_value))
            mode1[col * 4 + row] = total
    for row in range(4):
        total = 0.0
        for k in range(4):
            total = f32(total + f32(parent[k * 4 + row] * input_matrix[12 + k]))
        mode1[12 + row] = total
    mode1[3] = mode1[7] = mode1[11] = 0.0
    return [
        " ".join(f"{bits(value):x}" for value in mode0),
        " ".join(f"{bits(value):x}" for value in mode1),
    ]


def main() -> None:
    actual = [" ".join(line.split()) for line in subprocess.check_output([str(EXE)], text=True).splitlines()]
    wanted = expected()
    if actual != wanted:
        raise SystemExit(json.dumps({"status": "failed", "actual": actual, "expected": wanted}, indent=2))

    source_files = []
    for rel in (
        "work/t3b_unreal/Source/T3BRemake/Public/T3BGEOriginalMatrix.h",
        "work/t3b_unreal/Source/T3BRemake/Private/T3BGEOriginalMatrix.cpp",
        "work/t3b_unreal/Tools/ge_original_matrix_probe.cpp",
        "work/psp_parse/tools/verify_original_matrix_core.py",
    ):
        path = ROOT / rel
        data = path.read_bytes()
        source_files.append({"file": rel, "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()})

    report = {
        "schema": "t3b-original-matrix-core/v1",
        "status": "passed",
        "cases": 2,
        "output_words": 32,
        "outputs_bits": wanted,
        "source_files": source_files,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
