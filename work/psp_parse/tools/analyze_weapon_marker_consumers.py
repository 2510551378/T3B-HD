"""Bounded offline MIPS/recorded-RAM evidence for weapon marker consumers.

Never connects to an emulator. Unknown PSP VFPU instructions stay as raw words;
the report separates native dataflow from unobserved weapon/FX semantics.
"""
import argparse
import bisect
import hashlib
import json
import re
import struct
from pathlib import Path

from capstone import Cs, CS_ARCH_MIPS, CS_MODE_MIPS32, CS_MODE_LITTLE_ENDIAN
from disasm_aya_eboot import BASE, load_symbols


TARGETS = {
    0x08b3e73c: "raw local matrix pointer, handle/index -> source+0x40",
    0x08b44580: "WORLD matrix helper, out/actor/index",
    0x08b3e610: "WORLD matrix wrapper, out/handle/index",
    0x08b3e5b8: "WORLD point wrapper, out/handle/index",
    0x08b442bc: "WORLD point helper, actor/out/index, source+0x30",
    0x08bbc584: "generic attachment transform variant A",
    0x08bbc93c: "generic attachment transform variant B",
    0x08bbcd78: "generic attachment transform variant C",
    0x08b4492c: "numeric metadata tag/bone/offset lookup",
    0x08b62e98: "state-driven attachment transform caller",
    0x08b634ec: "parent state transform update, primary handle at +0x144",
}
FOCUS = [(0x08b3e610, 0x08b3e630), (0x08b3e73c, 0x08b3e764),
         (0x08b44580, 0x08b445f0), (0x08b44730, 0x08b44790),
         (0x08b442bc, 0x08b44348), (0x08b44348, 0x08b443d0),
         (0x08b4492c, 0x08b449b4), (0x08bbc93c, 0x08bbca40),
         (0x08bbccc4, 0x08bbccd4), (0x08b62e98, 0x08b62f20),
         (0x08b63070, 0x08b63160), (0x08b631c8, 0x08b63200),
         (0x08b634ec, 0x08b6355c), (0x08b63778, 0x08b637a8)]


def sha(data):
    return hashlib.sha256(data).hexdigest()


def run(args):
    blob = args.module.read_bytes()
    symbols = sorted(load_symbols(args.map))
    starts = [row[0] for row in symbols]
    md = Cs(CS_ARCH_MIPS, CS_MODE_MIPS32 | CS_MODE_LITTLE_ENDIAN)

    def owner(address):
        i = bisect.bisect_right(starts, address) - 1
        if i >= 0 and symbols[i][0] <= address < symbols[i][0] + symbols[i][1]:
            a, size, name = symbols[i]
            return {"address": a, "size": size, "map_name": name}
        return None

    def instruction(address):
        raw = blob[address - BASE:address - BASE + 4]
        if len(raw) != 4:
            raise ValueError("instruction outside selected module")
        decoded = next(md.disasm(raw, address), None)
        return {"address": address, "word_u32": struct.unpack("<I", raw)[0], "bytes_hex": raw.hex(),
                "mnemonic": decoded.mnemonic if decoded else ".word", "operands": decoded.op_str if decoded else raw.hex()}

    sites = []
    for offset in range(0, len(blob) - 3, 4):
        word = struct.unpack_from("<I", blob, offset)[0]
        if word >> 26 != 3:
            continue
        at = BASE + offset
        target = ((at + 4) & 0xf0000000) | ((word & 0x3ffffff) << 2)
        if target in TARGETS:
            sites.append({"callsite": at, "target": target, "target_description": TARGETS[target],
                          "owner": owner(at), "context": [instruction(p) for p in range(max(BASE, at - 24), at + 12, 4)]})
    focus = [{"start": lo, "end": hi, "instructions": [instruction(a) for a in range(lo, hi, 4)]} for lo, hi in FOCUS]
    snapshot = json.loads(args.snapshot.read_text(encoding="utf-8"))
    header = snapshot["header"]
    metadata = {"path": str(args.snapshot.resolve()), "sha256": sha(args.snapshot.read_bytes()),
                "object": snapshot["object"], "metadata": snapshot["metadata"], "bone_count": snapshot["boneCount"],
                "header_u32": header, "named_offset_table_count_s16_at_0x12": (header[4] >> 16) & 0xffff,
                "named_offset_table_pointer_at_0x28": header[10],
                "boundary": "The current original weapon header has zero records for helper 0x08b4492c; this does not name direct source indices."}
    strings = []
    for match in re.finditer(rb"[ -~]{5,200}", blob):
        text = match.group().decode("ascii")
        if re.search(r"\b(muzzle|weapon|socket|bullet|bone|shoot|shot|gun)\b", text, re.I):
            address = BASE + match.start()
            pointer_hits = [BASE + offset for offset in range(0, len(blob) - 3, 4)
                            if struct.unpack_from("<I", blob, offset)[0] == address]
            strings.append({"address": address, "text": text, "literal_pointer_locations": pointer_hits,
                            "link_to_weapon_source1_or_source2": "not established"})
    ram = None
    if args.ram is not None:
        raw = args.ram.read_bytes()
        cv = lambda guest: guest - 0x08000000 + 0x48

        def u32(guest):
            at = cv(guest)
            return struct.unpack_from("<I", raw, at)[0] if 0 <= at <= len(raw) - 4 else None

        def references(value):
            pattern, start, hits = struct.pack("<I", value), 0, []
            while True:
                at = raw.find(pattern, start)
                if at < 0:
                    return hits
                if at % 4 == 0:
                    hits.append(at - 0x48 + 0x08000000)
                start = at + 1

        expected_header = struct.pack("<16I", *header)
        at = cv(snapshot["metadata"])
        header_equal = raw[at:at + 64] == expected_header
        actors = []
        for reference in references(snapshot["metadata"]) if header_equal else []:
            actor = reference - 0x3e8
            source = u32(actor + 0x3c4)
            if source is None or not 0 <= cv(source) <= len(raw) - 3 * 0x130:
                continue
            parents = [u32(source + i * 0x130 + 0x124) for i in range(3)]
            if parents != [0, source, source]:
                continue
            source0 = raw[cv(source):cv(source) + 0x130]
            if source0[0xc0:0xf0] != struct.pack("<12I", *snapshot["records"][0]["words"][48:60]):
                continue
            handles = references(actor)
            actors.append({"object": actor, "source_base": source, "parent_pointer_values": parents,
                           "source0_skin_bytes_match": True, "object_pointer_reference_addresses": handles,
                           "references_to_possible_handles": [{"possible_handle": h, "references": references(h)} for h in handles]})
        ram = {"path": str(args.ram.resolve()), "sha256": sha(raw), "mapping": "file_offset=guest-0x08000000+0x48",
               "metadata_header_equal_to_selected_snapshot": header_equal, "validated_old_allocations": actors,
               "boundary": "These are passive pointer relationships in an older RAM image, not observed calls or proof of a marker/FX consumer."}
    report = {"schema": "weapon-marker-static-consumer-analysis/v1",
              "inputs": {"module": {"path": str(args.module.resolve()), "sha256": sha(blob), "base": BASE, "bytes": len(blob)},
                         "map": {"path": str(args.map.resolve()), "sha256": sha(args.map.read_bytes())}},
              "targets": [{"address": a, "description": name, "owner": owner(a),
                           "direct_jal_callsite_count": sum(row["target"] == a for row in sites)} for a, name in TARGETS.items()],
              "direct_jal_callsites": sites, "focused_disassembly": focus, "weapon_metadata": metadata,
              "bounded_keyword_strings": strings, "old_ram": ram,
              "abi": {"entry": 0x08b44580, "a0": "output 64-byte matrix address, unproduced at entry",
                      "a1": "drawable actor directly; do NOT dereference a1 again", "a2": "source index",
                      "source": "*(a1+0x3c4)+a2*0x130+0x40", "world": "a1+0x220",
                      "handle_wrapper": "0x08b3e610: lw a1,0(a1) at 0x08b3e61c before JAL 0x08b44580",
                      "timing_boundary": "entry precedes helper 0x08b460a0 lazy update; entry matrix snapshots are not return values"},
              "state_path": ["state+0x14c or state+0x14e (s16)", "0x08b62e98 calls 0x08bbc93c/0x08bbcd78/0x08bbc584",
                             "generic attachment selector with high mode bits and low 12-bit index/tag", "0x08b3e610 dereferences actor handle",
                             "0x08b44580 reads actual actor source[index]+0x40 and actor WORLD"],
              "conclusions": [{"claim": "A generic original consumer of source[index]+0x40 is identified", "status": "static code established"},
                              {"claim": "The selected weapon executes that consumer with source1 or source2", "status": "unresolved until runtime trace"},
                              {"claim": "Source1 is the game's muzzle socket", "status": "not established"},
                              {"claim": "Attachment state fields lead to the matrix consumer", "status": "static dataflow established; weapon/FX instance unobserved"}],
              "limits": ["Direct-JAL inventory is a bounded machine-word scan of this module; indirect calls/relocated external modules are not exhaustively resolved.",
                         "Capstone does not fully decode PSP VFPU. Raw bytes are retained; generic COP2 display mnemonics are not used as VFPU semantic proof.",
                         "Keyword labels such as close muzzle are not attributed to this weapon or source index without code/dataflow/runtime linkage.",
                         "No emulator connection, target execution, input injection or original asset modification occurs in this offline analysis."]}
    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "static_analysis.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    text = []
    for section in focus:
        text.append(f"[{section['start']:08x},{section['end']:08x})")
        text.extend(f"{r['address']:08x}: {r['word_u32']:08x}  {r['mnemonic']} {r['operands']}" for r in section["instructions"])
        text.append("")
    (args.out / "disassembly.txt").write_text("\n".join(text), encoding="utf-8")
    print(json.dumps({"out": str(args.out.resolve()), "direct_jal_callsites": len(sites), "keyword_strings": len(strings),
                      "named_offset_records": metadata["named_offset_table_count_s16_at_0x12"],
                      "weapon_source1_semantics": "unconfirmed"}))


def main():
    root = Path(__file__).resolve().parent.parent
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--module", type=Path, default=root / "raw/ULJM05798_module_08804000.bin")
    ap.add_argument("--map", type=Path, default=root / "map.ppmap.txt")
    ap.add_argument("--snapshot", type=Path, default=root / "out/AYA_BONE_GE_ACTIONS/slot0_fire_reverse120_world60/weapon_metadata_snapshot.json")
    ap.add_argument("--ram", type=Path)
    ap.add_argument("--out", type=Path, required=True)
    run(ap.parse_args())


if __name__ == "__main__":
    main()
