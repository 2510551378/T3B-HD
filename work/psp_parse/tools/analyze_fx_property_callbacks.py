"""Independently bind actual property callbacks to original FEP and replay type155 opcodes."""
import argparse
import json
import struct
from pathlib import Path

from analyze_fx_node_time import (bits, check, identity, number, read, registers,
                                  sha, sidecar, signed, u16, u32, window)


BASE=0x08804000


def code_identity(c,module):
    start,size=c['address'],c['size'];original=module[start-BASE:start-BASE+size]
    check(sidecar(c['original'])==sidecar(c['decoded'])==sidecar(c['expected'])==original,'Runtime original code differs')
    mapping={}
    for line in json.loads(sidecar(c['disasm']))['lines']:
        a,n=line['address'],line['addressSize']
        if a>=start+size or a+n<=start:continue
        check(line['type']in ('opcode','macro')and n%4==0,'Unsupported code identity line')
        words=[line['encoding']]if n==4 else line['macroEncoding']
        check(len(words)==n//4,'Wrong macro words')
        for i,w in enumerate(words):
            pc=a+i*4
            if start<=pc<start+size:
                check(pc not in mapping,'Overlapping original code identity');mapping[pc]=w
    check(b''.join(struct.pack('<I',mapping[a])for a in range(start,start+size,4))==original,'Original disassembly differs')


def original_window(item,asset,base):
    raw=sidecar(item['raw']);off=item['address']-base
    check(off>=0 and off+len(raw)<=len(asset),'Record outside original section')
    expected=bytearray(asset[off:off+len(raw)]);relocated=[]
    for at in range((-item['address'])%4,len(raw)-3,4):
        a,b=u32(expected,at),u32(raw,at)
        if a!=b and a<len(asset) and b==base+a:
            struct.pack_into('<I',expected,at,b);relocated.append(at)
    check(bytes(expected)==raw,'Original FEP window differs beyond exact pointer relocation')
    return relocated


def replay155(module,row,reference_only=False):
    """Small scalar MIPS/COP1 interpreter; execute retained original callback words."""
    entry=row['entry'];g,f=registers(entry['allRegisters']);g=list(g);f=list(f)
    memory={}
    def region(address,raw):
        for i,b in enumerate(raw):
            check(address+i not in memory or memory[address+i]==b,'Inconsistent overlapping retained memory')
            memory[address+i]=b
    region(entry['before']['parameterWindow']['address'],sidecar(entry['before']['parameterWindow']['raw']))
    for key in ('record','oldRecord'):
        item=row[key];check(item is not None,'Missing type155 source record');region(item['address'],sidecar(item['raw']))
    def load(a):
        check(a%4==0 and all(a+i in memory for i in range(4)),'Unretained callback read')
        return u32(bytes(memory[a+i]for i in range(4)))
    stores=[];trace=[];fcc=False
    def execute(pc,delay=False):
        nonlocal fcc
        w=u32(module,pc-BASE);op=w>>26;rs=(w>>21)&31;rt=(w>>16)&31;rd=(w>>11)&31;fd=(w>>6)&31;fn=w&63
        imm=struct.unpack('<h',struct.pack('<H',w&65535))[0];branch=None
        if op==0:
            if fn==8:
                check(not delay,'Nested control in delay slot');branch=(True,g[rs],False)
            elif fn in (0x21,0x25):g[rd]=((g[rs]+g[rt])if fn==0x21 else(g[rs]|g[rt]))&0xffffffff
            elif w==0:pass
            else:raise ValueError('Unsupported scalar callback integer opcode '+hex(w))
        elif op==15:g[rt]=(w&65535)<<16
        elif op==13:g[rt]=g[rs]|(w&65535)
        elif op==0x31:f[rt]=load((g[rs]+imm)&0xffffffff)
        elif op==0x39:
            address=(g[rs]+imm)&0xffffffff
            check(row['parameterAddress']+8<=address<row['parameterAddress']+0x20,'Unexpected type155 store')
            for i,b in enumerate(struct.pack('<I',f[rt])):memory[address+i]=b
            stores.append(dict(pc=pc,address=address,bits=f[rt]))
        elif op==0x11:
            if rs==0:g[rt]=f[rd]
            elif rs==4:f[rd]=g[rt]
            elif rs==8:
                check(not delay,'Nested COP1 branch');branch=(fcc==bool(rt&1),pc+4+imm*4,bool(rt&2))
            elif rs==16 and fn in (0,1,2):
                a,b=number(f[rd]),number(f[rt]);f[fd]=bits(a+b if fn==0 else a-b if fn==1 else a*b)
            elif rs==16 and fn==6:f[fd]=f[rd]
            elif rs==16 and fn==13:
                value=number(f[rd]);check(-2147483648<=value<2147483648,'Unsupported callback trunc domain');f[fd]=int(value)&0xffffffff
            elif rs==20 and fn==32:f[fd]=bits(signed(f[rd]))
            elif rs==16 and fn==60:fcc=number(f[rd])<number(f[rt])
            else:raise ValueError('Unsupported callback COP1 '+hex(w))
        else:raise ValueError('Unsupported callback opcode '+hex(w))
        g[0]=0;trace.append(dict(pc=pc,word=w));return branch
    pc=row['target'];count=0
    while count<512:
        check(row['target']<=pc<row['target']+0x200,'Callback left retained code range')
        control=execute(pc);count+=1
        if control:
            take,target,likely=control
            if take or not likely:execute(pc+4,True);count+=1
            if take and target==entry['stop']['pc']:
                raise ValueError('Unexpected callback self return')
            if take and target==row['return']['stop']['pc']:break
            pc=target if take else pc+8
        else:pc+=4
    else:raise ValueError('Callback instruction bound exceeded')
    p=entry['before']['parameterWindow'];predicted=bytes(memory[p['address']+i]for i in range(p['size']))
    if reference_only:return predicted
    actual=sidecar(row['return']['after']['parameterWindow']['raw'])
    check(predicted==actual,'Original type155 opcode replay differs from actual return memory')
    rg,_=registers(row['return']['allRegisters']);check(g[2]==rg[2],'Original callback return value differs')
    return dict(instructions=count,trace=trace,stores=stores,return_value_bits=g[2],all_retained_parameter_bytes_equal=True)


def audit(path):
    r=read(path);check(r['failure']is None and not r['cleanup']['errors']and not r['externalOrUnverifiedPause'],'Failed or unowned capture')
    check(r['ownedCPU']is None and r['ownedMemory']is None and r['cleanup']['buttonsReleased'],'Unreleased breakpoint/input')
    lifecycle=read(path.parent/'process_completed.json');check(lifecycle['node_exit_code']==0 and lifecycle['owned_emulator_stopped']and lifecycle['protection_passed'],'Nonterminal/failed runner')
    check(not r['initialCPU']['breakpoints']and not r['initialMemory']['breakpoints'],'Preexisting breakpoint')
    mode=r.get('mode','reset');dispatch=0x08b68ce4 if mode=='reset'else 0x08b68ad4;ret=dispatch+8
    module=Path(r['module']['file']).read_bytes();asset=Path(r['FEP']['file']).read_bytes()
    check(sha(module)==r['module']['sha256']=='b5fc590366fc610f2cdd60104a4a28851bacd402c4600a4c296776e1dea0869f','Wrong original module')
    check(sha(asset)==r['FEP']['sha256']=='97443c71b1c1d644f323c6ff611afb740329cfe11a47a711f39dc59de06ec802','Wrong original FEP')
    check(identity(path.parent/'executed_trace_fx_property_callbacks.js')['sha256']==r['producer']['sha256'],'Launch-time producer differs')
    active=None
    for t in r['transitions']:
        if t['operation']=='CPU_add_requested':check(active is None,'Overlapping owned breakpoints');active=t['address']
        elif t['operation']=='CPU_remove':check(active==t['address'],'Wrong breakpoint removal');active=None
        else:raise ValueError('Unexpected breakpoint transition')
    check(active is None,'Breakpoint left active')
    for c in r['code']:code_identity(c,module)
    s=r['selection'];base=s['FEPbase'];sb=sidecar(s['state']);nb=sidecar(s['node']);cb=sidecar(s['context']);sg,_=registers(s['allRegisters'])
    check(s['stop']['pc']==0x08b69d64 and sg[10]==0x08b9a514 and sg[5]==s['C']and sg[17]==s['N'],'Wrong visual handler selection')
    check(u32(cb,0x8c)==s['P']and u32(cb,0x90)==s['N']and u32(nb,0x40)==base+0x10c78==s['descriptor'],'Wrong selected node/descriptor')
    check(u32(sb,0x190)==base and u32(sb,0x198)==base+0x48f0 and sidecar(s['resource'])==asset[0x48f0:0x49b0],'Wrong original effect resource')
    i=s['identityRaw'];primary=window(i['primaryHandle'],s['handle'],4);af=window(i['actorFields'],s['actor']+0x3c4,40);mh=window(i['metadataHeader'],s['metadata'],64);dh=window(i['drawHeader'],s['drawTable'],16)
    check(u32(sb,0x144)==s['handle']and u32(primary)==s['actor']and u32(af)==s['sourceBase']and u32(af,0x24)==s['metadata']and u32(mh,0x34)==s['drawTable']and u16(mh,6)==3,'Rifle identity chain differs')
    check(u16(dh,4)==243 and u32(dh,12)==0x522 and sha(struct.pack('<I',0x522)+sidecar(s['geometry']))=='168578abca4c4f5d22d5994ebced6b93a25d5167428bfd47f1a1150a8d42e65a','Wrong rifle geometry')
    bindings=[];operations=[]
    for row in r['rows']:
        check(row.get('complete')and row['dispatch']['stop']['pc']==dispatch and row['entry']['stop']['pc']==row['target']and row['return']['stop']['pc']==ret,'Incomplete callback triple')
        check(row['dispatch']['stop']['ticks']<row['entry']['stop']['ticks']<row['return']['stop']['ticks'],'Nonexecuted callback stages')
        dg,df=registers(row['dispatch']['allRegisters']);eg,ef=registers(row['entry']['allRegisters'])
        check(dg[20]==s['N']and dg[30]==s['C']if mode=='reset'else dg[17]==s['N']and dg[16]==s['C'],'Wrong dispatch node/context')
        check(dg[9 if mode=='reset'else 10]==row['target']and eg[31]==ret and eg[4]==dg[4]and eg[5]==s['C']and eg[6]==row['callbackInputRecord']==dg[6],'Wrong dynamic target/ABI')
        check(eg[7]==row['parameterAddress']==dg[17 if mode=='reset'else 7]and eg[8]==row['oldInputRecord']==dg[8 if mode=='reset'else 11]and ef[12:14]==df[12:14],'Delay-slot arguments differ')
        before=row['entry']['before'];n=sidecar(before['node']);p=sidecar(before['state']);d=sidecar(before['descriptor']);count=d[8];index=row['definitionIndex']
        check(u32(n,0x40)==s['descriptor']and u32(p,0x190)==base and u32(p,0x198)==base+0x48f0 and u32(p,0x144)==s['handle']and u32(sidecar(before['primaryHandle']))==s['actor'],'Callback object identity changed')
        original_window(dict(address=s['descriptor'],raw=before['descriptor']),asset,base)
        defs=window(before['definitionTable'],u32(d,0x1c),count*4);original_window(before['definitionTable'],asset,base)
        definition=window(row['definition'],u32(defs,index*4),4);original_window(row['definition'],asset,base)
        check(u16(definition)==row['type']and row['parameterAddress']==u32(n,0x44)+u16(definition,2),'Definition class/parameter offset differs')
        registry=window(row['registrySlot'],0x08c3a820+4*row['type'],4);obj=sidecar(row['typeObject']['raw']);vt=sidecar(row['vtable']['raw']);slot=0x30 if mode=='reset'else 0x10
        check(u32(registry)==dg[4]==row['typeObject']['address']and u32(obj)==row['vtable']['address']and struct.unpack_from('<h',vt,slot)[0]==0 and u32(vt,slot+4)==row['target'],'Actual class vtable binding differs')
        slots=window(before['parameterTable'],u32(n,0x48),count*4);times=window(before['timeTable'],u32(n,0x4c),count*4)
        check(u32(slots,index*4)==eg[6],'Installed record pointer differs')
        reloc={}
        for key in ('record','oldRecord'):
            item=row[key]
            if item is not None:reloc[key]=original_window(item,asset,base)
        binding=dict(capture=identity(path),row=row['index'],mode=mode,definition_index=index,type=row['type'],target=row['target'],
                     parameter_offset=u16(definition,2),record_offset=eg[6]-base if eg[6]else None,time_slot_offset=u32(times,index*4)-base,
                     f12_bits=ef[12],f13_bits=ef[13],source_relocated_cells=reloc)
        if row['type']==155:
            expected_target=0x08b9ad1c if mode=='reset'else 0x08b9a3ec;check(row['target']==expected_target,'Unrecognized type155 implementation')
            limit=0x08b9aebc if mode=='reset'else 0x08b9a514
            check(any(c['address']<=row['target']and c['address']+c['size']>=limit for c in r['code']),'Full original callback code was not retained')
            binding['original_opcode_replay']=replay155(module,row)
            pw=before['parameterWindow'];offset=row['parameterAddress']-pw['address'];a=sidecar(pw['raw']);b=sidecar(row['return']['after']['parameterWindow']['raw'])
            check(a[:offset+8]==b[:offset+8]and a[offset+32:]==b[offset+32:],'Type155 touched outside its six scalar fields')
            operations.append(dict(mode=mode,state_bits=list(struct.unpack_from('<6I',a,offset+8)),
              previous_key_bits=list(struct.unpack_from('<6I',sidecar(row['oldRecord']['raw']),0x10)),
              current_key_bits=list(struct.unpack_from('<6I',sidecar(row['record']['raw']),0x10)),
              relative_time_bits=ef[12],previous_relative_time_bits=ef[13],expected_bits=list(struct.unpack_from('<6I',b,offset+8)),capture_row=row['index']))
        bindings.append(binding)
    return dict(capture=identity(path),mode=mode,callbacks=len(bindings),bindings=bindings,operations=operations)


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--capture',type=Path,action='append',required=True);p.add_argument('--out',type=Path,required=True)
    args=p.parse_args();check(not args.out.exists(),'Never replace property proof');args.out.mkdir(parents=True)
    captures=[audit(p)for p in args.capture]
    result=dict(schema='original-FX-property-callback-proof/v1',passed=True,captures=captures,producer=identity(Path(__file__)),
                callbacks=sum(c['callbacks']for c in captures),type155_operations=sum(len(c['operations'])for c in captures),
                full_FX_lifecycle_verified=False,default_M1_binding_replaced=False,
                limits=['Bindings cover all captured classes; scalar opcode/return-memory equivalence is established only for type155.',
                        'Bounded parameter windows are raw observations, not recovered allocation sizes. Only six type155 scalar fields are implemented.',
                        'This proof does not name anatomical bones, prove gameplay bullet origins, establish time units, or run formal UE.'])
    (args.out/'verification.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps(dict(passed=True,callbacks=result['callbacks'],type155_operations=result['type155_operations'])))


if __name__=='__main__':main()
