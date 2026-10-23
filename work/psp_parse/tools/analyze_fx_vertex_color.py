"""Audit original parent/mode color, cache, palette conversion and actual vertex-color writes."""
import argparse
import json
import struct
from pathlib import Path
from analyze_fx_node_time import bits,check,identity,number,read,registers,sha,sidecar,u16,u32,window
from analyze_fx_property_callbacks import code_identity,original_window
from replay_fx_render_color import Machine


def mode_reference(module,g,f,record,stack,jump):
    vm=Machine(module,g,f);vm.retain(record['address'],sidecar(record['raw']));vm.retain(stack['address'],sidecar(stack['raw']),True)
    vm.retain(jump['address'],sidecar(jump['raw']));vm.run(0x08b9a8e0,0x08b9aa84)
    return vm.bytes(stack['address'],16),vm.trace


def palette_reference(module,g,f,source,tint,destination):
    vm=Machine(module,g,f)
    for item,writable in ((source,False),(tint,False),(destination,True)):vm.retain(item['address'],sidecar(item['raw']),writable)
    vm.run(0x08b5f684,g[31]);return vm,vm.bytes(destination['address'],destination['size'])


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--capture',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    args=p.parse_args();check(not args.out.exists(),'Never replace vertex-color proof');args.out.mkdir(parents=True)
    r=read(args.capture);check(r['failure']is None and not r['cleanup']['errors']and not r['externalOrUnverifiedPause']and r['cleanup']['buttonsReleased']and r['ownedCPU']is None and r['ownedMemory']is None,'Failed/unowned color capture')
    check(not r['initialCPU']['breakpoints']and not r['initialMemory']['breakpoints'],'Existing breakpoints')
    life=read(args.capture.parent/'process_completed.json');check(life['node_exit_code']==0 and life['owned_emulator_stopped']and life['protection_passed'],'Runner not successful/terminal')
    check(identity(args.capture.parent/'executed_trace_fx_color_material_emissions.js')['sha256']==r['producer']['sha256'],'Actual observer identity changed')
    active=None
    for t in r['transitions']:
        if t['operation']=='CPU_add_requested':check(active is None,'Overlapping breakpoints');active=t['address']
        elif t['operation']=='CPU_remove':check(active==t['address'],'Wrong breakpoint removal');active=None
        else:raise ValueError('Unsupported transition')
    check(active is None,'Owned breakpoint left active')
    module=Path(r['module']['file']).read_bytes();asset=Path(r['FEP']['file']).read_bytes()
    check(sha(module)==r['module']['sha256']=='b5fc590366fc610f2cdd60104a4a28851bacd402c4600a4c296776e1dea0869f','Wrong original module')
    check(sha(asset)==r['FEP']['sha256']=='97443c71b1c1d644f323c6ff611afb740329cfe11a47a711f39dc59de06ec802','Wrong source FEP')
    for c in r['code']:code_identity(c,module)
    for a,z in ((0x08b9a514,0x08b9ad1c),(0x08b60080,0x08b602e4),(0x08b60758,0x08b60890),(0x08b5f684,0x08b5f854)):
        check(any(c['address']<=a and c['address']+c['size']>=z for c in r['code']),'Full original function identity missing')
    s=r['selection'];base=s['FEPbase'];sg,_=registers(s['allRegisters']);n=sidecar(s['node']);st=sidecar(s['state']);ct=sidecar(s['context'])
    check(s['stop']['pc']==0x08b69d64 and sg[10]==0x08b9a514 and sg[5]==s['C']and sg[17]==s['N']and u32(ct,0x8c)==s['P']and u32(ct,0x90)==s['N'],'Wrong handler selection')
    check(u32(n,0x40)==s['descriptor']==base+0x10c78 and u32(st,0x190)==base and u32(st,0x198)==base+0x48f0 and sidecar(s['resource'])==asset[0x48f0:0x49b0],'Wrong source resource')
    i=s['identityRaw'];primary=window(i['primaryHandle'],s['handle'],4);af=window(i['actorFields'],s['actor']+0x3c4,40);mh=window(i['metadataHeader'],s['metadata'],64);dh=window(i['drawHeader'],s['drawTable'],16)
    check(u32(st,0x144)==s['handle']and u32(primary)==s['actor']and u32(af)==s['sourceBase']and u32(af,0x24)==s['metadata']and u32(mh,0x34)==s['drawTable']and u16(mh,6)==3,'Rifle chain differs')
    check(u16(dh,4)==243 and u32(dh,12)==0x522 and sha(struct.pack('<I',0x522)+sidecar(s['geometry']))=='168578abca4c4f5d22d5994ebced6b93a25d5167428bfd47f1a1150a8d42e65a','Rifle geometry differs')
    ops=[];palettes=draw_count=vertex_count=0
    for row in r['rows']:
        check(row['complete'],'Incomplete color invocation');names=['dispatch','modulated','transformed','colorBind','binderReturn']
        pcs=[0x08b69d64,0x08b9a8e0,0x08b9aa84,0x08b60080]
        check([row[k]['stop']['pc']for k in names[:4]]==pcs,'Wrong color invocation stages')
        ticks=[row[k]['stop']['ticks']for k in names];check(all(a<b for a,b in zip(ticks,ticks[1:])),'Nonexecuted color stages')
        dg,df=registers(row['dispatch']['allRegisters']);mg,mf=registers(row['modulated']['allRegisters']);bg,bf=registers(row['colorBind']['allRegisters'])
        check(dg[10]==0x08b9a514 and dg[5]==mg[17]==s['C']and dg[17]==s['N']and bg[4]==mg[22]and bg[5]==mg[21],'Different render/context/bank binding')
        before=row['modulated']['before'];nb=sidecar(before['node']);pb=sidecar(before['state']);db=sidecar(before['descriptor'])
        check(u32(nb,0x40)==s['descriptor']and u32(pb,0x190)==base and u32(pb,0x198)==base+0x48f0 and u32(pb,0x144)==s['handle']and u32(sidecar(before['primaryHandle']))==s['actor'],'Original source node identity changed')
        slot=window(before['definitionSlot'],u32(db,0x1c)+20,4);definition=window(before['definition'],u32(slot),4);original_window(before['definition'],asset,base)
        check(u16(definition)==16,'Wrong color definition')
        params=window(before['colorParameters'],u32(nb,0x44)+u16(definition,2),0x30)
        rd=sidecar(before['rendererDefinition']['raw']);refs=sidecar(before['rendererReferences']['raw'])
        check(u16(rd)==155 and before['colorParameters']['address']==s['N']+0x60+u16(refs,u32(rd,4)*2),'Renderer does not reference the original type16 color block')
        original_window(before['rendererDefinition'],asset,base);original_window(before['rendererReferences'],asset,base)
        source=list(struct.unpack_from('<4I',params));parent=list(struct.unpack_from('<4I',pb,0x40))
        combined=b''.join(struct.pack('<I',bits(number(a)*number(b)))for a,b in zip(source,parent))
        check(window(row['modulated']['color'],mg[29],16)==combined,'Observed parent/color modulation differs')
        # The JALR delay slot moves t0 to a2; pre-call a2 is still vtable setup.
        delay=u32(module,0x08b69d68-0x08804000)
        check(delay>>26==0 and(delay>>21)&31==8 and(delay>>16)&31==0 and(delay>>11)&31==6 and delay&63 in(0x21,0x25),'Unknown renderer argument delay slot')
        record=row['modulated']['record'];check(record['address']==mg[20]==dg[8],'Original renderer record binding differs');original_window(record,asset,base)
        jump=row['modulated']['jumpTable'];check(window(jump,0x08c2d8f0,28)==module[0x08c2d8f0-0x08804000:0x08c2d90c-0x08804000],'Color jump table differs')
        processed,trace=mode_reference(module,mg,mf,record,row['modulated']['color'],jump)
        check(sidecar(row['transformed']['color']['raw'])==processed==window(row['colorBind']['inputColor'],bg[6],16),'Original color-mode result/binder input differs')
        bind=row['colorBind'];bank=window(bind['bank'],bg[4],0x34);slot=window(bind['slot'],u32(bank)+bg[5]*4,4);obj=window(bind['object'],u32(slot),0x20);header=window(bind['header'],u32(obj),0x24)
        group=window(bind['group'],u32(header,0x1c),0x44);count=u32(group,0x10)
        check(u32(header,0x18)==1 and u32(group,0x1c)==1 and count==bind['colorMode']>=2,'Unsupported actual group/palette count')
        pending,capacity=u32(bank,0x28),u32(bank,0x30);check(pending<=capacity<=8192,'Invalid cache capacity')
        enqueue=pending<capacity and obj[0x10:0x20]!=processed;check(enqueue==row['enqueued'],'Raw-byte cache decision differs')
        after_bank=window(row['binderReturn']['bank'],bg[4],0x34);after_obj=window(row['binderReturn']['object'],u32(slot),0x20)
        expected_bank=bytearray(bank);struct.pack_into('<I',expected_bank,0x28,pending+int(enqueue))
        check(after_bank==expected_bank and after_obj[:0x10]==obj[:0x10]and after_obj[0x10:0x20]==(processed if enqueue else obj[0x10:0x20]),'Actual cache count/object last-color differs')
        check(row['binderReturn']['stop']['pc']==bg[31]and bg[31]in (0x08b603a0,0x08b60538),'Wrong binder return')
        raw_palette=window(bind['sourceColors'],u32(group,0x14),count*4);old_palette=window(bind['convertedBefore'],u32(group,0x18),count*4)
        op=dict(row=row['index'],source_bits=source,parent_bits=parent,mode=sidecar(record['raw'])[0x4b],previous_cached_bits=list(struct.unpack('<4I',obj[0x10:0x20])),
                pending=pending,capacity=capacity,source_palette=bind['sourceColors'],previous_palette=bind['convertedBefore'],
                expected_combined_bits=list(struct.unpack('<4I',combined)),expected_processed_bits=list(struct.unpack('<4I',processed)),expected_enqueue=enqueue,draws=[],original_mode_trace=trace)
        if enqueue:
            stages=[row[k]['stop']['ticks']for k in ('binderReturn','flushEntry','paletteEntry','paletteReturn','vertexPatchEntry','vertexPatchReturn','flushReturn')]
            check(all(a<b for a,b in zip(stages,stages[1:])),'Cached color/patch stages did not execute in order')
            cache=u32(bank,0x24)+pending*32;entry=window(row['binderReturn']['enqueuedEntry'],cache,32)
            check(entry[:16]==processed and u32(entry,16)==u32(slot)and entry[20:]==sidecar(bind['nextCacheEntry']['raw'])[20:],'Enqueued tint/object record differs')
            fl=row['flushEntry'];fg,ff=registers(fl['allRegisters']);fb=window(fl['bank'],bg[4],0x34)
            check(fg[4]==bg[4]and u32(fb,0x2c)==pending and window(fl['cacheEntry'],cache,32)==entry,'Wrong actual queued-object flush')
            pe=row['paletteEntry'];pg,pf=registers(pe['allRegisters'])
            check(pe['stop']['pc']==0x08b5f684 and pg[4]==u32(group,0x18)and pg[5]==count and pg[6]==u32(group,0x14)and pg[7]==cache and pg[31]==0x08b60808,'Wrong converter ABI')
            check(window(pe['source'],pg[6],count*4)==raw_palette and window(pe['tint'],cache,16)==processed,'Converter operands differ from queue/source')
            vm,converted=palette_reference(module,pg,pf,pe['source'],pe['tint'],pe['outputBefore']);rg,rf=registers(row['paletteReturn']['allRegisters'])
            check(vm.g==rg and vm.f==rf,'Original converter register replay differs')
            check(window(row['paletteReturn']['output'],pg[4],count*4)==converted,'Original palette conversion differs from actual memory')
            op['expected_palette']=row['paletteReturn']['output'];op['original_palette_trace']=vm.trace;palettes+=1
            patch=row['vertexPatchEntry'];patch_g,_=registers(patch['allRegisters']);h=window(patch['header'],u32(group,0x20),16);vt=u32(h);inner=u32(h,8)
            check(patch_g[4]==u32(slot)and patch_g[5]==patch['header']['address']and patch_g[31]==0x08b6082c and vt in (0x11e,0x11c),'Wrong vertex-color patch ABI/layout')
            records=window(patch['records'],u32(h,12),inner*16);check(len(patch['draws'])==len(row['vertexPatchReturn']['draws'])==inner,'Missing patch subdraw')
            stride,offset=(16,4)if vt==0x11e else(12,0)
            for j,(d,returned)in enumerate(zip(patch['draws'],row['vertexPatchReturn']['draws'])):
                n=u32(records,j*16+8);refs=window(d['references'],u32(records,j*16+4),n*4);vertices=u32(records,j*16+12)
                original=window(d['vertices'],vertices,n*stride);expected=bytearray(original);indices=[]
                for k in range(n):
                    ptr=u32(refs,k*4);delta=ptr-pg[4];check(0<=delta<count*4 and delta%4==0,'Color reference outside converted palette')
                    indices.append(delta//4);expected[k*stride+offset:k*stride+offset+4]=converted[delta:delta+4]
                check(window(returned,vertices,n*stride)==expected,'Actual vertex-color patch changed wrong bytes')
                op['draws'].append(dict(vtype=vt,color_indices=indices,vertices_before=d['vertices'],vertices_after=returned));draw_count+=1;vertex_count+=n
            check(u32(window(row['flushReturn']['bank'],bg[4],0x34),0x2c)==pending+1 and row['flushReturn']['stop']['pc']==fg[31],'Cache consumed-count/return differs')
        else:op['expected_palette']=bind['convertedBefore']
        ops.append(op)
    check(len(ops)==6 and palettes>0,'Insufficient complete actual chain')
    report=dict(schema='original-FX-vertex-color-pipeline-proof/v1',passed=True,capture=identity(args.capture),producer=identity(Path(__file__)),oracle=identity(Path(__file__).with_name('replay_fx_render_color.py')),
                module=identity(Path(r['module']['file'])),operations=ops,render_calls=len(ops),actual_palette_conversions=palettes,patched_draws=draw_count,patched_vertices=vertex_count,
                texture_CLUT_modified=False,new_GE_consumption_capture_verified=False,default_M1_binding_replaced=False,all_VFPU_prefix_controls_directly_observed=False,
                limits=['This branch uses a vertex-color palette and CPU vertex writes; no mode7 GE material writes occur here.',
                        'No new GPU/GE consumption or final-pixel comparison is claimed. Parent modulation matches observed F32 products; VFPU control registers are not exported.',
                        'One source group/draw-header per selected object is observed; general cache scheduling and other palette branches remain unported.'])
    (args.out/'verification.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps(dict(passed=True,render_calls=len(ops),actual_palette_conversions=palettes,patched_draws=draw_count,patched_vertices=vertex_count)))


if __name__=='__main__':main()
