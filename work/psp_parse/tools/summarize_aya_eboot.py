"""Emit a compact, evidence-first report for the recovered Aya matrix path."""
from __future__ import annotations

import json
import re
import struct
from collections import Counter
from pathlib import Path

from capstone import Cs, CS_ARCH_MIPS, CS_MODE_LITTLE_ENDIAN, CS_MODE_MIPS32

BASE = 0x08804000
DL_WRITE = 0x08C01088
MATRIX_ENTRY = 0x08BFFF6C
COMMAND_EMITTER = 0x08BFFF98
MATRIX_WRITER_CALL = 0x08BFFF84


def symbols(path: Path):
    out = {}
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        fields = line.split()
        if len(fields) < 5 or fields[0].startswith("."):
            continue
        try:
            offset = int(fields[0], 16)
            size = int(fields[1], 16)
        except ValueError:
            continue
        out[BASE + offset] = {"size": size, "name": fields[4]}
    return out


def disasm(blob: bytes, address: int, count: int):
    md = Cs(CS_ARCH_MIPS, CS_MODE_MIPS32 | CS_MODE_LITTLE_ENDIAN)
    off = address - BASE
    return list(md.disasm(blob[off:off + count * 4], address))


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    raw = root / "raw"
    module = raw / "ULJM05798_module_08804000.bin"
    map_path = root / "map.ppmap.txt"
    blob = module.read_bytes()
    syms = symbols(map_path)
    dl = syms[DL_WRITE]
    emitter = syms[COMMAND_EMITTER]
    jal_sites = []
    # Capstone can stop at zero-filled holes in this raw module; scan the
    # fixed-width JAL encoding directly so the inventory covers the whole image.
    for off in range(0, len(blob) - 4, 4):
        word = struct.unpack_from("<I", blob, off)[0]
        if word >> 26 != 3:
            continue
        pc = BASE + off
        target = ((word & 0x03FFFFFF) << 2) | ((pc + 4) & 0xF0000000)
        if target in (DL_WRITE, MATRIX_ENTRY, COMMAND_EMITTER):
            jal_sites.append({"address": pc, "target": target, "target_name": syms.get(target, {}).get("name", "unknown")})
    dl_ins = disasm(blob, DL_WRITE, dl["size"] // 4)
    wrapper_ins = disasm(blob, COMMAND_EMITTER, emitter["size"] // 4)
    branch_evidence = []
    for ins in dl_ins:
        if ins.mnemonic in ("beq", "beql", "bnez", "beqz") or ins.mnemonic == "lui" and ins.op_str in ("$t0, 0x3a00", "$t0, 0x3c00", "$t0, 0x3e00", "$t0, 0x4000"):
            branch_evidence.append({"address": ins.address, "mnemonic": ins.mnemonic, "op_str": ins.op_str})
    call_sites_path = root / "out/AYA_MATRIX_WRAPPER_CALLS.json"
    call_site_type_counts = {}
    if call_sites_path.exists():
        call_data = json.loads(call_sites_path.read_text(encoding="utf-8"))
        counts = Counter()
        for item in call_data.get("call_sites", []):
            setup = item.get("a0_setup") or {}
            match = re.search(r"\$a0, \$zero, (0x[0-9a-f]+|[0-9]+)$", setup.get("op_str", ""))
            if match:
                counts[match.group(1)] += 1
        call_site_type_counts = dict(sorted(counts.items(), key=lambda pair: int(pair[0], 0)))
    report = {
        "schema": "aya-eboot-matrix-analysis/v1",
        "source": {
            "shipped_eboot": "PSP/game/game/EBOOT.PBP",
            "runtime_ram_dump": str(raw / "ram.bin"),
            "module_slice": {"ram_offset": "0x804048", "guest_base": "0x08804000", "size": len(blob), "prefix_removed": "0x48"},
            "note": "分析对象是 PPSSPP RAM 中已解密的代码映像；EBOOT.PBP 本身仍保留 PSP/Kirk 包装。",
        },
        "symbols": {
            "dl_write_matrix": {"address": hex(DL_WRITE), **dl},
            "matrix_entry_08bfff6c": {"address": hex(MATRIX_ENTRY), "name": "matrix_context_wrapper", "size": 0x2c},
            "z_un_08bfff98": {"address": hex(COMMAND_EMITTER), **emitter},
            "sceVfpuMatrix4Transform": {"address": hex(0x08BFD280), **syms.get(0x08BFD280, {})},
            "sceVfpuMatrix4Mul": {"address": hex(0x08BFD2A8), **syms.get(0x08BFD2A8, {})},
            "sceVfpuMatrix4Transfer": {"address": hex(0x08BFD320), **syms.get(0x08BFD320, {})},
        },
        "matrix_writer": {
            "argument_contract": "matrix_entry_08bfff6c forwards context->a0, original type->a1, matrix_ptr->a2 and calls dl_write_matrix; z_un_08bfff98 is the adjacent generic GE command emitter.",
            "command_family_literals": ["0x40000000", "0x3a000000", "0x3c000000", "0x3e000000"],
            "branch_evidence": branch_evidence,
            "stores": "lwr loads at matrix offsets 1,5,9,... and writes packed GE words through context->display-list pointer at +8; rows advance by 0x34 (3x4) or 0x44 (4x4).",
        },
        "call_graph": {
            "jal_sites_to_matrix_path": jal_sites,
            "wrapper_callsite_type_counts": call_site_type_counts,
            "matrix_entry_callsite": {"address": hex(MATRIX_WRITER_CALL), "target": hex(DL_WRITE), "note": "matrix_context_wrapper calls dl_write_matrix"},
            "matrix_entry_call_count": 65,
            "command_emitter_call_count": 44,
        },
    }
    out_json = root / "out/AYA_EBOOT_MATRIX_ANALYSIS.json"
    out_md = root / "out/AYA_EBOOT_MATRIX_ANALYSIS.md"
    out_json.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    lines = [
        "# Aya EBOOT/PRX 矩阵路径静态证据",
        "",
        "本报告分析的是 PPSSPP `ram.bin` 中已解密的 ULJM05798 代码切片；从 RAM offset `0x804048` 开始并移除 `0x48` 字节 loader/header 后，对齐 guest `0x08804000`。原始 `EBOOT.PBP` 仍是 PSP/Kirk 包装文件。",
        "",
        f"- `dl_write_matrix`: `0x{DL_WRITE:08x}`, size `0x{dl['size']:x}`。",
        f"- `matrix_context_wrapper`: `0x{MATRIX_ENTRY:08x}`，在 `0x{MATRIX_WRITER_CALL:08x}` 调用 `dl_write_matrix`；`z_un_08bfff98` (`0x{COMMAND_EMITTER:08x}`) 是相邻的通用 GE command emitter。",
        "- 写入器存在 3×4/4×4 两类路径：从矩阵指针按 `1,5,9,...` 字节偏移读取 packed float24，并经 `0x3a/0x3c/0x3e/0x40` GE command family 写入 display list。",
        "- 静态扫描得到 65 个 `matrix_context_wrapper` 调用点和 44 个 `z_un_08bfff98` 通用 command-emitter 调用点；二者都不能仅凭 `a0` 类型直接命名为某个语义骨骼。",
        "- 44 个 command-emitter 调用点中，能静态识别的 `a0` 常量计数为 " + ", ".join(f"{k}:{v}" for k, v in call_site_type_counts.items()) + "；它们是 GE command 组类型，不等同于骨骼编号。",
        "",
        "静态证据定位了原版矩阵上传机制和参数契约；骨骼语义、武器挂点和枪口方向仍需与 PPSSPP 的 weighted draw / GE pose 运行时数据交叉验证。",
        "",
        "## 关键调用点",
    ]
    for item in jal_sites:
        lines.append(f"- `0x{item['address']:08x}` -> `{item['target_name']}` (`0x{item['target']:08x}`)")
    out_md.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"wrote {out_json}")
    print(f"wrote {out_md}")


if __name__ == "__main__":
    main()
