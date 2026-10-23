import argparse
from capstone import Cs, CS_ARCH_MIPS, CS_MODE_MIPS32, CS_MODE_LITTLE_ENDIAN
from disasm_aya_eboot import load_symbols, BASE
from pathlib import Path

ap=argparse.ArgumentParser(); ap.add_argument('module'); ap.add_argument('map'); ap.add_argument('address',type=lambda x:int(x,0)); ap.add_argument('--before',type=int,default=0x80); ap.add_argument('--after',type=int,default=0x100); a=ap.parse_args()
b=Path(a.module).read_bytes(); md=Cs(CS_ARCH_MIPS,CS_MODE_MIPS32|CS_MODE_LITTLE_ENDIAN)
off=a.address-BASE-a.before
print('target',hex(a.address),'file_offset',hex(off))
for x in md.disasm(b[off:off+a.before+a.after],BASE+off):
    mark=' >>>' if x.address==a.address else ''
    print(f'{x.address:08x}: {x.mnemonic:<8} {x.op_str}{mark}')
syms=load_symbols(a.map); prev=[s for s in syms if s[0]<=a.address]
print('nearest_symbol',prev[-1] if prev else None)
