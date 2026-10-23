"""Independently replay the retained original common-state opcode sequence.

Only the finite-data common branch 08b632cc..08b63494 is supported. This tool
does not import the algebra predictor, synthetic tests, emulator APIs or UI.
Memory and GPR inputs come from hash-verified retained runtime sidecars. VFPU
register indexing follows the pinned official PPSSPP v1.20.4 reference.
"""
from __future__ import annotations

import argparse
import collections
import hashlib
import json
import math
from pathlib import Path
import struct
import sys

ROOT = Path(__file__).resolve().parents[1]
BASE = 0x08804000
MODULE_SHA = "b5fc590366fc610f2cdd60104a4a28851bacd402c4600a4c296776e1dea0869f"
START, END = 0x08B632CC, 0x08B63498
GENERIC_RETURN, HELPER_RETURN = 0x08B630DC, 0x08B3E62C
REFERENCE_SHA = {
    "MIPSIntVFPU.cpp": "9a5f53df3b5f8c0a1b48424eae8430c729a89b89fab1d8926e553226dfcab876",
    "MIPSDisVFPU.cpp": "059adb5403b88b8fc22f4b85b3d3e1d1d58b5f9aa6e2798c1c17dd7a4d139f88",
    "MIPSVFPUUtils.cpp": "33c419ce793f5fc2db2cd825626541d823ce975c81784d67cd87fee53d115525",
    "MIPSVFPUUtils.h": "262d77fcc9dda7d63d56ff12cf93338d86bd4373f8fa57eb073c55a6b6cfc7e9",
    "MIPSTables.cpp": "960cdfcb001780ff8eb629eb8d0d1cd911dd96c3aa654bc3ad6c2860b5cca637",
}


def check(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sidecar(item: dict) -> bytes:
    raw = Path(item["file"]).read_bytes()
    check(len(raw) == item["bytes"] and sha(raw) == item["sha256"], "sidecar identity mismatch")
    return raw


def u2f(word: int) -> float:
    value = struct.unpack("<f", struct.pack("<I", word))[0]
    check(math.isfinite(value), "unsupported nonfinite VFPU input")
    return value


def f2u(value: float) -> int:
    check(math.isfinite(value), "unsupported nonfinite VFPU result")
    return struct.unpack("<I", struct.pack("<f", value))[0]


def f32(value: float) -> float:
    return u2f(f2u(value))


def vector_indices(reg: int, size: int) -> list[int]:
    """Official ReadVector physical layout, including single-row addressing."""
    matrix = ((reg >> 2) & 7) * 16
    column = reg & 3
    if size == 1:
        return [matrix + column * 4 + ((reg >> 5) & 3)]
    check(size in (2, 3, 4), "unsupported VFPU vector size")
    row = ((reg >> 6) & 1) if size == 3 else ((reg >> 5) & 2)
    if (reg >> 5) & 1:
        return [matrix + column + ((row + i) & 3) * 4 for i in range(size)]
    return [matrix + column * 4 + ((row + i) & 3) for i in range(size)]


class Replay:
    def __init__(self, module: bytes, row: dict):
        self.module = module
        self.context = row["genericReturn"]["sp"]
        self.state = row["statePointer"]
        self.memory: dict[int, int] = {}
        for start, raw, expected_size in ((self.context, sidecar(row["genericContext"]), 0x160), (self.state, sidecar(row["stateAfterGeneric"]), 0x1A4)):
            check(len(raw) == expected_size, "unexpected retained memory extent")
            for offset in range(0, len(raw), 4):
                address = start + offset
                word = struct.unpack_from("<I", raw, offset)[0]
                check(address not in self.memory or self.memory[address] == word, "inconsistent overlapping memory")
                self.memory[address] = word
        self.r = list(row["genericReturn"]["gpr"])
        check(len(self.r) == 32 and self.r[0] == 0, "invalid retained GPR shape")
        check(self.r[29] == self.context and self.r[31] == GENERIC_RETURN, "generic return ABI mismatch")
        check(self.r[16] == self.state + 0x60 and self.r[17] == self.state and self.r[18] == self.context + 0x40, "source/matrix pointer mismatch")
        check(self.r[20] == self.state + 0x10 and self.r[21] == self.state + 0x90, "position/state pointer mismatch")
        self.flags = self.read(self.context + 0x128)
        check(self.flags == struct.unpack_from("<I", sidecar(row["stateAfterGeneric"]), 0x154)[0], "live/saved flags differ")
        check(not (self.flags & (0x00200000 | 0x10)), "unsupported high-basis or terrain-height branch")
        check((self.r[30] & 0xFFFF) == ((self.flags >> 16) & 0xFFFF), "saved high flags do not select the common branch")
        # 631cc's taken BEQL delay slot loads these original flags before START.
        self.r[4] = self.flags
        self.v: list[float | None] = [None] * 128
        self.f: list[int | None] = [None] * 32
        # Selected helper's last VFPU op is vmmul at 08b445ec. It consumes
        # prefixes; subsequent verified helper/wrapper/copy64 tail is integer.
        # Official EatPrefixes resets S/T/D to passthrough/passthrough/zero.
        self.prefix = (0xE4, 0xE4, 0)
        self.trace: list[dict] = []

    def read(self, address: int) -> int:
        check(address in self.memory, f"unretained memory read {address:#x}")
        return self.memory[address]

    def write(self, address: int, word: int) -> None:
        check(address in self.memory, f"unretained memory write {address:#x}")
        self.memory[address] = word

    def reg(self, index: int) -> float:
        check(self.v[index] is not None, f"uninitialized VFPU register {index}")
        return float(self.v[index])

    def matrix_indices(self, reg: int, size: int) -> list[tuple[int, int]]:
        check(size in (3, 4), "unsupported matrix size")
        row = ((reg >> 6) & 1) if size == 3 else ((reg >> 5) & 2)
        matrix, column, transpose = ((reg >> 2) & 7) * 16, reg & 3, (reg >> 5) & 1
        result = []
        for j in range(size):
            for i in range(size):
                physical = matrix + (((row + i) & 3) * 4 + ((column + j) & 3) if transpose else ((column + j) & 3) * 4 + ((row + i) & 3))
                result.append((j * 4 + i, physical))
        return result

    def read_matrix(self, reg: int, size: int) -> list[float]:
        values = [0.0] * 16
        for logical, physical in self.matrix_indices(reg, size):
            values[logical] = self.reg(physical)
        return values

    def instruction(self, pc: int) -> int:
        check(START <= pc < END and pc % 4 == 0, "unsupported common-state control flow")
        return struct.unpack_from("<I", self.module, pc - BASE)[0]

    def execute(self, pc: int, delay_slot: bool = False) -> None:
        word = self.instruction(pc)
        op, rs, rt = word >> 26, (word >> 21) & 31, (word >> 16) & 31
        imm = word & 0xFFFF
        imm = imm - 0x10000 if imm & 0x8000 else imm
        vd, vs, vt = word & 127, (word >> 8) & 127, (word >> 16) & 127
        size = 1 + ((word >> 7) & 1) + 2 * ((word >> 15) & 1)
        name = ""
        if word == 0:
            name = "nop"
        elif op == 12:
            name = "andi"
            self.r[rt] = self.r[rs] & (word & 0xFFFF)
        elif op == 9:
            name = "addiu"
            self.r[rt] = (self.r[rs] + imm) & 0xFFFFFFFF
        elif op == 49:
            name = "lwc1"
            self.f[rt] = self.read((self.r[rs] + imm) & 0xFFFFFFFF)
        elif op == 17 and rs == 0:
            name = "mfc1"
            value = self.f[(word >> 11) & 31]
            check(value is not None, "uninitialized scalar FPR")
            self.r[rt] = int(value)
        elif op == 43:
            name = "sw"
            self.write((self.r[rs] + imm) & 0xFFFFFFFF, self.r[rt])
        elif op in (54, 62):
            name = "lv.q" if op == 54 else "sv.q"
            reg = ((word >> 16) & 31) | ((word & 1) << 5)
            offset = word & 0xFFFC
            offset = offset - 0x10000 if offset & 0x8000 else offset
            address = (self.r[rs] + offset) & 0xFFFFFFFF
            for component, index in enumerate(vector_indices(reg, 4)):
                if op == 54:
                    self.v[index] = u2f(self.read(address + 4 * component))
                else:
                    self.write(address + 4 * component, f2u(self.reg(index)))
        elif word == 0xF004A008:
            name = "vmmul.t M200,M000,M100"
            check(self.prefix == (0xE4, 0xE4, 0), "unsupported active VFPU prefix")
            source, target, result = self.read_matrix(vs, 3), self.read_matrix(vt, 3), [0.0] * 16
            # Int_Vmmul uses source[b*4+k] * target[a*4+k]. Raw VS=0x20
            # transposes the physical matrix; the resulting mathematical order
            # is selected_basis * local_basis, not the reverse.
            for a in range(3):
                for b in range(3):
                    total = 0.0
                    for k in range(4 if a == b == 2 else 3):
                        total = f32(total + f32(source[b * 4 + k] * target[a * 4 + k]))
                    result[a * 4 + b] = total
            for logical, physical in self.matrix_indices(vd, 3):
                self.v[physical] = result[logical]
        elif word == 0xF184A088:
            name = "vtfm4.q C200,E000,C100"
            check(self.prefix == (0xE4, 0xE4, 0), "unsupported active VFPU prefix")
            source = self.read_matrix(vs, 4)
            target = [self.reg(index) for index in vector_indices(vt, 4)]
            result = []
            for row in range(4):
                total = f32(source[row * 4] * target[0])
                for k in range(1, 4):
                    total = f32(total + f32(source[row * 4 + k] * target[k]))
                result.append(total)
            for index, value in zip(vector_indices(vd, 4), result):
                self.v[index] = value
        elif word in (0xD0060068, 0xD0060069, 0xD006006A, 0xD0070064, 0xD0070060):
            check(size == 1 and self.prefix == (0xE4, 0xE4, 0), "unsupported vector-init prefix or size")
            value = 1.0 if ((word >> 16) & 15) == 7 else 0.0
            name = "vone.s" if value else "vzero.s"
            self.v[vector_indices(vd, 1)[0]] = value
        elif word == 0x60018000:
            name = "vadd.t C000,C000,C010"
            check(self.prefix == (0xE4, 0xE4, 0), "unsupported active VFPU prefix")
            source = [self.reg(index) for index in vector_indices(vs, size)]
            target = [self.reg(index) for index in vector_indices(vt, size)]
            for index, a, b in zip(vector_indices(vd, size), source, target):
                self.v[index] = f32(a + b)
        else:
            raise ValueError(f"unsupported opcode {word:#010x} at {pc:#010x}")
        check(self.r[0] == 0, "unexpected write to MIPS zero register")
        self.trace.append({"pc": f"0x{pc:08x}", "word": f"0x{word:08x}", "instruction": name, "delay_slot": delay_slot})

    def run(self) -> bytes:
        pc = START
        while pc != END:
            check(len(self.trace) < 512, "unexpected replay instruction count")
            word = self.instruction(pc)
            if word >> 26 == 4:
                rs, rt = (word >> 21) & 31, (word >> 16) & 31
                take = self.r[rs] == self.r[rt]
                offset = word & 0xFFFF
                offset = offset - 0x10000 if offset & 0x8000 else offset
                self.trace.append({"pc": f"0x{pc:08x}", "word": f"0x{word:08x}", "instruction": "beq", "taken": take, "delay_slot": False})
                self.execute(pc + 4, True)
                pc = pc + 4 + 4 * offset if take else pc + 8
            else:
                self.execute(pc)
                pc += 4
        return b"".join(struct.pack("<I", self.read(self.state + 0x60 + i * 4)) for i in range(16))


def verify_capture(path: Path, module: bytes) -> dict:
    raw = path.read_bytes()
    capture = json.loads(raw)
    check(capture["schema"] == "weapon-marker-state-output-capture/v1", "unexpected capture schema")
    check(capture["failure"] is None and capture["inFlight"] is None, "incomplete capture")
    check(capture["module"]["sha256"] == MODULE_SHA and sha(Path(capture["module"]["file"]).read_bytes()) == MODULE_SHA, "capture module mismatch")
    required = {(0x08B44580, 0x210), (0x08B3E610, 0x12C), (0x08BBC93C, 0x43C), (0x08B62E98, 0x654), (0x08BFD23C, 0x44)}
    verified_ranges = set()
    for block in capture["codeIdentity"]["checks"]:
        at, size = block["address"], block["size"]
        check(at >= BASE and at + size <= BASE + len(module), "code identity range outside selected module")
        expected = module[at - BASE:at - BASE + size]
        for field in ("expected", "original", "decoded"):
            check(sidecar(block[field]) == expected, "retained original instruction bytes differ")
        check(block["verified"], "unverified code identity block")
        verified_ranges.add((at, size))
    check(capture["codeIdentity"]["verified"] and required <= verified_ranges, "required full helper/wrapper/common/copy identity missing")
    check(struct.unpack_from("<I", module, 0x08B445EC - BASE)[0] == 0xF02488A0, "last helper vmmul opcode changed")
    rows = []
    for row in capture["rows"]:
        check(row["ra"] == HELPER_RETURN and row["genericReturn"]["pc"] == GENERIC_RETURN, "unsupported helper/generic control flow")
        check(struct.unpack_from("<I", sidecar(row["entryStack"]), 0x84)[0] == 0x08BBCCD0, "unsupported upper helper caller")
        replay = Replay(module, row)
        result = replay.run()
        actual = sidecar(row["stateFinal"])
        check(len(actual) == 64 and actual == sidecar(row["stateAfterReturn"])[0x60:0xA0], "final state source binding mismatch")
        expected_words, actual_words = struct.unpack("<16I", result), struct.unpack("<16I", actual)
        expected_values, actual_values = struct.unpack("<16f", result), struct.unpack("<16f", actual)
        check(all(math.isfinite(value) for value in actual_values), "unsupported nonfinite final-state observation")
        differences = [{"component": i, "replayed": f"0x{a:08x}", "actual": f"0x{b:08x}"} for i, (a, b) in enumerate(zip(expected_words, actual_words)) if a != b]
        rows.append({"sample": row["sample"], "flags": f"0x{replay.flags:x}", "common_start": hex(START), "common_end_exclusive": hex(END), "replayed_sha256": sha(result), "actual_sha256": sha(actual), "bit_difference_components": len(differences), "bit_differences": differences, "max_absolute_difference": max(abs(a - b) for a, b in zip(expected_values, actual_values)), "instruction_count_including_delay_slots": len(replay.trace), "instructions": replay.trace})
    check(rows, "no retained completed rows")
    return {"capture": str(path.resolve()), "capture_sha256": sha(raw), "rows": rows, "rows_checked": len(rows), "flags_histogram": dict(collections.Counter(row["flags"] for row in rows)), "bit_difference_components": sum(row["bit_difference_components"] for row in rows), "max_absolute_difference": max(row["max_absolute_difference"] for row in rows), "passed": all(not row["bit_differences"] for row in rows)}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--capture", type=Path, action="append", required=True)
    parser.add_argument("--module", type=Path, default=ROOT / "raw/ULJM05798_module_08804000.bin")
    parser.add_argument("--reference-dir", type=Path, default=ROOT / "raw/ppsspp_v1.20.4_vfpu_reference")
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    module = args.module.read_bytes()
    check(sha(module) == MODULE_SHA, "selected original module SHA256 mismatch")
    manifest_raw = (args.reference_dir / "sources.json").read_bytes()
    manifest = json.loads(manifest_raw)
    check(manifest["tag"] == "v1.20.4" and len(manifest["files"]) == len(REFERENCE_SHA), "official reference tag/inventory mismatch")
    check({record["name"] for record in manifest["files"]} == set(REFERENCE_SHA), "incomplete/duplicated official reference inventory")
    sources = []
    for record in manifest["files"]:
        name = record["name"]
        check(name in REFERENCE_SHA, "unrecognized official reference file")
        url = f"https://raw.githubusercontent.com/hrydgard/ppsspp/v1.20.4/Core/MIPS/{name}"
        raw = (args.reference_dir / name).read_bytes()
        check(record["url"] == url and sha(raw) == record["sha256"] == REFERENCE_SHA[name] and len(raw) == record["bytes"], "official pinned source identity mismatch")
        sources.append({"file": str((args.reference_dir / name).resolve()), "url": url, "sha256": sha(raw), "bytes": len(raw)})
    report = {"schema": "weapon-state-independent-vfpu-opcode-replay/v1", "passed": True, "module": {"file": str(args.module.resolve()), "base": hex(BASE), "sha256": MODULE_SHA}, "verifier_sha256": sha(Path(__file__).read_bytes()), "reference_manifest_sha256": sha(manifest_raw), "official_sources": sources, "model": "finite binary32 multiply/add with a separate F32 rounding after every arithmetic operation; PPSSPP v1.20.4 interpreter default non-accurate-dot path", "prefix_evidence": "08b445ec vmmul consumes prefixes; selected helper/wrapper/copy64 return tail is integer, with no prefix setter before the common branch; official EatPrefixes sets S=T=0xe4,D=0.", "captures": [], "reproduction_argv": [sys.executable, "-X", "utf8", *sys.argv], "reproduction_cwd": str(Path.cwd()), "limits": ["Only entered common branch 08b632cc..08b63494 with flags&0x00200010 == 0 is supported.", "Unknown opcodes, unknown memory/register reads, nonfinite values and unsupported caller/prefix/high-basis/terrain paths are rejected, not skipped.", "Bit equality applies to retained observed inputs; it does not certify all VFPU/JIT rounding modes, denormal/NaN behavior, or unobserved flag combinations.", "No resource pointer, marker matrix or final state is given muzzle/FX semantics by this verifier."]}
    for path in args.capture:
        try:
            result = verify_capture(path, module)
        except (ValueError, KeyError, IndexError, struct.error) as error:
            result = {"capture": str(path.resolve()), "passed": False, "rejected": True, "reason": str(error)}
        report["captures"].append(result)
        report["passed"] = report["passed"] and result["passed"]
    checked = [row for capture in report["captures"] for row in capture.get("rows", [])]
    report["rows_checked"] = len(checked)
    report["flags_histogram"] = dict(collections.Counter(row["flags"] for row in checked))
    report["bit_difference_components"] = sum(row["bit_difference_components"] for row in checked)
    report["max_absolute_difference"] = max((row["max_absolute_difference"] for row in checked), default=None)
    observed_low = sorted({int(row["flags"], 16) & 0x60 for row in checked})
    report["observed_low_0x60_combinations"] = [hex(value) for value in observed_low]
    report["unobserved_low_0x60_combinations"] = [hex(value) for value in (0, 0x20, 0x40, 0x60) if value not in observed_low]
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({key: report[key] for key in ("passed", "rows_checked", "flags_histogram", "bit_difference_components", "max_absolute_difference", "unobserved_low_0x60_combinations")}))
    if not report["passed"]:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
