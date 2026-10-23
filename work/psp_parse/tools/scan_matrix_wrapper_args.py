"""Inventory the call sites that feed z_un_08bfff98 (matrix upload wrapper)."""
from __future__ import annotations

import argparse
import struct
from pathlib import Path

from capstone import Cs, CS_ARCH_MIPS, CS_MODE_LITTLE_ENDIAN, CS_MODE_MIPS32

BASE = 0x08804000


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("module", type=Path)
    ap.add_argument("out", type=Path)
    ap.add_argument("--target", type=lambda value: int(value, 0), default=0x08BFFF98)
    args = ap.parse_args()
    blob = args.module.read_bytes()
    md = Cs(CS_ARCH_MIPS, CS_MODE_MIPS32 | CS_MODE_LITTLE_ENDIAN)
    rows = []
    for off in range(0, len(blob) - 4, 4):
        word = struct.unpack_from("<I", blob, off)[0]
        if word >> 26 != 3:
            continue
        pc = BASE + off
        dest = ((word & 0x03FFFFFF) << 2) | ((pc + 4) & 0xF0000000)
        if dest != args.target:
            continue
        start = max(0, off - 24)
        ins = list(md.disasm(blob[start:off + 8], BASE + start))
        def last_setup(reg: str):
            for x in reversed(ins[:-1]):
                if reg in x.op_str and x.mnemonic in {"ori", "addiu", "lui", "move", "addu", "lw", "lbu", "lb", "sll", "srl", "and", "or", "xor", "andi"}:
                    return {"address": hex(x.address), "mnemonic": x.mnemonic, "op_str": x.op_str}
            return None
        rows.append({
            "callsite": hex(pc),
            "a0_setup": last_setup("$a0"),
            "a1_setup": last_setup("$a1"),
            "a2_setup": last_setup("$a2"),
            "a3_setup": last_setup("$a3"),
            "instructions": [{"address": hex(x.address), "mnemonic": x.mnemonic, "op_str": x.op_str} for x in ins],
        })
    args.out.write_text(__import__("json").dumps({"schema": "aya-matrix-call-sites/v1", "target": hex(args.target), "count": len(rows), "call_sites": rows}, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"call_sites={len(rows)} -> {args.out}")


if __name__ == "__main__":
    main()
