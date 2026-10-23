"""Bind actual modifier targets, full instruction paths and RNG states to original resources."""
import argparse,json,struct
from pathlib import Path
from analyze_fx_node_time import check,sidecar,registers,number,bits,u32,u16,read,identity
from analyze_fx_property_callbacks import audit,original_window
from replay_fx_random_modifiers import Machine,vfpu_registers
from verify_weapon_ge_matrix_math import vindices

def references(v,seen=None):
    seen={}if seen is None else seen
    if isinstance(v,dict):
        if 'file'in v and 'sha256'in v:
            name=v['file'];check(name not in seen or seen[name]==v['sha256'],'Conflicting retained sidecar identities');seen[name]=v['sha256'];sidecar(v)
        else:
            for item in v.values():references(item,seen)
    elif isinstance(v,list):
        for item in v:references(item,seen)
    return seen

def audit_capture(path):
    original=read(path);check(original.get('randomDetails')and original['mode']=='key','Missing actual random observation mode')
    references(original['rows']);base=audit(path);module=Path(original['module']['file']).read_bytes();fep=Path(original['FEP']['file']).read_bytes();selection=original['selection'];result=[]
    for row in original['rows']:
        if row['type']not in(23,24):continue
        rnd=row['random'];check(rnd['complete']and not rnd.get('skippedByNodeFlag'),'No complete active modifier')
        check([c['channel']for c in rnd['channels']]==[0,1,2],'Incomplete original channel loop')
        header=sidecar(rnd['activeDefinitionHeader']['raw']);ctx=sidecar(row['entry']['before']['context']);node=sidecar(row['entry']['before']['node'])
        check(rnd['activeDefinitionHeader']['address']==u32(ctx,0x94),'Modifier active definition differs')
        original_window(rnd['activeDefinitionHeader'],fep,selection['FEPbase']);original_window(rnd['targetOffset'],fep,selection['FEPbase'])
        check(rnd['targetOffset']['address']==u32(header,8)+u32(header,4)*2,'Original target lookup differs')
        offset=u16(sidecar(rnd['targetOffset']['raw']));resolved=selection['N']+0x60+offset
        check(resolved==rnd['resolvedBase'],'Resolved internal write target differs')
        window=row['entry']['before']['parameterWindow'];relative=resolved-window['address'];check(0<=relative<=window['size']-64,'Resolved bounded target unavailable')
        tables=sidecar(rnd['tables']['raw']);constants=sidecar(rnd['vectorConstants']['raw']);cache=sidecar(rnd['vectorCache']['raw'])
        for item in (rnd['tables'],rnd['vectorConstants']):
            start=item['address']-0x08804000;check(sidecar(item['raw'])==module[start:start+item['size']],'Runtime static modifier data differs from module')
        before=sidecar(window['raw']);after=sidecar(row['return']['after']['parameterWindow']['raw']);channels=[];rng=[]
        center=list(struct.unpack_from('<3I',cache if u32(cache,16)else constants))
        for c in rnd['channels']:
            k=c['channel'];start=0 if row['type']==23 else 16;enabled,mode,vector=[tables[start+d+k]for d in(0,3,6)]
            record=sidecar(row['record']['raw']);check((enabled,mode,vector)==(c['enabledOffset'],c['modeOffset'],c['vectorOffset'])and c['enabled']==bool(record[enabled])and c['mode']==record[mode],'Original per-channel operands differ')
            g,_=registers(c['loop']['allRegisters']);check(g[24 if row['type']==23 else 18]==k,'Original channel GPR differs')
            if row['type']==23:check(g[25]==resolved,'Internal type23 destination base differs')
            else:check(g[17]==resolved,'Internal type24 destination base differs')
            samples=[0,0,0]
            if c['enabled']and row['type']==23:
                vr=c['vectorRandom'];pc=vr['stop']['pc'];expected=0x08bb8ebc if c['mode']==1 else 0x08bb8f68 if c['mode']==2 else 0x08bb8e24
                check(pc==expected and u32(module,pc-4-0x08804000)==0xd0238000,'Wrong original VRNDF2 continuation');vfpu=vfpu_registers(vr['allRegisters']);samples=[vfpu[i]for i in vindices(0,3)]
                check(all(2<=number(x)<4 for x in samples),'Original random vector outside VRNDF2 range')
            for call in c['rng']:
                sg,_=registers(call['entry']['allRegisters']);rg,_=registers(call['return']['allRegisters']);seed_before=u32(sidecar(call['entry']['seed']['raw']));seed_after=u32(sidecar(call['return']['seed']['raw']))
                root=u32(sidecar(call['entry']['seedRoot']['raw']));check(call['entry']['seed']['address']==root+0x58 and call['return']['seed']['address']==root+0x58,'Wrong original scalar seed object')
                check(call['entry']['stop']['pc']==0x08afc000 and call['return']['stop']['pc']==sg[31]==call['returnPC'],'Wrong original scalar RNG ABI')
                check(seed_after==(seed_before*1103515245+12345)&0xffffffff and rg[2]==seed_after&0x7fffffff,'Original LCG transition/return differs')
                if rng:check(rng[-1]['seed_after']==seed_before,'Original RNG seed chain is discontinuous')
                rng.append(dict(seed_before=seed_before,seed_after=seed_after,return_bits=rg[2],return_pc=sg[31]))
            channels.append(dict(enabled=c['enabled'],mode=c['mode'],amplitude_bits=list(struct.unpack_from('<3I',record,vector)),observed_VRNDF2_bits=samples))
        machine=Machine(module,row);oracle=machine.run()
        check(machine.window_bytes()==after,'Complete original modifier window differs')
        operation=dict(type=row['type'],capture=identity(path),row=row['index'],parameter_address=row['parameterAddress'],resolved_address=resolved,
                       resolved_offset_in_parameter_window=relative,target_lookup_offset=offset,
                       before_bits=list(struct.unpack_from('<16I',before,relative)),expected_after_bits=list(struct.unpack_from('<16I',after,relative)),
                       independent_axes=bool(sidecar(row['record']['raw'])[12]),channels=channels,vector_center_bits=center,
                       seed_before=rng[0]['seed_before']if rng else 0,seed_after=rng[-1]['seed_after']if rng else 0,
                       scalar_rng_calls=rng,opcode_replay=oracle,
                       observed_changed_offsets=[i for i in range(0,window['size'],4)if before[i:i+4]!=after[i:i+4]])
        check(relative==(0x20 if row['type']==23 else 0x60),'Unexpected selected descriptor target binding')
        result.append(operation)
    check([o['type']for o in result]==[23,24],'Incomplete selected modifier pair')
    return dict(passed=True,source_capture=identity(path),base_audit=base,operations=result,
                original_vector_RNG_controls_recovered=False,original_timing_seconds_recovered=False,
                scope='Type23 arithmetic consumes observed VRNDF2 vectors; type24 includes original scalar LCG state and generated outputs.')

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--capture',type=Path,required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args()
    check(not a.out.exists(),'Never overwrite modifier audit');a.out.mkdir(parents=True);result=audit_capture(a.capture)
    (a.out/'verification.json').write_text(json.dumps(result,indent=2),encoding='utf-8');print(json.dumps(dict(passed=True,callbacks=2,source_offsets=[o['resolved_offset_in_parameter_window']for o in result['operations']],scalar_rng_calls=sum(len(o['scalar_rng_calls'])for o in result['operations']))))
