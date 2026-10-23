import struct
from pathlib import Path
from capstone import Cs, CS_ARCH_MIPS, CS_MODE_MIPS32, CS_MODE_LITTLE_ENDIAN
from disasm_aya_eboot import BASE

blob=Path(r'C:\Users\25105\Documents\寄生前夜第四日\work\psp_parse\raw\ULJM05798_module_08804000.bin').read_bytes(); md=Cs(CS_ARCH_MIPS,CS_MODE_MIPS32|CS_MODE_LITTLE_ENDIAN)
target=0x08BFFEB0; calls=[]
for off in range(0,len(blob)-4,4):
 w=struct.unpack_from('<I',blob,off)[0]
 if w>>26 != 3: continue
 pc=BASE+off; dest=((w&0x03ffffff)<<2)|((pc+4)&0xf0000000)
 if dest==target:calls.append(pc)
for pc in calls:
 off=pc-BASE-16; ins=list(md.disasm(blob[off:off+32],BASE+off));
 print('\nCALL',hex(pc));
 for x in ins: print(f'{x.address:08x}: {x.mnemonic:<8} {x.op_str}')
