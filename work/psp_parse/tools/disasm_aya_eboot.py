"""Focused MIPS static analysis for the recovered ULJM05798 module.

The code image is taken from PPSSPP guest RAM (the shipped EBOOT is PSP/Kirk
wrapped).  This keeps the original file intact while producing a reproducible
map-addressed disassembly and call-site inventory for matrix/display-list code.
"""
import argparse, json, re, struct
from pathlib import Path
from capstone import Cs, CS_ARCH_MIPS, CS_MODE_MIPS32, CS_MODE_LITTLE_ENDIAN

BASE = 0x08804000

def load_symbols(path):
    out=[]
    for line in Path(path).read_text(encoding='utf-8',errors='replace').splitlines():
        p=line.split()
        if len(p)<5 or p[0].startswith('.'): continue
        try: off=int(p[0],16); size=int(p[1],16)
        except ValueError: continue
        out.append((BASE+off,size,p[4]))
    return out

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('module'); ap.add_argument('map'); ap.add_argument('out'); a=ap.parse_args()
    blob=Path(a.module).read_bytes(); syms=load_symbols(a.map); names={addr:(size,name) for addr,size,name in syms}
    md=Cs(CS_ARCH_MIPS,CS_MODE_MIPS32|CS_MODE_LITTLE_ENDIAN); md.detail=True
    focus=[(addr,size,name) for addr,size,name in syms if any(k in name.lower() for k in ('matrix','ge','draw','prim','vfpu','mesh','anim','bone','model')) and not name.startswith('z_un_')]
    text=[]
    for addr,size,name in focus:
        off=addr-BASE
        if off<0 or off>=len(blob): continue
        ins=[]
        for x in md.disasm(blob[off:off+min(size,0x600)],addr):
            ins.append({'address':x.address,'mnemonic':x.mnemonic,'op_str':x.op_str,'bytes':x.bytes.hex()})
        text.append({'address':addr,'offset':off,'size':size,'name':name,'instructions':ins})
    targets={x[0] for x in focus}
    callers=[]
    for x in md.disasm(blob,BASE):
        if x.mnemonic in ('jal','jalx'):
            try: target=int(x.op_str,0)
            except ValueError: continue
            if target in targets:
                callers.append({'callsite':x.address,'target':target,'target_name':names.get(target,(0,'?'))[1]})
    result={'module':str(a.module),'base':hex(BASE),'focus_count':len(text),'focus':text,'matrix_callers':callers}
    Path(a.out).write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(f'focus={len(text)} callers={len(callers)} -> {a.out}')
    for row in text:
        if row['name'] in ('dl_write_matrix','sceVfpuMatrix4Transform','sceVfpuMatrix4Mul','sceVfpuMatrix4Transfer'):
            print(f"\n== {row['name']} {row['address']:#x} size={row['size']:#x} ==")
            for i in row['instructions'][:80]: print(f"{i['address']:08x}: {i['mnemonic']:<8} {i['op_str']}")
    print('\n== matrix callsites ==')
    for c in callers[:80]: print(f"{c['callsite']:08x} -> {c['target_name']} ({c['target']:08x})")

if __name__=='__main__': main()
