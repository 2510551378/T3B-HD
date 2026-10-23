"""Audit original type16 RGBA/type7 percent-scale callbacks and nested color evaluation."""
import argparse
import json
import struct
from pathlib import Path

from analyze_fx_node_time import check,identity,read,registers,sidecar
from analyze_fx_property_callbacks import audit
from replay_fx_color_scale import Machine
from verify_weapon_ge_matrix_math import REFERENCE_SHA


def replay(module,row,entry,before,expected):
    g,f=registers(entry['allRegisters']);pw=before['parameterWindow']
    vm=Machine(module,g,f,pw['address'],sidecar(pw['raw']))
    for key in ('record','oldRecord','typeObject','vtable'):
        item=row[key]
        if item is not None:vm.retain(item['address'],sidecar(item['raw']))
    predicted=vm.run(entry['stop']['pc'],g[31])
    if expected is not None:check(predicted==expected,'Original color/scale opcode replay differs from actual return memory')
    return vm,predicted


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--capture',type=Path,action='append',required=True);p.add_argument('--out',type=Path,required=True)
    args=p.parse_args();check(not args.out.exists(),'Never replace color/scale proof');args.out.mkdir(parents=True)
    primary=Path(__file__).resolve().parents[1]/'raw/ppsspp_v1.20.4_vfpu_reference';references=[]
    for name,digest in REFERENCE_SHA.items():
        item=identity(primary/name);check(item['sha256']==digest,'Pinned VFPU reference changed');references.append(item)
    captures=[];operations=[]
    for path in args.capture:
        base=audit(path);r=read(path);module=Path(r['module']['file']).read_bytes();mode=r['mode'];captures.append(base)
        for row in r['rows']:
            if row['type']not in (7,16):continue
            entry,before=row['entry'],row['entry']['before'];after=row['return']['after'];expected=sidecar(after['parameterWindow']['raw'])
            vm,predicted=replay(module,row,entry,before,expected)
            g,f=registers(entry['allRegisters']);offset=row['parameterAddress']-before['parameterWindow']['address'];size=0x30 if row['type']==16 else 0x20
            previous=r['rows'][row['index']-1]if row['index']else None
            established=row['type']==16 and mode=='reset'and previous is not None and previous['type']==7 and previous['target']==0x08b949d0
            if established:
                for a,z in ((0x08b949d0,0x08b949fc),(0x08b68b8c,0x08b68d78),(0x08b6ac94,0x08b6add8)):
                    check(any(c['address']<=a and c['address']+c['size']>=z for c in r['code']),'Prefix predecessor/dispatcher code not retained')
                for a,z in ((0x08b68b8c,0x08b68d78),(0x08b6ac94,0x08b6add8)):
                    for at in range(a,z,4):
                        word=int.from_bytes(module[at-0x08804000:at-0x08804000+4],'little')
                        check(word>>26 not in (18,50,54,58,62)and word>>24 not in (0x60,0x64,0x65,0x6d,0xd0,0xdc,0xdd,0xde,0xf0),
                              'VFPU instruction in presumed scalar prefix boundary')
                check(int.from_bytes(module[0x08b949ec-0x08804000:0x08b949f0-0x08804000],'little')==0xd0060060,'Missing original predecessor prefix consumption')
                pi=r['events'].index(previous['return']['stop']);check(r['events'][pi+1]==row['dispatch']['stop'],'Unobserved intervening callback stop')
            old=sidecar(row['oldRecord']['raw']);current=sidecar(row['record']['raw'])
            op=dict(kind=('color_'if row['type']==16 else'scale_')+mode,capture=identity(path),capture_row=row['index'],
                    state_bits=list(struct.unpack_from('<%dI'%(size//4),sidecar(before['parameterWindow']['raw']),offset)),
                    previous_key_bits=list(struct.unpack_from('<8I',old)),current_key_bits=list(struct.unpack_from('<8I',current)),
                    relative_time_bits=f[12],previous_relative_time_bits=f[13],expected_bits=list(struct.unpack_from('<%dI'%(size//4),predicted,offset)),
                    instructions=vm.trace,stores=vm.stores,all_retained_parameter_bytes_equal=True,
                    entry_prefix_controls_directly_observed=False,default_entry_prefix_established=established,
                    prefix_basis='Previous same-node type7 vzero consumes prefixes; following dispatcher/record finder are scalar.'if established else'Default-entry-prefix arithmetic is consistent with actual memory; control registers were not exported.')
            operations.append(op)
            if row.get('nested'):
                nested=row['nested'];check(nested['complete']and [nested[k]['stop']['pc']for k in ('dispatch','entry','return')]==[0x08b8fa48,0x08b8f954,0x08b8fa50],'Wrong nested color call')
                ng,nf=registers(nested['entry']['allRegisters']);check(ng[31]==0x08b8fa50 and ng[7]==row['parameterAddress'],'Wrong nested color ABI')
                en=nested['entry'];bn=en['snapshot'];end=nested['return']['snapshot']
                nvm,result=replay(module,row,en,bn,sidecar(end['parameterWindow']['raw']))
                check(int.from_bytes(module[0x08b8fa30-0x08804000:0x08b8fa34-0x08804000],'little')&0xff800000==0x60800000,'Missing immediate wrapper prefix consumption')
                offset=row['parameterAddress']-bn['parameterWindow']['address']
                operations.append(dict(kind='color_evaluate',capture=identity(path),capture_row=row['index'],
                    state_bits=list(struct.unpack_from('<12I',sidecar(bn['parameterWindow']['raw']),offset)),previous_key_bits=[0]*8,current_key_bits=[0]*8,
                    relative_time_bits=nf[12],previous_relative_time_bits=nf[13],expected_bits=list(struct.unpack_from('<12I',result,offset)),
                    instructions=nvm.trace,stores=nvm.stores,all_retained_parameter_bytes_equal=True,
                    entry_prefix_controls_directly_observed=False,default_entry_prefix_established=True,
                    prefix_basis='Original wrapper last vsub consumes all prefixes; subsequent stores/indirect-call setup do not modify them.'))
    report=dict(schema='original-FX-color-scale-proof/v1',passed=True,producer=identity(Path(__file__)),oracle=identity(Path(__file__).with_name('replay_fx_color_scale.py')),
                primary_references=references,captures=captures,operations=operations,actual_operations=len(operations),
                F32_components=sum(len(o['expected_bits'])for o in operations),prefix_established_operations=sum(o['default_entry_prefix_established']for o in operations),
                all_entry_prefix_controls_directly_observed=False,full_FX_lifecycle_verified=False,default_M1_binding_replaced=False,
                limits=['Finite/default-entry-prefix arithmetic only; non-default initial S/T/D prefix semantics are outside this core.',
                        'Actual default prefix is established by the retained predecessor/wrapper for color reset/evaluation, not every captured key/scale entry.',
                        'These samples have constant authored RGBA and zero color velocity; synthetic ramps must not be counted as new original poses.',
                        'No new final GPU pixels or formal UE module execution is established here.'])
    (args.out/'verification.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps(dict(passed=True,operations=len(operations),F32_components=report['F32_components'],prefix_established=report['prefix_established_operations'])))


if __name__=='__main__':main()
