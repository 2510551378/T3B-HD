import struct
from pathlib import Path

BASE = 0x08804000
blob = Path(r'C:\Users\25105\Documents\寄生前夜第四日\work\psp_parse\raw\ULJM05798_module_08804000.bin').read_bytes()
targets = {0x08C01088, 0x08BFD280, 0x08BFD2A8, 0x08BFD320, 0x08BFFEB0, 0x08BFFF00, 0x08C01E9C}
hits = {t: [] for t in targets}
for off in range(0, len(blob) - 4, 4):
    word = struct.unpack_from('<I', blob, off)[0]
    if word >> 26 != 3:
        continue
    pc = BASE + off
    dest = ((word & 0x03FFFFFF) << 2) | ((pc + 4) & 0xF0000000)
    if dest in hits:
        hits[dest].append(pc)
for target, pcs in hits.items():
    print(hex(target), len(pcs), [hex(x) for x in pcs[:50]])
