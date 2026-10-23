"""Read-only static/data-flow analysis of the actually observed selector caller.

Consumes saved capture/code only. Does not connect to PPSSPP, access the ISO,
write guest memory, modify the producer or infer a muzzle/FX semantic name.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import struct
from pathlib import Path
from capstone import Cs, CS_ARCH_MIPS, CS_MODE_MIPS32, CS_MODE_LITTLE_ENDIAN
from disasm_aya_eboot import load_symbols

BASE=0x08804000
EXPECTED="b5fc590366fc610f2cdd60104a4a28851bacd402c4600a4c296776e1dea0869f"
TARGETS=[0x08971EDC,0x08976F1C,0x08B38DD0,0x0896CE9C,0x0896C5FC,0x08AC288C,0x08AC28CC,0x08B26C6C]


def sha(data): return hashlib.sha256(data).hexdigest()


def main():
    root=Path(__file__).resolve().parents[1]
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--capture",type=Path,default=root/"out/AYA_BONE_GE_ACTIONS/slot0_weapon_selector_fire_probe/marker_selector_writer.json")
    ap.add_argument("--module",type=Path,default=root/"raw/ULJM05798_module_08804000.bin")
    ap.add_argument("--map",type=Path,default=root/"map.ppmap.txt")
    ap.add_argument("--out",type=Path,default=root/"out/WEAPON_MARKER_SELECTOR_SOURCE_20261020")
    args=ap.parse_args()
    module=args.module.read_bytes()
    if sha(module)!=EXPECTED: raise ValueError("selected module SHA mismatch")
    capture_bytes=args.capture.read_bytes();capture=json.loads(capture_bytes)
    if capture["failure"] is not None: raise ValueError("capture failed")
    args.out.mkdir(parents=True,exist_ok=True)
    symbols=load_symbols(args.map)
    decoder=Cs(CS_ARCH_MIPS,CS_MODE_MIPS32|CS_MODE_LITTLE_ENDIAN)

    def save(name,data):
        p=(args.out/name).resolve();p.write_bytes(data)
        return {"file":str(p),"bytes":len(data),"sha256":sha(data)}

    def word(address): return struct.unpack_from("<I",module,address-BASE)[0]

    functions=[]
    for target in TARGETS:
        found=[(a,n,s) for a,n,s in symbols if a==target]
        if len(found)!=1: raise ValueError(f"function boundary missing {target:x}")
        address,size,name=found[0]
        if size>0x1000: raise ValueError("unexpectedly large function")
        instructions=[]
        for a in range(address,address+size,4):
            raw=module[a-BASE:a-BASE+4];decoded=list(decoder.disasm(raw,a))
            instructions.append({"address":a,"word":word(a),"mnemonic":decoded[0].mnemonic if decoded else None,
                "op_str":decoded[0].op_str if decoded else None})
        functions.append({"address":address,"bytes":size,"map_name":name,"semanticName":None,
            "raw":save(f"function_{address:08x}.bin",module[address-BASE:address-BASE+size]),"instructions":instructions})

    anchors={0x08971EE8:0x8C940000,0x08971F14:0x01009025,0x08971F18:0x8E060004,
        0x08971F24:0x00059880,0x08971F48:0x0260B025,0x08971FDC:0x02403825,0x08971FE0:0x0E2C9B1B,
        0x08976F24:0x0080A025,0x0897704C:0x8E670090,0x08977058:0xAFA70378,0x08977068:0x8E640094,
        0x08977078:0xAFA40374,0x08977CB4:0x8FA60374,0x08977CBC:0x8FA80378,0x08977CC0:0x0E25C7B7,
        0x08977CC4:0x02003825,0x08B38DD0:0x8C860084,0x08B38DE0:0x8C840080,0x08B38E0C:0x8CA50000}
    for a,w in anchors.items():
        if word(a)!=w: raise ValueError(f"opcode anchor mismatch {a:x}")

    observations=[]
    for row in capture["rows"]:
        stack_meta=row["entryStack"];stack=Path(stack_meta["file"]).read_bytes()
        if sha(stack)!=stack_meta["sha256"]: raise ValueError("raw stack SHA mismatch")
        S=row["entrySP"]
        def at_address(address):
            offset=address-S
            if offset<0 or offset+4>len(stack): raise ValueError("stack read outside original capture")
            return struct.unpack_from("<I",stack,offset)[0]
        # This report is explicitly for the actually observed single-recursion chain.
        if row["entryRA"]!=0x08B651AC or at_address(S+0x18)!=0x08B5B9F4:
            raise ValueError("not the observed one-level recursion ABI")
        R=S+0x20;G=R+0x30;Q=R+0x50;U=R+0x70
        if [at_address(R+o) for o in [0x10,0x20,0x48,0x6c]]!=[0x08B59AD8,0x08B26D04,0x08971FE8,0x08977CC8]:
            raise ValueError("actual caller saved RA chain differs")
        context=at_address(G);primary=at_address(G+4);selector=at_address(G+8);container=at_address(G+0x14)
        config=at_address(Q+0x0c);actor=at_address(Q+0x10);slot_byte=row["entryGPR"][22]
        if slot_byte%4 or selector!=row["newSelector"] or primary!=row["primary"]:
            raise ValueError("live saved-register parameter relation differs")
        if at_address(G+0x10)!=0xffffffff: raise ValueError("game function failure sentinel differs")
        upper_local_range={"address":U+0x370,"bytes":0x10,"original_stack_offset":U+0x370-S,
            "available_in_existing_capture":U+0x380-S<=len(stack)}
        fields={"game_context":context,"primary_handle":primary,"selector":selector,"slot_container":container,
            "slot_byte_offset":slot_byte,"slot_index":slot_byte//4,"config":config,"actor":actor,
            "binding_object_context":at_address(R-0x14),"binding_inner_context":row["context"],
            "root_group":at_address(R-0x18)}
        windows=[{"name":"upper_locals_370","address":U+0x370,"bytes":0x10},
            {"name":"config_8c","address":config+0x8c,"bytes":0x10},
            {"name":"actor_model_array_fields","address":actor+0x80,"bytes":8},
            {"name":"actor_slot_container_field","address":actor+0x148c,"bytes":4},
            {"name":"actor_mode_1538","address":actor+0x1538,"bytes":4},
            {"name":"actor_selector_bool_bytes","address":actor+0x161c,"bytes":4},
            {"name":"slot_container_header","address":container,"bytes":8},
            {"name":"binding_context_link","address":fields["binding_object_context"]+0x18,"bytes":4}]
        for w in windows:
            if w["address"]%4 or w["address"]<0x08000000 or w["address"]+w["bytes"]>0x0c000000:
                raise ValueError("planned fixed window outside RAM")
        observations.append({"sample":row["sample"],"state":row["state"],"entryTicks":row["entryTicks"],
            "frames":{"leafS":S,"rootS":R,"game_wrapper_G":G,"game_function_Q":Q,"upper_function_U":U},
            "game_callsite":0x08971FE0,"upper_callsite":0x08977CC0,
            "saved_register_fields":fields,"source_field_90_address":config+0x90,
            "source_field_90_value_supported_by_parameter_flow":selector,
            "source_field_90_raw_observed":False,"requested_resource_config94_raw_observed":False,
            "upper_local_range":upper_local_range,
            "game_wrapper_savedregs_raw":save(f"game_wrapper_savedregs_{row['sample']:04d}.bin",stack[G-S:G-S+0x20]),
            "game_function_savedregs_raw":save(f"game_function_savedregs_{row['sample']:04d}.bin",stack[Q-S:Q-S+0x20]),
            "proposed_fixed_windows":windows})
    report={"schema":"observed-weapon-selector-source-static/v1","semanticName":None,
        "module":{"file":str(args.module.resolve()),"sha256":sha(module)},
        "capture":{"file":str(args.capture.resolve()),"sha256":sha(capture_bytes),"producer":capture["producer"]},
        "producer":{"file":str(Path(__file__).resolve()),"sha256":sha(Path(__file__).read_bytes())},
        "observations":observations,"functions":functions,"anchors":[{"address":a,"word":w} for a,w in anchors.items()],
        "dynamic_windows_after_pointer_validation":[
            {"name":"slot_word","base":"u32(slotContainer+0)","offset":"saved leaf GPR22","bytes":4,
             "require":"byteOffset%4=0; byteOffset/4<u32(slotContainer+4); guest RAM bounds"},
            {"name":"selected_actor_model_entry","base":"u32(actor+0x80)","offset":"24*(u8(actor+0x161e)!=0)","bytes":24,
             "require":"normalized bool index<u32(actor+0x84); guest RAM bounds; first word matches primary handle"}],
        "optional_resource_manager_relation":{"manager":"u32(0x08c3bc0c)+0x340",
            "fields_window":{"offset":0x8be0,"bytes":12},"contiguous_record_stride":0xe4,
            "mode3":"pointer table at manager+0x8be4","other_mode":"contiguous base at manager+0x8be0",
            "count_field":0x8be8,"observed_manager_fields":False},
        "limits":["This analyzes the observed caller parameter path, not the root writer auditor's complete raw verification.",
            "Actual game s2=1 and its unchanged static propagation are observed; config+0x90 has not yet been directly read in this capture.",
            "Requested config+0x94 ID and the cached/returned stateKey are distinct values; neither is recovered from missing upper locals.",
            "Original 0x400 stack ends immediately before upper+0x370; source locals +374/+378/+37c are not present and cannot be retrospectively filled.",
            "No virtual function +0x48 target or FX/muzzle semantic is inferred from its offset."]}
    p=args.out/"selector_source.json";p.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps({"report":str(p.resolve()),"rows":len(observations),"functions":len(functions),
        "source90_addresses":[hex(x["source_field_90_address"]) for x in observations]},ensure_ascii=False))


if __name__=="__main__": main()
