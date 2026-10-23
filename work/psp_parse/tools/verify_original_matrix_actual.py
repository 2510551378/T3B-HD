from __future__ import annotations

import json
import hashlib
import struct
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
MARKER = ROOT / "work/psp_parse/out/AYA_BONE_GE_ACTIONS/slot0_weapon_ge_emit_fire6_command_alias_v3/marker_ge_emit.json"
MATH = ROOT / "work/psp_parse/out/WEAPON_GE_MATRIX_MATH_20261020/actual_v3/matrix_math_verification.json"
EXE = ROOT / "work/t3b_unreal/Validation/ge_original_matrix_probe_new.exe"
OUT = ROOT / "work/t3b_unreal/Validation/original_matrix_core_v1/actual_sidecar_verification.json"


def f32(value: float) -> float:
    return struct.unpack("<f", struct.pack("<f", float(value)))[0]


def main() -> None:
    marker = json.loads(MARKER.read_text(encoding="utf-8"))
    math = json.loads(MATH.read_text(encoding="utf-8"))
    math_rows = {row["sample"]: row for row in math["captures"][0]["rows"]}
    lines: list[str] = []
    expected: list[list[int]] = []
    samples: list[int] = []
    for row in marker["rows"]:
        sample = row["sample"]
        mrow = math_rows[sample]
        matrix = row["matrix"]["entry"]
        # The captured node's state sidecar is the P object used by this
        # helper; its +0x30 XYZ scale is (1,1,1) in all six retained rows.
        state_file = Path(matrix["state"]["raw"]["file"])
        state = state_file.read_bytes()
        p30 = [struct.unpack("<f", state[offset : offset + 4])[0] for offset in (0x30, 0x34, 0x38)]
        assert all(value == 1.0 for value in p30), (sample, p30)
        input_values = matrix["input"]["f32"]
        parent_values = matrix["p60"]["f32"]
        global_values = matrix["globalMatrix"]["f32"]
        scalar = mrow["matrix"]["registers"]["f12_float"]
        values = [mrow["matrix"]["mode"], scalar, *p30, *input_values, *parent_values, *global_values]
        lines.append(" ".join(format(value, ".9g") if isinstance(value, float) else str(value) for value in values))
        expected.append(row["matrix"]["returned"]["output"]["words"])
        samples.append(sample)

    actual_lines = subprocess.check_output([str(EXE), "--stdin"], input="\n".join(lines) + "\n", text=True).splitlines()
    actual = [[int(word, 16) for word in line.split()] for line in actual_lines]
    assert len(actual) == len(expected), (len(actual), len(expected))
    mismatches = []
    for sample, got, want in zip(samples, actual, expected):
        if got != want:
            mismatches.append({"sample": sample, "different_words": [i for i, (a, b) in enumerate(zip(got, want)) if a != b]})
    report = {
        "schema": "t3b-original-matrix-core/actual-sidecar/v1",
        "status": "passed" if not mismatches else "failed",
        "samples": samples,
        "sample_count": len(samples),
        "output_words": 16 * len(samples),
        "all_output_words_bit_exact": not mismatches,
        "mismatches": mismatches,
        "input_provenance": "marker_ge_emit matrix input/p60/globalMatrix + state +0x30 XYZ + actual_v3 f12/mode",
        "input_files": [],
        "source_files": [],
    }
    for path in (MARKER, MATH):
        data = path.read_bytes()
        report["input_files"].append({"file": str(path.relative_to(ROOT)), "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()})
    for rel in (
        "work/t3b_unreal/Source/T3BRemake/Public/T3BGEOriginalMatrix.h",
        "work/t3b_unreal/Source/T3BRemake/Private/T3BGEOriginalMatrix.cpp",
        "work/t3b_unreal/Tools/ge_original_matrix_probe.cpp",
        "work/psp_parse/tools/verify_original_matrix_actual.py",
    ):
        path = ROOT / rel
        data = path.read_bytes()
        report["source_files"].append({"file": rel, "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()})
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    if mismatches:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
