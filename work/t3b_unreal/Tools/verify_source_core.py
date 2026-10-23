"""Verify the UE-independent source core against frozen C replay outputs.

This compares saved output and source bits; it does not duplicate skinning or
claim an Unreal Engine build. Run from any directory after compiling probes.
"""
from __future__ import annotations

import csv
import hashlib
import itertools
import json
from pathlib import Path
import shutil
import struct
import subprocess

ROOT = Path(__file__).resolve().parents[1]
WORK = ROOT.parent
TOOLS = ROOT / "Tools"
ASSETS = WORK / "t3b_hd" / "assets"
FROZEN = WORK / "psp_parse" / "out"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def bits(value: float) -> int:
    return struct.unpack("<I", struct.pack("<f", value))[0]


def f32(value: float) -> float:
    return struct.unpack("<f", struct.pack("<f", value))[0]


def verify_conversions(row: dict[str, str], source: Path | None) -> None:
    pc = [f32(float(row[f"pc_{axis}"])) for axis in "xyz"]
    ue = [f32(float(row[f"ue_{axis}"])) for axis in "xyz"]
    # T3BSource::ToUE = (PC.z, -PC.x, PC.y) * 100 (left-handed UE, no mirroring).
    assert [bits(v) for v in ue] == [bits(f32(sign * pc[i] * 100)) for i, sign in ((2, 1), (0, -1), (1, 1))]
    if source is not None:
        units, floor = struct.unpack_from("<2f", source.read_bytes(), 44)
        original = [f32(float(row[axis])) for axis in "xyz"]
        local = [f32(original[0] * units), f32(f32(original[1] - floor) * units), f32(original[2] * units)]
        expected = [f32(f32(0 + f32(local[0] * 1)) + f32(local[2] * 0)), local[1], f32(f32(0 - f32(local[0] * 0)) + f32(local[2] * 1))]
        assert [bits(v) for v in pc] == [bits(v) for v in expected]


def verify_skin(name: str, source: Path, frozen: Path) -> dict:
    output = TOOLS / f"{name}_probe.csv"
    command = [str(TOOLS / "source_probe.exe"), "--skin", str(source.relative_to(WORK)), "--out", str(output.relative_to(WORK))]
    process = subprocess.run(command, cwd=WORK, capture_output=True, text=True, check=True)
    mismatch = 0
    maximum = 0.0
    count = 0
    units, floor = struct.unpack_from("<2f", source.read_bytes(), 44)
    with frozen.open(newline="", encoding="utf-8") as c_file, output.open(newline="", encoding="utf-8") as cpp_file:
        for c_row, cpp_row in itertools.zip_longest(csv.reader(c_file), csv.DictReader(cpp_file)):
            assert c_row is not None and cpp_row is not None, "probe coverage differs"
            assert (int(c_row[0]), int(c_row[1])) == (int(cpp_row["sample"]), int(cpp_row["index"]))
            expected = [f32(float(v)) for v in c_row[2:5]]
            actual = [f32(float(cpp_row[axis])) for axis in "xyz"]
            mismatch += sum(bits(a) != bits(b) for a, b in zip(actual, expected))
            maximum = max(maximum, *(abs(a - b) for a, b in zip(actual, expected)))
            pc = [f32(float(cpp_row[f"pc_{axis}"])) for axis in "xyz"]
            local = [f32(actual[0] * units), f32(f32(actual[1] - floor) * units), f32(actual[2] * units)]
            expected_pc = [f32(f32(0 + local[0]) + f32(local[2] * 0)), local[1], f32(f32(0 - f32(local[0] * 0)) + local[2])]
            assert [bits(v) for v in pc] == [bits(v) for v in expected_pc]
            verify_conversions(cpp_row, None)
            count += 1
    assert mismatch == 0, f"{name}: {mismatch} C/C++ component bit mismatches"
    return {"source": str(source), "source_sha256": sha(source), "frozen_c_probe": str(frozen), "frozen_c_probe_sha256": sha(frozen), "cpp_probe": str(output), "cpp_probe_sha256": sha(output), "vertices_compared": count, "component_bit_mismatches": mismatch, "max_absolute_original_unit_error": maximum, "pc_and_ue_conversion_bit_mismatches": 0, "probe_stdout": process.stdout.strip()}


def verify_scene() -> dict:
    source = ASSETS / "scenes/original_street/original_street.bin"
    output = TOOLS / "scene_probe.csv"
    process = subprocess.run([str(TOOLS / "source_probe.exe"), "--scene", str(source.relative_to(WORK)), "--out", str(output.relative_to(WORK))], cwd=WORK, capture_output=True, text=True, check=True)
    data = source.read_bytes()
    version, draws, vertices, materials = struct.unpack_from("<4I", data, 8)
    assert version == 1
    packets = [struct.unpack_from("<3I", data, 56 + i * 12) for i in range(draws)]
    lookup = [(draw, packet[2]) for draw, packet in enumerate(packets) for _ in range(packet[1])]
    assert len(lookup) == vertices
    count = 0
    with output.open(newline="", encoding="utf-8") as file:
        for index, row in enumerate(csv.DictReader(file)):
            assert int(row["sample"]) == 0 and int(row["index"]) == index
            assert (int(row["draw"]), int(row["material"])) == lookup[index]
            offset = 56 + draws * 12 + index * 24
            raw_bits = struct.unpack_from("<5I", data, offset)
            assert tuple(int(row[key]) for key in ("xbits", "ybits", "zbits", "ubits", "vbits")) == raw_bits
            assert tuple(int(row[key]) for key in "rgba") == tuple(data[offset + 20:offset + 24])
            assert tuple(bits(float(row[key])) for key in ("x", "y", "z", "u", "v")) == raw_bits
            assert all(bits(float(row[axis])) == bits(float(row[f"pc_{axis}"])) for axis in "xyz")
            verify_conversions(row, None)
            count += 1
    assert count == vertices
    return {"source": str(source), "source_sha256": sha(source), "cpp_probe": str(output), "cpp_probe_sha256": sha(output), "draws": draws, "vertices_compared": count, "materials": materials, "position_uv_rgba_bit_mismatches": 0, "ue_conversion_bit_mismatches": 0, "probe_stdout": process.stdout.strip()}


def main() -> None:
    compiler = shutil.which("g++")
    if compiler is None:
        raise RuntimeError("g++ is required for the standalone source core verification")
    flags = ["-O2", "-Wall", "-Wextra", "-Werror", "-ffp-contract=off", "-std=c++17"]
    implementation = "Source/T3BRemake/Private/T3BSourceData.cpp"
    for target in ("source_probe", "source_data_tests"):
        subprocess.run([compiler, *flags, "-o", f"Tools/{target}.exe", f"Tools/{target}.cpp", implementation], cwd=ROOT, capture_output=True, text=True, check=True)
    tests = subprocess.run([str(TOOLS / "source_data_tests.exe")], cwd=ROOT, capture_output=True, text=True, check=True)
    report = {
        "schema": "t3b-unreal-independent-source-core/v1",
        "passed": True,
        "scope": "standalone C++ source readers, arbitrary affine replay, PC and UE coordinate conversion",
        "unreal_engine_build_tested": False,
        "standalone_build": {"compiler": compiler, "compiler_version": subprocess.run([compiler, "--version"], capture_output=True, text=True, check=True).stdout.splitlines()[0], "flags": flags},
        "source_core_sha256": {path.name: sha(path) for path in (ROOT / "Source/T3BRemake/Private/T3BSourceData.h", ROOT / "Source/T3BRemake/Private/T3BSourceData.cpp")},
        "probe_executable_sha256": sha(TOOLS / "source_probe.exe"),
        "test_executable_sha256": sha(TOOLS / "source_data_tests.exe"),
        "unit_test_stdout": tests.stdout.strip(),
        "scene": verify_scene(),
        "skins": {
            "aya_fire": verify_skin("aya_fire", ASSETS / "models/clips/aya_fire_reverse_capture.bin", FROZEN / "AYA_REVERSE_C_RUNTIME_PROBES/aya_fire_cpu_probe.csv"),
            "weapon_fire": verify_skin("weapon_fire", ASSETS / "models/clips/weapon_fire_reverse_capture.bin", FROZEN / "AYA_REVERSE_C_RUNTIME_PROBES/weapon_fire_cpu_probe.csv"),
            "enemy": verify_skin("enemy", ASSETS / "models/original_actor_source.bin", FROZEN / "ORIGINAL_ACTOR_SOURCE_SPAWN_C_RUNTIME_PROBES/original_actor_cpu_probe.csv"),
        },
        "limitations": ["Does not establish Unreal Engine compilation, GPU rendering, materials, collision, or gameplay.", "C/C++ pose comparison covers all 60 stored samples; between-sample interpolation and clamp are covered by explicit affine unit tests."]
    }
    target = TOOLS / "source_core_verification.json"
    target.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({"passed": True, "scene_vertices": report["scene"]["vertices_compared"], "skin_vertices": {name: value["vertices_compared"] for name, value in report["skins"].items()}, "report": str(target)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
