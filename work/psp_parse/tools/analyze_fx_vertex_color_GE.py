"""Join audited CPU palette/vertex writes to complete, exact-content GE primitive blocks."""
import argparse
import hashlib
import json
import struct
from pathlib import Path
from PIL import Image
from analyze_fx_node_time import check,identity,read,registers,sidecar,u32,window
from analyze_weapon_cpu_ge_correlated import high24
from exact_aya_materials import iter_material_draws,decode_texture,material_parameters
from extract_runtime_character import read_ppdmp
from inventory_original_scene import draw_stream


GUN_SHA='168578abca4c4f5d22d5994ebced6b93a25d5167428bfd47f1a1150a8d42e65a'


def sha(b):return hashlib.sha256(b).hexdigest()


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--proof',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    p.add_argument('--expect-matched-rows',type=int)
    args=p.parse_args();check(not args.out.exists(),'Never replace CPU-GE color proof');args.out.mkdir(parents=True)
    proof=read(args.proof);check(proof['passed'],'Missing CPU palette/write proof')
    capture_path=Path(proof['capture']['file']);check(identity(capture_path)==proof['capture'],'CPU capture changed');r=read(capture_path)
    check(not r['geFailure']and len(r['geCaptures'])==r['geFrameCount']>0,'Incomplete actual GE recording')
    cpu=[]
    for op in proof['operations']:
        if not op['expected_enqueue']:continue
        row=r['rows'][op['row']];entry=row['viewEntry'];g,f=registers(entry['allRegisters'])
        ctx=u32(window(entry['DLGlobal'],0x08ca31d8,4));dc=window(entry['DLContext'],ctx,12);cursor=u32(dc,8)
        check(entry['stop']['pc']==0x08c01088 and g[4]==ctx and g[5]==1 and g[6]==entry['input']['address']and g[31]==0x08bfff8c,'Unexpected actual VIEW writer ABI')
        source=window(entry['input'],g[6],64);source_words=struct.unpack('<16I',source)
        packet=row['modulated']['viewPacket'];physical=cursor&~0x40000000
        check(entry['cursor']==packet['guestCursor']==cursor,'VIEW packet cursor differs')
        commands=struct.unpack('<13I',window(packet,physical,52));expected=[0x3c000000]+[0x3d000000|(source_words[k]>>8)for k in (0,1,2,4,5,6,8,9,10,12,13,14)]
        check(list(commands)==expected,'Actual VIEW packet differs from original writer input')
        a,b=entry['weaponPose'],row['modulated']['weaponPose']
        world=window(a['world'],r['selection']['actor']+0x220,64)
        check(world==window(b['world'],r['selection']['actor']+0x220,64),'Rifle WORLD changed within CPU render stages')
        slot=window(a['mainViewSlot'],0x08c3b588,4);main=window(a['mainView'],u32(slot),64)
        check(window(b['mainViewSlot'],0x08c3b588,4)==slot and window(b['mainView'],u32(slot),64)==main,'Main VIEW changed within CPU stages')
        cpu.append(dict(op=op,row=row,view=tuple(v&0xffffff for v in commands[1:]),world=high24(world),main=high24(main),matches=[],before_matches=[]))
    summaries=[];matched=[];textures={};blocks=[]
    for cap in r['geCaptures']:
        path=Path(cap['raw']['file']);check(identity(path)['sha256']==cap['raw']['sha256'],'Retained GE capture changed')
        commands,push=read_ppdmp(str(path));draws=list(draw_stream(commands,push));vertices=[];guns=[];nearest=[];gun=None
        for d in draws:
            v=d['vertex'];raw=push[v['pointer']:v['pointer']+v['bytes']];vertices.append(raw)
            if sha(struct.pack('<I',d['vtype'])+raw)==GUN_SHA:gun=d;guns.append(d)
            nearest.append(gun)
        candidates=[]
        for c in cpu:
            op=c['op']
            for phase in ('before','after'):
                arrays=[sidecar(d['vertices_'+phase]['raw'])for d in op['draws']];n=len(arrays)
                for start,d in enumerate(draws):
                    if vertices[start]!=arrays[0]or tuple(d['view'])!=c['view']:continue
                    gun=nearest[start]
                    if gun is None or gun['world']!=c['world']or gun['view']!=c['main']:continue
                    if start+n>len(draws):continue
                    if not all(vertices[start+j]==raw and draws[start+j]['vtype']==op['draws'][j]['vtype']and draws[start+j]['count']==len(op['draws'][j]['color_indices'])and draws[start+j]['primitive']==4 and tuple(draws[start+j]['view'])==c['view']for j,raw in enumerate(arrays)):continue
                    candidate=dict(CPU_row=op['row'],GE_sample=cap['sample'],phase=phase,start_draw=start,draw_count=n,capture=identity(path))
                    c['matches'if phase=='after'else'before_matches'].append(candidate)
                    if phase=='after':candidates.append((c,candidate))
        if candidates:
            states={(s['register_record'],s['register_word']):s for s in iter_material_draws(commands,push)}
            for c,block in candidates:
                blocks.append(block)
                for subdraw,source in enumerate(c['op']['draws']):
                    ordinal=block['start_draw']+subdraw;d=draws[ordinal];state=states[(d['register_record'],d['register_word'])];regs=state['registers'];tex=state['texture0']
                    check(tex is not None and not tex['framebuffer'],'Unresolved framebuffer texture in matched FX')
                    rgba,facts=decode_texture(tex['raw'],regs,state['clut'],state['clut_known']);digest=facts['rgba_sha256']
                    if digest not in textures:
                        png=args.out/('original_'+digest[:16]+'.png');Image.frombytes('RGBA',(facts['width'],facts['height']),rgba).save(png);textures[digest]=dict(facts=facts,png=identity(png))
                    prefix='CPU%02d_GE%02d_DRAW%02d'%(c['op']['row'],cap['sample'],subdraw)
                    vertex_file=args.out/(prefix+'_GE_vertices.bin');vertex_file.write_bytes(vertices[ordinal])
                    clut=args.out/(prefix+'_texture_CLUT.bin');clut.write_bytes(state['clut'])
                    check(vertex_file.read_bytes()==sidecar(source['vertices_after']['raw']),'GE vertex bytes differ from actual CPU after-image')
                    matched.append(dict(CPU_sample=c['op']['row'],subdraw=subdraw,GE_sample=cap['sample'],GE_record=d['register_record'],record=d['register_record'],word=d['register_word'],
                        runtime_geometry_id=registers(c['row']['colorBind']['allRegisters'])[0][5],source_primitive=dict(vtype=d['vtype'],primitive=d['primitive'],count=d['count'],vertices=dict(**identity(vertex_file),bytes=len(vertices[ordinal]))),
                        source_color_binding=source,CPU_palette_operation=c['op'],registers={hex(k):v for k,v in regs.items()},
                        WORLD_payload=d['world'],VIEW_payload=d['view'],PROJECTION_payload=d['proj'],texture_RGBA_sha256=digest,texture_facts=facts,
                        CLUT=identity(clut),CLUT_known_sha256=sha(state['clut_known']),material_parameters=material_parameters(regs),
                        exact_after_vertex_bytes=True,exact_full_VIEW_payload=True,exact_preceding_rifle_WORLD_and_main_VIEW_high24=True))
        summaries.append(dict(GE_sample=cap['sample'],capture=identity(path),draws=len(draws),rifle_draws=len(guns),matching_after_blocks=len(candidates)))
    rows=[]
    for c in cpu:
        check(len(c['matches'])<=1,'Ambiguous exact CPU-after/GE content join')
        check(not c['before_matches'],'Recorded GE block uses CPU-before bytes for this anchored invocation')
        rows.append(dict(CPU_row=c['op']['row'],exact_after_matches=c['matches'],exact_before_matches=c['before_matches']))
    check(matched,'No exact after-write GE consumption observations')
    matched_rows=sum(bool(c['matches'])for c in cpu)
    if args.expect_matched_rows is not None:check(matched_rows==args.expect_matched_rows,'Unexpected matched CPU-row coverage')
    result=dict(schema='original-FX-vertex-color-CPU-GE-proof/v1',passed=True,CPU_write_proof=identity(args.proof),capture=identity(capture_path),producer=identity(Path(__file__)),
                rows=rows,GE_recordings=summaries,matched_blocks=blocks,matched_primitives=matched,textures=textures,
                matched_CPU_rows=matched_rows,expected_matched_CPU_rows=args.expect_matched_rows,matched_GE_primitive_count=len(matched),matched_vertices=sum(m['source_primitive']['count']for m in matched),
                original_GE_after_vertex_bytes_verified=True,actual_GPU_pixels_verified=False,default_M1_binding_replaced=False,
                limits=['Exact block content, full VIEW and preceding original-rifle WORLD/main-VIEW anchor identify recorded observations, not a universal invocation ID.',
                        'CPU palette flush uses another stack. Its written bytes are verified in GE recording; host timing alone is not used as a frame assignment.',
                        'Unmatched CPU invocations are outside the recorded matching subset, not evidence that they never render.',
                        'GE command/input recording does not establish final GPU pixels, formal UE module loading or playable M1.'])
    (args.out/'verification.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps(dict(passed=True,matched_CPU_rows=result['matched_CPU_rows'],GE_primitives=len(matched),vertices=result['matched_vertices'],textures=len(textures))))


if __name__=='__main__':main()
