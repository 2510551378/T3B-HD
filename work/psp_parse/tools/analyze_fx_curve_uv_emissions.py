"""Audit type155 time/curve evaluation through original texture binder and emitted GE words."""
import argparse
import json
import struct
from pathlib import Path

import numpy as np
from analyze_fx_node_time import bits,check,identity,number,read,registers,sha,sidecar,u16,u32,window
from analyze_fx_property_callbacks import code_identity,original_window


def fadd(a,b):return bits(np.float32(number(a))+np.float32(number(b)))
def fmul(a,b):return bits(np.float32(number(a))*np.float32(number(b)))


def evaluate(state,t):
    tt=fmul(t,t);output=[]
    for k in range(2):
        output.append(fadd(fadd(fmul(fmul(state[4+k],bits(0.5)),tt),fmul(state[2+k],t)),state[k]))
    return output


def normalize(values,width,height,group):
    result=[]
    for value,size,offset in zip(values,(width,height),group):
        size=np.float32(size);v=np.float32(number(value));iterations=0
        while v<0 or v>size:
            iterations+=1;check(iterations<=65536,'Reference normalization bound')
            v=np.float32(v+size if v<0 else v-size)
        result.append(bits(np.float32(v/size)+np.float32(number(offset))))
    return result


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--capture',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    args=p.parse_args();check(not args.out.exists(),'Never replace emitted UV proof');args.out.mkdir(parents=True)
    r=read(args.capture)
    check(r['failure']is None and not r['cleanup']['errors']and not r['externalOrUnverifiedPause']and r['ownedCPU']is None and r['ownedMemory']is None and r['cleanup']['buttonsReleased'],'Incomplete/unowned UV capture')
    check(not r['initialCPU']['breakpoints']and not r['initialMemory']['breakpoints'],'Preexisting breakpoint')
    lifecycle=read(args.capture.parent/'process_completed.json');check(lifecycle['node_exit_code']==0 and lifecycle['owned_emulator_stopped']and lifecycle['protection_passed'],'Runner not successful/terminal')
    active=None
    for t in r['transitions']:
        if t['operation']=='CPU_add_requested':check(active is None,'Overlapping breakpoint');active=t['address']
        elif t['operation']=='CPU_remove':check(active==t['address'],'Wrong breakpoint removal');active=None
        else:raise ValueError('Unknown breakpoint transition')
    check(active is None,'Unreleased breakpoint')
    check(identity(args.capture.parent/'executed_trace_fx_curve_uv_emissions.js')['sha256']==r['producer']['sha256'],'Executed observer changed')
    module=Path(r['module']['file']).read_bytes();asset=Path(r['FEP']['file']).read_bytes()
    check(sha(module)==r['module']['sha256']=='b5fc590366fc610f2cdd60104a4a28851bacd402c4600a4c296776e1dea0869f','Wrong original module')
    check(sha(asset)==r['FEP']['sha256']=='97443c71b1c1d644f323c6ff611afb740329cfe11a47a711f39dc59de06ec802','Wrong original FEP')
    for c in r['code']:code_identity(c,module)
    for start,end in ((0x08b9a514,0x08b9ad1c),(0x08bbfbc4,0x08bbfcc8),(0x08c00aa8,0x08c00aec),(0x08b5ecac,0x08b5ee80)):
        check(any(c['address']<=start and c['address']+c['size']>=end for c in r['code']),'Missing full relevant original code')
    s=r['selection'];base=s['FEPbase'];g,_=registers(s['allRegisters']);n=sidecar(s['node']);state=sidecar(s['state']);ctx=sidecar(s['context'])
    check(s['stop']['pc']==0x08b69d64 and g[10]==0x08b9a514 and g[5]==s['C']and g[17]==s['N']and u32(ctx,0x8c)==s['P']and u32(ctx,0x90)==s['N'],'Wrong selected render callback')
    check(u32(n,0x40)==s['descriptor']==base+0x10c78 and u32(state,0x190)==base and u32(state,0x198)==base+0x48f0 and sidecar(s['resource'])==asset[0x48f0:0x49b0],'Wrong selected FEP source')
    i=s['identityRaw'];primary=window(i['primaryHandle'],s['handle'],4);af=window(i['actorFields'],s['actor']+0x3c4,40);mh=window(i['metadataHeader'],s['metadata'],64);dh=window(i['drawHeader'],s['drawTable'],16)
    check(u32(state,0x144)==s['handle']and u32(primary)==s['actor']and u32(af)==s['sourceBase']and u32(af,0x24)==s['metadata']and u32(mh,0x34)==s['drawTable']and u16(mh,6)==3,'Rifle pointer identity differs')
    check(u16(dh,4)==243 and u32(dh,12)==0x522 and sha(struct.pack('<I',0x522)+sidecar(s['geometry']))=='168578abca4c4f5d22d5994ebced6b93a25d5167428bfd47f1a1150a8d42e65a','Wrong original rifle geometry')
    operations=[]
    for row in r['rows']:
        check(row['complete'],'Incomplete UV row');stages=[row[k]for k in ('dispatch','evaluation','textureBind','offsetEmitter','offsetReturn')]
        check([x['stop']['pc']for x in stages]==[0x08b69d64,0x08b9a71c,0x08bbfbc4,0x08c00aa8,0x08bbfcbc],'Wrong UV stage chain')
        ticks=[x['stop']['ticks']for x in stages];check(all(a<b for a,b in zip(ticks,ticks[1:])),'UV stages did not execute in order')
        (dg,df),(eg,ef),(bg,bf),(ug,uf),(rg,rf)=[registers(x['allRegisters'])for x in stages]
        check(dg[10]==0x08b9a514 and dg[5]==eg[17]==s['C']and dg[17]==s['N'],'Different source render invocation')
        states=[]
        for before in (row['dispatch']['before'],row['evaluation']['before']):
            nb=sidecar(before['node']);pb=sidecar(before['state']);db=sidecar(before['descriptor'])
            check(u32(nb,0x40)==s['descriptor']and u32(pb,0x190)==base and u32(pb,0x198)==base+0x48f0 and u32(pb,0x144)==s['handle']and u32(sidecar(before['primaryHandle']))==s['actor'],'Render identity changed')
            original_window(dict(address=s['descriptor'],raw=before['descriptor']),asset,base)
            slot=window(before['definitionSlot'],u32(db,0x1c)+36,4);definition=window(before['definition'],u32(slot),4);original_window(before['definition'],asset,base)
            check(u16(definition)==155,'Different property class')
            parameter=window(before['parameter'],u32(nb,0x44)+u16(definition,2),32)
            record=window(before['installedRecordSlot'],u32(nb,0x48)+36,4)
            check(u32(record)==base+0x11a40,'Different actual type155 original data record')
            states.append(parameter)
        check(states[0]==states[1],'Curve state changed during evaluation')
        sb=list(struct.unpack_from('<6I',states[0],8));evaluated=evaluate(sb,df[12])
        check(evaluated==[ef[20],ef[24]]==[bf[12],bf[13]],'Original evaluated curve/binder input differs')
        check(bg[31]in (0x08b5edd0,0x08b5e94c)and ug[31]==0x08bbfcbc,'Unexpected binder/emitter caller')
        bind=row['textureBind'];bank=window(bind['bank'],bg[4],4);slot=window(bind['slot'],u32(bank)+bg[5]*4,4);obj=window(bind['object'],u32(slot),4);header=window(bind['header'],u32(obj),0x24)
        width,height=struct.unpack_from('<2i',header,0x1c);check(width>0 and height>0,'Invalid actual texture dimensions')
        normalized=normalize(evaluated,width,height,[bf[14],bf[15]])
        check(normalized==[uf[12],uf[13]],'Original texture normalized offset differs')
        emitter,ret=row['offsetEmitter'],row['offsetReturn'];global_before=window(emitter['global'],0x08ca31d8,4);context_address=u32(global_before)
        before_context=window(emitter['context'],context_address,12);cursor=u32(before_context,8)
        check(cursor==emitter['cursor']and window(ret['global'],0x08ca31d8,4)==global_before,'DL context changed')
        check(u32(window(ret['context'],context_address,12),8)==cursor+8,'UV emitter cursor advance differs')
        physical=cursor-0x40000000 if 0x48000000<=cursor<0x4c000000 else cursor
        commands=window(ret['commands'],physical,8);expected=[0x4a000000|(uf[12]>>8),0x4b000000|(uf[13]>>8)]
        check(ret['commands']['guestCursor']==cursor and list(struct.unpack('<2I',commands))==expected,'Actual emitted UV OFFSET words differ')
        operations.append(dict(row=row['index'],relative_time_bits=df[12],state_bits=sb,width=width,height=height,group_offset_bits=[bf[14],bf[15]],
                               expected_evaluation_bits=evaluated,expected_normalized_bits=normalized,expected_command_words=expected))
    check(len(operations)==6,'Unexpected actual UV invocation count')
    report=dict(schema='original-FX-curve-UV-emission-proof/v1',passed=True,capture=identity(args.capture),producer=identity(Path(__file__)),
                module=identity(Path(r['module']['file'])),operations=operations,actual_render_invocations=len(operations),emitted_UV_words=2*len(operations),
                new_GE_consumption_capture_verified=False,default_M1_binding_replaced=False,full_FX_lifecycle_verified=False,
                limits=['The actual CPU command writes are observed; this capture does not separately record their GPU/GE consumption or final pixels.',
                        'Six calls cover this rifle type155/descriptor10c78 only; no original CLUT pixel identity is inferred from dimensions alone.',
                        'Curve evaluation and width/height normalization have direct runtime FPU evidence. Other classes and full FX events remain unported.'])
    (args.out/'verification.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps(dict(passed=True,render_invocations=len(operations),emitted_words=2*len(operations))))


if __name__=='__main__':main()
