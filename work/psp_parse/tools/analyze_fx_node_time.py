"""Audit actual successive-write observations and replay original clock slices."""
import argparse
import hashlib
import json
import math
import struct
from pathlib import Path


def check(v,why):
    if not v:
        raise ValueError(why)


def read(p):
    return json.loads(p.read_text(encoding='utf-8-sig'))


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def identity(p):
    return dict(file=str(p.resolve()),sha256=sha(p.read_bytes()))


def sidecar(item):
    b=Path(item['file']).read_bytes()
    check(len(b)==item['bytes'] and sha(b)==item['sha256'],'Retained sidecar differs')
    return b


def window(item,address,size):
    check(item['address']==address and item['size']==size,'Window address/size differs')
    return sidecar(item['raw'])


def u32(b,at=0):return struct.unpack_from('<I',b,at)[0]
def u16(b,at=0):return struct.unpack_from('<H',b,at)[0]
def number(bits):return struct.unpack('<f',struct.pack('<I',bits))[0]
def bits(value):return struct.unpack('<I',struct.pack('<f',value))[0]
def signed(word):return word-(1<<32) if word&0x80000000 else word


def registers(item):
    r=json.loads(sidecar(item))
    g=next(c['uintValues'] for c in r['categories'] if c['name']=='GPR')[:32]
    f=next(c['uintValues'] for c in r['categories'] if c['name']=='FPU')[:32]
    check(len(g)==len(f)==32 and g[0]==0,'Invalid captured register categories')
    return g,f


def replay_wrap(module,time_bits,start,end):
    """08b68e04..e50: actual straight-line instructions, not a fmod formula."""
    g=[0]*32;f=[0]*32;g[16],g[17],g[19]=0x09000000,0x09001000,end
    memory={g[16]+0x30:struct.pack('<I',time_bits),g[17]+0xc:struct.pack('<H',start),g[17]+0xe:struct.pack('<H',end)}
    trace=[];hi=None;stored=None
    for pc in range(0x08b68e04,0x08b68e50,4):
        w=u32(module,pc-0x08804000);op=w>>26;rs=(w>>21)&31;rt=(w>>16)&31;rd=(w>>11)&31;fd=(w>>6)&31;fun=w&63;imm=struct.unpack('<h',struct.pack('<H',w&65535))[0]
        if op in (0x31,0x25):
            address=(g[rs]+imm)&0xffffffff
            check(address in memory,'Clock slice unretained memory')
            if op==0x31:f[rt]=u32(memory[address])
            else:g[rt]=u16(memory[address])
        elif op==0x39:
            check((g[rs]+imm)&0xffffffff==0x09000030,'Wrong original clock store destination')
            stored=f[rt]
        elif op==0x11:
            if rs==0:g[rt]=f[rd]
            elif rs==4:f[rd]=g[rt]
            elif rs==16 and fun==13:f[fd]=int(number(f[rd]))&0xffffffff
            elif rs==20 and fun==32:f[fd]=bits(signed(f[rd]))
            elif rs==16 and fun==0:f[fd]=bits(number(f[rd])+number(f[rt]))
            elif rs==16 and fun==1:f[fd]=bits(number(f[rd])-number(f[rt]))
            else:raise ValueError('Unknown clock COP1 instruction')
        elif op==0 and fun==0x23:g[rd]=(g[rs]-g[rt])&0xffffffff
        elif op==0 and fun==0x1a:
            a,b=signed(g[rs]),signed(g[rt]);check(b!=0,'Invalid original integer loop interval')
            q=abs(a)//abs(b);q=-q if (a<0)!=(b<0) else q;hi=(a-q*b)&0xffffffff
        elif op==0 and fun==0x10:
            check(hi is not None,'Uninitialized original HI');g[rd]=hi
        else:raise ValueError('Unknown original clock instruction '+hex(w))
        trace.append(dict(pc=pc,word=w,f12_bits=f[12]))
    check(stored is not None,'Original clock store absent')
    return stored,trace


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--capture',type=Path,required=True)
    parser.add_argument('--out',type=Path,required=True)
    args=parser.parse_args();check(not args.out.exists(),'Never replace clock proof');args.out.mkdir(parents=True)
    r=read(args.capture)
    check(r['failure'] is None and not r['cleanup']['errors'] and not r['externalOrUnverifiedPause'],'Incomplete/failed clock observation')
    check(r['ownedCPU'] is None and r['ownedMemory'] is None and r['cleanup']['buttonsReleased'],'Breakpoint/input ownership not released')
    lifecycle=read(args.capture.parent/'process_completed.json')
    check(lifecycle['node_exit_code']==0 and lifecycle['owned_emulator_stopped'] and lifecycle['protection_passed'],'Runner lifecycle/protection differs')
    module=Path(r['module']['file']).read_bytes();asset=Path(r['FEP']['file']).read_bytes()
    check(sha(module)==r['module']['sha256']=='b5fc590366fc610f2cdd60104a4a28851bacd402c4600a4c296776e1dea0869f','Wrong original module')
    check(sha(asset)==r['FEP']['sha256']=='97443c71b1c1d644f323c6ff611afb740329cfe11a47a711f39dc59de06ec802','Wrong source FEP section')
    executed=args.capture.parent/'executed_trace_fx_node_time_writes.js'
    check(sha(executed.read_bytes())==r['producer']['sha256'],'Actual producer identity differs')
    for c in r['code']:
        expected=module[c['address']-0x08804000:c['address']-0x08804000+c['size']]
        check(sidecar(c['original'])==sidecar(c['decoded'])==sidecar(c['expected'])==expected,'Original code restore differs')
        d=json.loads(sidecar(c['disasm']));mapping={}
        for l in d['lines']:
            if l['address']>=c['address']+c['size'] or l['address']+l['addressSize']<=c['address']:continue
            values=[l['encoding']]if l['addressSize']==4 else l['macroEncoding']
            check(l['type']in ('opcode','macro') and len(values)==l['addressSize']//4,'Invalid original disassembly')
            for j,w in enumerate(values):
                at=l['address']+4*j
                if c['address']<=at<c['address']+c['size']:
                    check(at not in mapping,'Overlapping code');mapping[at]=w
        check(b''.join(struct.pack('<I',mapping[a])for a in range(c['address'],c['address']+c['size'],4))==expected,'Disassembly does not reconstruct original code')
    check(not r['initialCPU']['breakpoints'] and not r['initialMemory']['breakpoints'],'Existing breakpoints were present')
    active=None
    for t in r['transitions']:
        if t['operation'].endswith('add_requested'):
            check(active is None,'Overlapping owned breakpoints');active=(t['operation'].split('_')[0],t['address'])
        elif t['operation'].endswith('_remove'):
            check(active==(t['operation'].split('_')[0],t['address']),'Breakpoint removal differs');active=None
    check(active is None,'Owned breakpoint left active')
    s=r['selection'];node=sidecar(s['node']);state=sidecar(s['state']);context=sidecar(s['context']);g,f=registers(s['allRegisters'])
    check(s['stop']['pc']==0x08b69d64 and g[10]==0x08b9a514 and g[5]==s['C'] and g[17]==s['N'],'Wrong source callback selection')
    check(u32(context,0x8c)==s['P'] and u32(context,0x90)==s['N'],'Selected context identity differs')
    check(u32(state,0x190)==s['FEPbase'] and u32(state,0x198)==s['FEPbase']+0x48f0 and u32(node,0x40)==s['descriptor']==s['FEPbase']+0x10c78,'Selected FEP/node pointers differ')
    check(sidecar(s['resource'])==asset[0x48f0:0x49b0],'Selected original FEP192 differs')
    i=s['identityRaw'];primary=window(i['primaryHandle'],s['handle'],4);fields=window(i['actorFields'],s['actor']+0x3c4,40);mh=window(i['metadataHeader'],s['metadata'],64);dh=window(i['drawHeader'],s['drawTable'],16)
    check(u32(state,0x144)==s['handle'] and u32(primary)==s['actor'] and u32(fields)==s['sourceBase'] and u32(fields,0x24)==s['metadata'] and u32(mh,0x34)==s['drawTable'] and u16(mh,6)==3,'Actual rifle pointer chain differs')
    check(u16(dh,4)==243 and u32(dh,12)==0x522 and sha(struct.pack('<I',0x522)+sidecar(s['geometry']))=='168578abca4c4f5d22d5994ebced6b93a25d5167428bfd47f1a1150a8d42e65a','Original rifle geometry differs')
    operations=[];pairs=[];pending=0
    for n,row in enumerate(r['rows']):
        b=row['before'];nb=sidecar(b['node']);pb=sidecar(b['state']);db=sidecar(b['descriptor']);cb=sidecar(b['context']);g,f=registers(row['allRegisters'])
        check(u32(nb,0x30)==b['timeBits'] and u32(nb,0x40)==s['descriptor'],'Snapshot time/node fields differ')
        check(u32(pb,0x190)==s['FEPbase'] and u32(pb,0x198)==s['FEPbase']+0x48f0 and u32(pb,0x144)==s['handle'] and u32(sidecar(b['primaryHandle']))==s['actor'],'Parent/actor identity differs')
        check(db[0xc:0x10]==asset[0x10c78+0xc:0x10c78+0x10],'Live loop range differs from original asset')
        pc=row['stop']['pc'];w=u32(module,pc-0x08804000);branch=(w>>26)==0x11 and ((w>>21)&31)==8;store=pc+4 if branch else pc;sw=u32(module,store-0x08804000)
        rs,rt,imm=(sw>>21)&31,(sw>>16)&31,struct.unpack('<h',struct.pack('<H',sw&65535))[0]
        check(sw>>26==0x39 and (g[rs]+imm)&0xffffffff==s['N']+0x30,'Stop is not owned original F32 clock store')
        check(row['writer']['pc']==store and row['writer']['expectedBits']==f[rt],'Producer store prediction differs from actual registers')
        if store==0x08b683f8:
            check(sw==0xe48c0030 and u32(module,0x08b683e8-0x08804000)==0x46166300,'Wrong original advance slice')
            check(u32(pb,0x130)==f[22],'Effective delta does not match parent130')
            predicted=bits(number(b['timeBits'])+number(f[22]));op=dict(kind=0,a_bits=b['timeBits'],b_bits=f[22],x=0,y=0)
            trace=[]
        elif store==0x08b68e4c:
            check(g[16]==s['N'] and g[17]==s['descriptor'] and g[19]==u16(db,0xe),'Original wrap pointer/bound differs')
            predicted,trace=replay_wrap(module,b['timeBits'],u16(db,0xc),u16(db,0xe));op=dict(kind=1,a_bits=b['timeBits'],b_bits=0,x=u16(db,0xc),y=u16(db,0xe))
        else:raise ValueError('Unclassified original time writer')
        check(predicted==f[rt],'Original clock arithmetic differs from actual store source')
        if not row.get('effectObservedAtNextWriteStop'):
            check(n==len(r['rows'])-1 and 'nextObservation'not in row,'Unverified middle observation');pending+=1;continue
        check(n+1<len(r['rows']),'Missing following observed write')
        following=r['rows'][n+1];check(row['nextObservation']==dict(stop=following['stop'],before=following['before']),'Next observation is not actual following stop')
        nextbits=u32(sidecar(following['before']['node']),0x30)
        check(nextbits==predicted and following['stop']['ticks']>row['stop']['ticks'],'Actual subsequent field differs from original store')
        op['expected_bits']=nextbits;op['CPU_writer_pc']=store;operations.append(op)
        pairs.append(dict(index=n,writer_pc=store,before_bits=b['timeBits'],after_observed_bits=nextbits,observed_at_following_write=True,original_instruction_trace=trace,
            context_delta10_bits=u32(cb,0x10),state_rate1b4_bits=u32(pb,0x1b4),effective_delta130_bits=u32(pb,0x130)))
    check(pending==1 and len(pairs)==8,'Unexpected completed/pending clock coverage')
    t=s['dispatchTime'];slot=u32(node,0x4c)+9*4;ptr=u32(window(t['slot'],slot,4));_,f=registers(s['allRegisters']);start=0
    check(t['f20Bits']==f[20]==u32(node,0x30) and t['f12Bits']==f[12] and ptr==t['recordPointer'],'Dispatch time/register provenance differs')
    if ptr:
        q=t['signedStart'];field=ptr+4;check(q['fieldAddress']==field and q['byteOffset']==field-(field&~3),'Wrong signed start address')
        start=struct.unpack_from('<h',window(q['window'],field&~3,4),q['byteOffset'])[0]
    actual=bits(number(f[20])-start) if ptr else f[20]
    check(actual==f[12],'Original signed-start time subtraction differs')
    operations.append(dict(kind=2,a_bits=f[20],b_bits=0,x=int(ptr!=0),y=start,expected_bits=actual,CPU_writer_pc=0x08b69d34))
    result=dict(schema='original-FX-node-clock-proof/v1',passed=True,capture=identity(args.capture),executed_producer=identity(executed),
        module=identity(Path(r['module']['file'])),FEP=identity(Path(r['FEP']['file'])),pairs=pairs,operations=operations,completed_observed_store_effects=len(pairs),pending_store_observations=pending,
        source_loop_range=[u16(sidecar(r['rows'][0]['before']['descriptor']),0xc),u16(sidecar(r['rows'][0]['before']['descriptor']),0xe)],
        producer=identity(Path(__file__)),full_FX_lifecycle_verified=False,seconds_to_source_units_verified=False,default_M1_binding_replaced=False,
        limits=['Store effect is observed at the following trapped write; no immediate single-step after-image is claimed. The final pending store is excluded.',
                'Loop arithmetic begins after original boundary callbacks; their property/event side effects are not implemented here.',
                'Live descriptor clock fields and FEP192 match original source. This is not a full loaded-bank byte inventory.',
                'Only this original rifle descriptor10c78 and the captured normal F32/default rounding path are validated.'])
    (args.out/'verification.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps(dict(passed=True,observed_store_effects=len(pairs),pending_excluded=pending,original_clock_operations=len(operations),range=result['source_loop_range'])))


if __name__=='__main__':main()
