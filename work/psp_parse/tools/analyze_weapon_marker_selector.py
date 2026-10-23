"""Offline, bounded selector/primary writer analysis of the selected MIPS module.

No process, debugger, UI or ISO access. Raw immediate-store candidates are not
treated as a complete alias/write inventory. All semantic names remain null.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import struct
from pathlib import Path
from capstone import Cs, CS_ARCH_MIPS, CS_MODE_MIPS32, CS_MODE_LITTLE_ENDIAN
from disasm_aya_eboot import load_symbols

BASE = 0x08804000
EXPECTED = "b5fc590366fc610f2cdd60104a4a28851bacd402c4600a4c296776e1dea0869f"
TARGETS = [0x08B6513C, 0x08B646B4, 0x08B5B990, 0x08B59A98,
           0x08B26C6C, 0x08bbbfac, 0x08B3F140, 0x08B447CC, 0x08B65338,
           0x08B5A50C, 0x08B59AF4, 0x08B5BA3C]


def digest(data):
    return hashlib.sha256(data).hexdigest()


def main():
    root = Path(__file__).resolve().parents[1]
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--module", type=Path, default=root / "raw/ULJM05798_module_08804000.bin")
    ap.add_argument("--map", type=Path, default=root / "map.ppmap.txt")
    ap.add_argument("--out", type=Path, default=root / "out/WEAPON_MARKER_SELECTOR_20261020")
    args = ap.parse_args()
    blob = args.module.read_bytes()
    if digest(blob) != EXPECTED:
        raise ValueError("selected module SHA256 mismatch")
    args.out.mkdir(parents=True, exist_ok=True)
    symbols = load_symbols(args.map)
    decoder = Cs(CS_ARCH_MIPS, CS_MODE_MIPS32 | CS_MODE_LITTLE_ENDIAN)

    def symbol(address):
        hits = [(a, n, name) for a, n, name in symbols if a <= address < a+n]
        if len(hits) != 1:
            raise ValueError(f"ambiguous/missing function boundary at {address:x}")
        a, n, name = hits[0]
        return {"address": a, "bytes": n, "map_name": name, "semanticName": None}

    def word(address):
        return struct.unpack_from("<I", blob, address-BASE)[0]

    def instruction(address):
        raw = blob[address-BASE:address-BASE+4]
        decoded = list(decoder.disasm(raw, address))
        return {"address": address, "word": word(address), "hex_le": raw.hex(),
                "mnemonic": decoded[0].mnemonic if decoded else None,
                "op_str": decoded[0].op_str if decoded else None,
                "note": None if decoded else "Retained original word; generic Capstone does not decode this Allegrex/VFPU opcode."}

    def sidecar(name, data):
        path = (args.out / name).resolve()
        path.write_bytes(data)
        return {"file": str(path), "bytes": len(data), "sha256": digest(data)}

    # Direct J/JAL scan only; JALR and synthesized function pointers are not covered.
    calls = {target: [] for target in TARGETS}
    for off in range(0, len(blob)-3, 4):
        value = struct.unpack_from("<I", blob, off)[0]
        if value >> 26 not in (2, 3):
            continue
        target = ((BASE+off+4) & 0xf0000000) | ((value & 0x03ffffff) << 2)
        if target in calls:
            calls[target].append(BASE+off)

    functions = []
    for target in TARGETS:
        fn = symbol(target)
        start, size = fn["address"], fn["bytes"]
        fn["raw"] = sidecar(f"function_{start:08x}.bin", blob[start-BASE:start-BASE+size])
        fn["instructions"] = [instruction(a) for a in range(start, start+size, 4)]
        fn["direct_callers"] = [{"callsite": c, "returnPC": c+8,
            "function": symbol(c), "context": [instruction(a) for a in range(c-0x34, c+8, 4)]} for c in calls[target]]
        functions.append(fn)

    candidates = []
    # A direct immediate displacement can alias 14c/14d only if the base really
    # is P. This inventory does not establish that base or follow data flow.
    widths = {0x28: ("SB", 1), 0x29: ("SH", 2), 0x2b: ("SW", 4), 0x39: ("SWC1", 4)}
    for off in range(0, len(blob)-3, 4):
        value = struct.unpack_from("<I", blob, off)[0]
        op, rs = value >> 26, (value >> 21) & 31
        if op not in widths or rs == 29:
            continue
        name, width = widths[op]
        displacement = (value & 0xffff) - (0x10000 if value & 0x8000 else 0)
        if displacement <= 0x14d and displacement+width > 0x14c:
            candidates.append({**instruction(BASE+off), "store_form": name, "base_register": rs,
                               "displacement": displacement, "width": width,
                               "base_is_state_proven": False})

    literal_address = 0x08C2D5C0
    literal_off = literal_address-BASE
    terminator = blob.index(b"\0", literal_off, literal_off+64)
    literal = blob[literal_off:terminator].decode("ascii")
    assert literal == "SetBindObjectPlus"
    assert calls[0x08B6513C] == [0x08B5B9EC, 0x08B651A4]
    assert calls[0x08B5B990] == [0x08B59AD0]
    assert calls[0x08B59A98] == [0x08B26CFC]
    assert word(0x08B651FC) == 0xA650014C and word(0x08B65210) == 0xA650014C
    assert word(0x08B6478C) == 0xAE500144
    assert word(0x08B65338) == 0x03E00008 and word(0x08B6533C) == 0
    report = {"schema": "weapon-marker-selector-static/v1", "semanticName": None,
        "module": {"file": str(args.module.resolve()), "base": BASE, "bytes": len(blob), "sha256": digest(blob)},
        "map": {"file": str(args.map.resolve()), "sha256": digest(args.map.read_bytes())},
        "producer": {"file": str(Path(__file__).resolve()), "sha256": digest(Path(__file__).read_bytes())},
        "associated_literal": {"address": literal_address, "value": literal,
                               "raw": sidecar("SetBindObjectPlus_literal.bin", blob[literal_off:terminator+1])},
        "functions": functions, "immediate_alias_store_candidates": candidates,
        "sh_14c_non_sp_count": sum(x["store_form"] == "SH" and x["displacement"] == 0x14c for x in candidates),
        "actual_runtime_writer_observed": False,
        "limits": ["Map names z_un_* are boundary labels, not recovered semantic names.",
            "No live/debugger/UI/ISO access occurs in this script.",
            "Direct J/JAL scans do not cover JALR, tail dispatch through registers, synthesized pointers or dynamically generated code.",
            "Immediate-store candidates do not prove the base register is the target state.",
            "Five SH+14c sites do not imply all selector writers are covered; SB/SW aliases, offset base pointers, indexed/copy writes, SWL/SWR and VFPU stores remain separate questions.",
            "The emitted static chain can set selector1 if its dynamic argument is 1 and validation succeeds; no gameplay caller is attributed without runtime evidence."]}
    destination = args.out / "selector_analysis.json"
    destination.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"report": str(destination.resolve()), "functions": len(functions),
                      "game_callers": len(calls[0x08B26C6C]), "sh_14c_non_sp_count": report["sh_14c_non_sp_count"],
                      "alias_candidates": len(candidates)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
