"""Bounded offline final-state -> queue -> renderer analysis; never opens PPSSPP.

This is a static reachability report, not a claim that the retained live state
actually executed any downstream callback. Unknown semantic names stay null.
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
MODULE_SHA = "b5fc590366fc610f2cdd60104a4a28851bacd402c4600a4c296776e1dea0869f"
SECTION_SHA = "97443c71b1c1d644f323c6ff611afb740329cfe11a47a711f39dc59de06ec802"
RESOURCE_SHA = "04afeecb38df20d41a7c24da1686e31cf70a8e631aa51e48321c776ab21d89b6"
# Deliberately enumerated call-chain functions; no module-wide +0x60 scan.
FUNCTIONS = [
    0x08B69DBC, 0x08B69994, 0x08B68924, 0x08B68E6C, 0x08B6902C,
    0x08B68840, 0x08B689B8, 0x08B68F14, 0x08B92E14, 0x08B92FCC,
    0x08B65CB0, 0x08BBDCE8, 0x08BBDA68, 0x08BBDB20, 0x08BBD7F0,
    0x08BBD828, 0x08BBD864, 0x08B69540, 0x08B692F4, 0x08B69B58,
    0x08B9809C, 0x08B9A514, 0x08B66BB4, 0x08BBB8D4, 0x08BFFF6C,
    0x08C01088, 0x08B62674, 0x08B6270C, 0x08B5DD50, 0x08B5DDB0,
    0x08B5CB90, 0x08B5D258, 0x08B60374, 0x08B6050C, 0x08B5E7D0,
    0x08B5ECAC, 0x08B5E368, 0x08BBA1FC, 0x08BFFF98,
]
ANCHORS = {
    0x08B69EF8: 0x0E2D8D3B,  # jal update P matrix
    0x08B6A9E0: 0x0E2DA665,  # jal 69994, branch selected by R+6==0
    0x08B699F4: 0xAE30008C,  # context current P
    0x08B68FE8: 0x0100F809,  # post callback jalr t0
    0x08B935E8: 0x0E2EF73A,  # type14 -> enqueue
    0x08BBDE70: 0xAD2B0010,  # E+10=P
    0x08BBDE74: 0xAD2A0014,  # E+14=node
    0x08B694F4: 0x0140F809,  # render callback jalr t2
    0x08B69D64: 0x0140F809,
    0x08B66BD8: 0x8CCB008C,  # P=context+8c
    0x08B66BE0: 0x256B0060,  # P+60
    0x08BBB918: 0x34040001,  # matrix upload kind1=GE VIEW, not WORLD
    0x08C01270: 0x3C083C00,  # GE VIEW cursor
    0x08BFFFC0: 0x3C030400,  # GE PRIM command prefix
    0x08C0004C: 0xAC860000,
}


def sha(b):
    return hashlib.sha256(b).hexdigest()


def bounded(b, offset, size):
    if offset < 0 or size < 0 or offset + size > len(b):
        raise ValueError(f"out of original-byte bounds: {offset:x}+{size:x}")
    return b[offset:offset + size]


def u16(b, o):
    return struct.unpack("<H", bounded(b, o, 2))[0]


def u32(b, o):
    return struct.unpack("<I", bounded(b, o, 4))[0]


def analyze(module, section, symbols, capture, save):
    if sha(module) != MODULE_SHA:
        raise ValueError("selected module identity mismatch")
    if sha(section) != SECTION_SHA:
        raise ValueError("selected original FEP identity mismatch")
    for a, expected in ANCHORS.items():
        if u32(module, a - BASE) != expected:
            raise ValueError(f"opcode anchor mismatch {a:08x}")
    decoder = Cs(CS_ARCH_MIPS, CS_MODE_MIPS32 | CS_MODE_LITTLE_ENDIAN)
    funcs = []
    for a in FUNCTIONS:
        matches = [q for q in symbols if q[0] == a]
        if len(matches) != 1:
            raise ValueError(f"missing unique map function boundary {a:08x}")
        _, size, name = matches[0]
        if not 0 < size <= 0x1000 or size % 4:
            raise ValueError("unexpected function boundary")
        raw = bounded(module, a - BASE, size)
        instructions = []
        lines = []
        for o in range(0, size, 4):
            word = raw[o:o + 4]
            decoded = list(decoder.disasm(word, a + o))
            mnemonic = decoded[0].mnemonic if decoded else None
            opstr = decoded[0].op_str if decoded else None
            instructions.append({"address": a + o, "word": u32(word, 0),
                                 "mnemonic": mnemonic, "op_str": opstr})
            lines.append(f"{a+o:08x} {u32(word,0):08x} {mnemonic or 'UNDECODED'} {opstr or ''}")
        funcs.append({"address": a, "size": size, "map_name": name,
                      "raw": save(f"function_{a:08x}.bin", raw),
                      "disassembly": save(f"function_{a:08x}.txt", ("\n".join(lines)+"\n").encode()),
                      "instructions": instructions})

    def registry(typ):
        slot = 0x08C3A820 + typ * 4
        obj = u32(module, slot - BASE)
        vt = u32(module, obj - BASE)
        methods = []
        for offset in (0x18, 0x20, 0x38, 0x40):
            raw = bounded(module, vt + offset - BASE, 8)
            adjust, target = struct.unpack("<hxxI", raw)
            methods.append({"vtable_offset": offset, "this_adjust": adjust,
                            "target": target, "descriptor_hex": raw.hex()})
        return {"type": typ, "slot": slot, "object": obj, "vtable": vt,
                "draw_pass_filter_byte": module[0x08C3ACC0 + typ - BASE],
                "methods": methods, "semanticName": None}

    # Already verified table1[4] chain, extended only one concrete nested list.
    table1 = u32(section, 0x2C)
    record = u32(section, table1 + 4 * 4)
    if record != 0xFB4:
        raise ValueError("selected table1 index identity changed")
    count = u16(section, record + 0x12)
    ptrlist = u32(section, record + 0x20)
    if count != 4:
        raise ValueError("selected nested-descriptor count mismatch")
    descs = []
    observed_types = {14}
    for i in range(count):
        d = u32(section, ptrlist + i * 4)
        defs = u32(section, d + 0x1C)
        lists = []
        # Counts/pointers here come from the actual dispatcher instructions.
        for role, countoff, listoff, method in [
            ("pre", 0x19, 0x3C, 0x38),
            ("post", 0x14, 0x28, 0x18),
            ("render", 0x15, 0x2C, 0x20),
        ]:
            n = bounded(section, d + countoff, 1)[0]
            start = u32(section, d + listoff)
            items = []
            for j in range(n):
                index = u16(section, start + 2 * j)
                b = u32(section, defs + 4 * index)
                typ = u16(section, b)
                observed_types.add(typ)
                items.append({"index": index, "definition_offset": b,
                              "type": typ, "mutable_data_offset": u16(section, b + 2),
                              "definition_prefix_hex": bounded(section, b, 12).hex()})
            lists.append({"role": role, "count": n, "list_offset": start,
                          "vtable_method_offset": method, "items": items})
        descs.append({"ordinal": i, "offset": d,
                      "raw": save(f"fep_descriptor_{d:05x}.bin", bounded(section, d, 0x48)),
                      "lists": lists, "runtime_node_match_observed": False})

    if capture.get("failure") is not None:
        raise ValueError("retained capture failed")

    def sidecar(meta):
        raw = Path(meta["file"]).read_bytes()
        if sha(raw) != meta["sha256"] or len(raw) != meta["bytes"]:
            raise ValueError("retained raw-sidecar identity mismatch")
        return raw

    live = []
    for row in capture["rows"]:
        full = sidecar(row["stateAfterReturn"])
        final = sidecar(row["stateFinal"])
        helper = sidecar(row["actualOutput"])
        generic = sidecar(row["genericOutput"])
        resource = sidecar(row["resourceIdentity"]["stateReturn"]["bytes"])
        if full[0x60:0xA0] != final or not final == helper == generic:
            raise ValueError("retained final-state/helper bytes differ")
        if sha(resource) != RESOURCE_SHA or resource != section[0x48F0:0x4930]:
            raise ValueError("retained resource first64 identity mismatch")
        if row["outerRA"] != 0x08B69F00:
            raise ValueError("different observed updater outer RA")
        live.append({"sample": row["sample"], "P": row["P"],
                     "outerRA": row["outerRA"], "final_matrix_sha256": sha(final),
                     "record_byte6": resource[6],
                     "state_word0": u32(full, 0), "state_u16_a": u16(full, 0xA),
                     "state_u16_e": u16(full, 0xE),
                     "node_bank0": u32(full, 0x180), "node_bank1": u32(full, 0x184),
                     "source190": u32(full, 0x190), "source194": u32(full, 0x194),
                     "source198": u32(full, 0x198),
                     "downstream_observed": False, "semanticName": None})
    return {
        "schema": "t3b.weapon-marker-state-consumer.static.v1",
        "semanticName": None,
        "scope": "39 enumerated functions, one selected FEP nested descriptor list, saved state rows only",
        "module_sha256": sha(module), "section_sha256": sha(section),
        "functions": funcs, "opcode_anchors": [{"address": a, "word": w} for a,w in ANCHORS.items()],
        "registries": [registry(t) for t in sorted(observed_types)],
        "selected_fep_table1_index": 4, "nested_pointer_list": ptrlist,
        "nested_descriptors": descs, "retained_live_state_rows": live,
        "claims": [
            {"claim": "helper/generic/final P+60 equality and updater outer RA", "status": "observed_saved_runtime"},
            {"claim": "record+6 zero selects 69994 in updater if earlier gates pass", "status": "static_conditional"},
            {"claim": "type14 post callback enqueues entry containing P and node", "status": "static_conditional"},
            {"claim": "bucket processing dispatches render method+20", "status": "static_conditional"},
            {"claim": "selected nested definitions include render types152/155", "status": "original_resource_bytes"},
            {"claim": "66bb4 selects P+60 when node+1c is zero", "status": "static_conditional"},
            {"claim": "bbb8d4 composition is uploaded as GE VIEW 3c/3d", "status": "static_instructions"},
            {"claim": "fff98 writes VTYPE12, optional IADDR02/VADDR01 and PRIM04", "status": "static_instructions"},
            {"claim": "this exact gun-associated P executed those render callbacks", "status": "unobserved"},
            {"claim": "muzzle/particle/other visual semantic name", "status": "unknown"},
        ],
        "limits": [
            "No runtime node+40/registry callback/queue entry/GE packet has been captured here.",
            "Generic Capstone rendering of Allegrex VFPU words is not an exact VFPU mnemonic decoder; raw words are authoritative.",
            "No claim of exhaustive state+60 readers, all resource types, all render modes, or actual target execution.",
        ],
    }


def main():
    root = Path(__file__).resolve().parents[1]
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--module", type=Path, default=root / "raw/ULJM05798_module_08804000.bin")
    ap.add_argument("--map", type=Path, default=root / "map.ppmap.txt")
    ap.add_argument("--section", type=Path, default=root / "out/WEAPON_MARKER_STATE_20261020/original_source_match_section.bin")
    ap.add_argument("--capture", type=Path, default=root / "out/AYA_BONE_GE_ACTIONS/slot0_weapon_marker_state_fep6_v2/marker_state_output.json")
    ap.add_argument("--out", type=Path, default=root / "out/WEAPON_MARKER_STATE_CONSUMER_20261020")
    args = ap.parse_args()
    module, section, capraw = args.module.read_bytes(), args.section.read_bytes(), args.capture.read_bytes()
    capture = json.loads(capraw)
    args.out.mkdir(parents=True, exist_ok=True)

    def save(name, raw):
        p = (args.out / name).resolve()
        p.write_bytes(raw)
        if p.read_bytes() != raw:
            raise ValueError("output read-back mismatch")
        return {"file": str(p), "bytes": len(raw), "sha256": sha(raw)}

    result = analyze(module, section, load_symbols(args.map), capture, save)
    result["capture"] = {"file": str(args.capture.resolve()), "bytes": len(capraw), "sha256": sha(capraw)}
    out = args.out / "state_consumer.json"
    out.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    if json.loads(out.read_text(encoding="utf-8")) != result:
        raise ValueError("report read-back mismatch")
    print(json.dumps({"report": str(out.resolve()), "sha256": sha(out.read_bytes()),
                      "functions": len(result["functions"]), "retained_rows": len(result["retained_live_state_rows"]),
                      "runtime_downstream_observed": False}))


if __name__ == "__main__":
    main()
