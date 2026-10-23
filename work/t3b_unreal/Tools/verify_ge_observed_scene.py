"""Audit real GPU SO/texture/colour/depth/stencil outputs and source camera data."""
import argparse,hashlib,json,struct,sys
from pathlib import Path
import numpy as np
from PIL import Image,ImageDraw


def check(v,msg):
    if not v:raise ValueError(msg)
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def read(p):return json.loads(p.read_text(encoding='utf-8'))
def identity(row):
    p=Path(row['file']);check(sha(p)==row['sha256'],'Changed evidence: '+str(p));return p
def f24(v):return (np.array(v,dtype='<u4')<<8).view('<f4').astype(float)


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--run',required=True,type=Path);a=p.parse_args()
    out=a.run;dest=out/'independent_verification.json';check(not dest.exists(),'Never replace accepted audit')
    req=read(out/'request.json');actual=read(out/'actual_gpu_report.json');started=read(out/'started.json');done=read(out/'completed.json')
    check(req['build_exit_code']==done['exit_code']==0 and actual['pid']==started['pid']==done['pid'],'Process/build identity failed')
    for row in req['sources']:identity(row)
    check(sha(Path(req['command'][0]))==req['executable_sha256'],'Executed EXE changed')
    data=read(identity(req['inputs']));raw=identity(req['binary']).read_bytes();check(raw[:8]==b'T3BGEF1\0','Observed format mismatch')
    width,height,frames,atlases=struct.unpack_from('<4I',raw,8);check((width,height,frames)==(480,272,12)and atlases==len(data['atlases']),'Header scope mismatch')
    at=24
    for t in data['atlases']:
        w,h=struct.unpack_from('<2I',raw,at);at+=8;rgba=raw[at:at+w*h*4];at+=w*h*4
        check((w,h)==(t['width'],t['height'])and hashlib.sha256(rgba).hexdigest()==t['rgba_sha256'],'Bundle texture differs')
        check((out/f'atlas_{t["index"]}_actual.rgba').read_bytes()==rgba,'Actual GPU texture upload/readback differs')
    project=Path(__file__).resolve().parents[1];parse=project.parent/'psp_parse';sys.path.insert(0,str(parse/'tools'))
    from extract_runtime_character import read_ppdmp,layout
    from inventory_original_scene import draw_stream
    from export_aya_actual_weapon import matrix_draws
    from exact_aya_materials import iter_material_draws,decode_texture
    actor_req=read(identity(data['actor_provenance']));manifests=[read(identity(actor_req[k]))for k in ('body_input','weapon_input')]
    source_dtype=np.dtype([('position','<f4',3),('normal','<f4',3),('color','u1',4),('secondary','u1',3),('pad','u1')])
    source_positions=[];source_uv=[]
    proofs=list(actor_req['runtime_proofs']);other=None
    if data.get('other_actor_proof'):
        other_proof=identity(data['other_actor_proof']);proof=read(other_proof);other=read(identity(proof['input_manifest']))
        check(other['captures']==manifests[1]['captures']and other['same_GE_dump_pairing'],'Additional actor capture pairing differs')
        proofs.append(data['other_actor_proof']);other_raw=identity(other['binary']).read_bytes()
    for row in proofs:
        proof=read(identity(row));check(proof['passed'],'Actor proof failed');source_positions.append(np.fromfile(identity(proof['runtime_output']),dtype=source_dtype))
        source_uv.append(np.fromfile(identity(proof['runtime_uv']),dtype='<f4').reshape(-1,2))
        comparison=read(Path(proof['comparison']['file']));official=Path(proof['comparison']['file']).parent/'official_outputs.bin'
        check(sha(official)==comparison['official_output_sha256']and official.read_bytes()==Path(proof['runtime_output']['file']).read_bytes(),'Actor world output reference differs')
    bm,wm=manifests;origin=np.array(data['fixed_shared_PSP_world_origin']);units=data['metres_per_PSP_world_unit']
    unit=units*100;inverse=np.array([[1/unit,0,0,0],[0,0,1/unit,0],[0,1/unit,0,0],[*origin,1]])
    source_rows=[];gpu_vertices=0
    for sample,frame in enumerate(data['frames']):
        sid,count=struct.unpack_from('<2I',raw,at);at+=8;check(sid==sample and count==len(frame['draws']),'Frame pairing/count differs')
        pp=Path(frame['capture']['path']);check(sha(pp)==frame['capture']['sha256'],'Original GE dump changed')
        commands,push=read_ppdmp(str(pp));draws={(d['register_record'],d['register_word']):d for d in draw_stream(commands,push)}
        states={(d['register_record'],d['register_word']):d for d in iter_material_draws(commands,push)}
        matrix_states={(d['register_record'],d['register_word']):d for d in matrix_draws(commands,push)}if other else{}
        wf=wm['frames'][sample];bf=bm['frames'][wf['body_frame_index']]
        actors={(d['register_record'],d['register_word']):(0,d)for d in bm['draws'][bf['first_draw']:bf['first_draw']+106]}
        weapon=wm['draws'][wf['first_draw']];actors[(weapon['register_record'],weapon['register_word'])]=(1,weapon)
        if other:
            of=other['frames'][sample]
            for desc in other['draws'][of['first_draw']:of['first_draw']+of['draw_count']]:actors[(desc['register_record'],desc['register_word'])]=(2,desc)
        expected_keys={k for k,d in draws.items()if d['vtype']==0x11f}|set(actors)
        check(expected_keys=={(d['register_record'],d['register_word'])for d in frame['draws']},'Source world draws omitted or invented')
        so=np.fromfile(out/f'sample_{sample}.clip_uv_color_fog_f32',dtype='<f4').reshape(-1,11);so_at=0;screen_error=0.;fog_error=0.;backgrounds=0
        for ordinal,row in enumerate(frame['draws']):
            texture,index,flags,n,reference=struct.unpack_from('<5I',raw,at);at+=20
            check((texture,index,flags,n)==(row['texture'],ordinal,row['flags'],row['vertices']),'Draw header differs')
            matrix=np.frombuffer(raw,dtype='<f4',count=16,offset=at).reshape(4,4);at+=64
            fog=np.frombuffer(raw,dtype='<f4',count=4,offset=at);at+=16;fogRGB=struct.unpack_from('<4I',raw,at);at+=16
            vertices=np.frombuffer(raw,dtype='<f4',count=n*9,offset=at).reshape(n,9);at+=n*36
            check(hashlib.sha256(vertices.tobytes()).hexdigest()==row['vertex_input_sha256'],'Vertex input changed')
            key=row['register_record'],row['register_word'];d=draws[key];state=states[key];regs=state['registers']
            check(d['world']==row['WORLD_payload']and d['view']==row['VIEW_payload']and d['proj']==row['PROJECTION_payload'],'Raw camera/WORLD differs')
            check({hex(k):v for k,v in regs.items()}==row['registers'],'Raw PRIM registers differ')
            flags_from_raw=(regs[0x21]&1)|((1-(regs[0xe7]&1))<<1)|((regs[0x1d]&1)<<2)|(((regs[0xc9]>>16)&1)<<3)|((regs[0x1f]&1)<<4)|((regs[0x24]&1)<<5)|((regs[0x1c]&1)<<6)
            flags_from_raw|=int(d['view']!=weapon['VIEW_payload']or d['proj']!=weapon['PROJECTION_payload'])<<7
            check(flags==flags_from_raw,'Draw state flags disagree with raw GE registers')
            v=d['vertex'];source_raw=push[v['pointer']:v['pointer']+v['bytes']]
            check(hashlib.sha256(struct.pack('<I',d['vtype'])+source_raw).hexdigest()==row['vertex_sha256'],'Source vertex identity differs')
            if key in actors:
                actor,desc=actors[key];first=desc['first_output_vertex'];source=source_positions[actor][first:first+n]
                world=source['position'].astype(float);color=source['color'].astype(float)/255;uv=source_uv[actor][first:first+n]
                if actor==2:
                    original=matrix_states[key];offset_lit=desc['binary_byte_offset'];slots=((d['vtype']>>14)&7)+1
                    check(desc['BONE_payload']==original['bones'],'Other actor effective BONE uploads differ')
                    header=struct.pack('<256I',*[regs.get(k,0)for k in range(256)])+f24(d['world']).astype('<f4').tobytes()
                    header+=f24([v if v is not None else 0 for v in original['bones']]).astype('<f4').tobytes()+struct.pack('<2I',n,slots)
                    check(other_raw[offset_lit:offset_lit+1464]==header,'Evaluated actor transform/light header differs from original PRIM state')
                    stride,fields=layout(d['vtype']);decoded=[]
                    for i in range(n):
                        base=i*stride
                        values=[x/32768 for x in struct.unpack_from('<3h',source_raw,base+fields['pos'][0])]
                        values+=[x/128 for x in struct.unpack_from('<3b',source_raw,base+fields['nrm'][0])]
                        values+=[x/32768 for x in struct.unpack_from('<'+'H'*slots,source_raw,base+fields['wt'][0])]+[0]*(8-slots)
                        values+=[x/32768 for x in struct.unpack_from('<2H',source_raw,base+fields['uv'][0])];decoded.append(values)
                    check(other_raw[offset_lit+1464:offset_lit+1464+n*64]==np.asarray(decoded,dtype='<f4').tobytes(),'Evaluated actor vertices differ from original raw weights/normals/positions/UV')
            else:
                stride,off=layout(d['vtype']);local=np.array([struct.unpack_from('<3h',source_raw,i*stride+off['pos'][0])for i in range(n)],dtype=float)/32768
                world=np.column_stack([local,np.ones(n)])@f24(d['world']).reshape(3,4,order='F').T
                color=np.array([struct.unpack_from('<4B',source_raw,i*stride+8)for i in range(n)],dtype=float)/255
                uv=np.array([struct.unpack_from('<2f',source_raw,i*stride)for i in range(n)],dtype='<f4')
            expected=np.column_stack([((world-origin)*units*100)[:,[0,2,1]],uv,color]).astype('<f4')
            check(expected.tobytes()==vertices.tobytes(),'Actual world/UV/color inputs differ from original data')
            rgba,facts=decode_texture(state['texture0']['raw'],regs,state['clut'],state['clut_known'])
            check(facts['rgba_sha256']==data['atlases'][texture]['rgba_sha256']==row['texture_RGBA_sha256'],'Per-draw effective CLUT binding differs')
            check(reference==(regs[0xdc]>>8)&255,'Stencil reference differs')
            view=np.eye(4);view[:,:3]=f24(d['view']).reshape(4,3);proj=f24(d['proj']).reshape(4,4)
            vp=f24([regs[k]for k in(0x42,0x43,0x44)]);center=f24([regs[k]for k in(0x45,0x46,0x47)]);offset=np.array([regs[k]&65535 for k in(0x4c,0x4d)])/16
            remap=np.diag([vp[0]/240,-vp[1]/136,vp[2]/65535,1.]);remap[3,:3]=[(center[0]-offset[0])/240-1,1-(center[1]-offset[1])/136,center[2]/65535]
            check((inverse@view@proj@remap).astype('<f4').tobytes()==matrix.tobytes(),'Per-draw source projection differs')
            expected_fog=inverse@view[:,2];expected_fog[3]+=f24([regs[0xcd]])[0];expected_fog*=f24([regs[0xce]])[0]
            check(expected_fog.astype('<f4').tobytes()==fog.tobytes(),'Per-draw fog plane differs')
            check(fogRGB[:3]==tuple((regs[0xcf]>>(8*k))&255 for k in range(3)),'Source fog colour differs')
            output=so[so_at:so_at+n];so_at+=n;h=np.column_stack([vertices[:,:3].astype(float),np.ones(n)])
            bound=8*np.finfo(np.float32).eps*(np.abs(h)@np.abs(matrix.astype(float)))
            check(np.all(np.abs(output[:,:4]-h@matrix.astype(float))<=bound),'Actual GPU clip exceeds float32 arithmetic bound')
            check(output[:,4:10].tobytes()==vertices[:,3:].tobytes(),'Actual GPU VS UV/color changed')
            fog_bound=8*np.finfo(np.float32).eps*(np.abs(h)@np.abs(fog.astype(float)))
            check(np.all(np.abs(output[:,10]-h@fog.astype(float))<=fog_bound),'Actual GPU fog exceeds dot-product bound')
            clip=np.column_stack([world,np.ones(n)])@view@proj@remap;valid=(clip[:,3]>1)&np.all(np.abs(clip[:,:2])<=clip[:,3,None],axis=1)
            if valid.any():
                cpu=clip[valid,:2]/clip[valid,3,None];gpu=output[valid,:2].astype(float)/output[valid,3,None]
                screen_error=max(screen_error,float(np.max(np.abs((cpu-gpu)*[240,136]))))
            raw_fog=(np.column_stack([world,np.ones(n)])@view[:,2]+f24([regs[0xcd]])[0])*f24([regs[0xce]])[0]
            fog_error=max(fog_error,float(np.max(np.abs(raw_fog-output[:,10]))));backgrounds+=int(bool(flags&128));gpu_vertices+=n
        check(so_at==len(so),'Incomplete actual GPU vertex output')
        check(screen_error<.01,'Visible source projection differs by >=0.01 PSP pixel')
        source_rows.append(dict(sample=sample,draws=count,vertices=so_at,independent_camera_draws=backgrounds,
                                max_visible_projection_error_PSP_pixels=screen_error,max_source_fog_vertex_error=fog_error))
    check(at==len(raw),'Trailing observed scene data')
    images={};files=[]
    for capture in actual['captures']:
        stem=capture['stem'];paths=[out/(stem+s)for s in('.rgba','.owner_u32','.depth_stencil_u32')]
        rgb=np.fromfile(paths[0],dtype='u1').reshape(272,480,4);owner=np.fromfile(paths[1],dtype='<u4').reshape(272,480)
        packed=np.fromfile(paths[2],dtype='<u4').reshape(272,480);z=(packed&0xffffff).astype(float)/0xffffff;stencil=packed>>24
        check(np.all(rgb[:,:,3]==255),'Colour write mask/clear alpha differs')
        check(not np.any(stencil)if not capture['synthetic']else True,'Unexpected source stencil values')
        if capture['mode']=='no_depth_writes':check(not np.any(z),'No-write control changed depth')
        check(np.any(owner),'Empty actual GPU capture')
        png=out/(stem+'.png')
        if png.exists():
            with Image.open(png)as existing:check(np.array_equal(np.asarray(existing.convert('RGBA')),rgb),'Existing PNG differs from actual GPU readback')
        else:Image.fromarray(rgb).save(png)
        images[stem]=(rgb,owner,packed,z,stencil);files.append(dict(stem=stem,rgba_sha256=sha(paths[0]),owner_sha256=sha(paths[1]),depth_stencil_sha256=sha(paths[2]),png_sha256=sha(png)))
    check(len(images)==64,'Expected60 original plus4 synthetic captures')
    controls=[]
    for i,expected in enumerate(([68,112,142],[98,88,166],[128,64,191])):
        rgb,owner,_,z,stencil=images[f'fog_control_{i}'];mask=owner>0
        check(np.all(rgb[mask,:3]==expected)and np.all(owner[mask]==1)and np.max(np.abs(z[mask]-.5))<1e-7 and not np.any(stencil),'Analytic fog control failed')
        controls.append(dict(case=i,RGB=expected,checked_pixels=int(mask.sum())))
    rgb,owner,_,z,stencil=images['stencil_depth_fail_control'];mask=owner>0
    check(np.all(owner[mask]==1)and np.all(stencil[mask]==73)and np.max(np.abs(z[mask]-.8))<1e-7,'Actual stencil depth-fail replacement failed')
    effects=[]
    for sample in range(12):
        prefix=f'sample_{sample}_';base=images[prefix+'source_states'];off=images[prefix+'no_background'];fog=images[prefix+'no_fog'];depth=images[prefix+'no_depth_writes']
        check(np.array_equal(base[2],off[2]),'Background/no-depth draws affected source main depth/stencil')
        check(np.array_equal(base[1],fog[1])and np.array_equal(base[2],fog[2]),'Fog changed raster ownership/depth')
        check(np.array_equal(base[1]>0,depth[1]>0),'Depth intervention changed union coverage')
        background=images[prefix+'background_only']
        background_ids=[j+1 for j,row in enumerate(data['frames'][sample]['draws'])if row['flags']&128]
        uncovered_background=(background[1]>0)&(off[1]==0)
        final_background=np.isin(base[1],background_ids)
        check(np.any(background[1]),'Independent-camera draws have no isolated raster coverage')
        check(np.array_equal(final_background,uncovered_background),'Final background ownership differs from unoccluded source coverage')
        changed=np.any(base[0][:,:,:3]!=off[0][:,:,:3],axis=2)
        if not np.any(uncovered_background):check(not np.any(changed),'Fully overwritten background still changed RGB')
        effects.append(dict(sample=sample,isolated_background_pixels=int((background[1]>0).sum()),
            final_background_owner_pixels=int(final_background.sum()),background_fully_overwritten=not bool(np.any(uncovered_background)),background_changed_RGB_pixels=int(np.any(base[0][:,:,:3]!=off[0][:,:,:3],axis=2).sum()),
            fog_changed_RGB_pixels=int(np.any(base[0][:,:,:3]!=fog[0][:,:,:3],axis=2).sum()),
            depth_changed_RGB_pixels=int(np.any(base[0][:,:,:3]!=depth[0][:,:,:3],axis=2).sum())))
    check(any(e['background_changed_RGB_pixels']>0 for e in effects)and all(e['fog_changed_RGB_pixels']>0 for e in effects),'Background never visible or source fog had no effect')
    sheet=Image.new('RGB',(1440,1200),(22,22,22));draw=ImageDraw.Draw(sheet)
    for i in range(12):
        x=i%3*480;y=i//3*300;sheet.paste(Image.fromarray(images[f'sample_{i}_source_states'][0]).convert('RGB'),(x,y+28));draw.text((x+8,y+6),f'Sample{i}: original per-draw cameras/fog/depth',fill='white')
    sheet.save(out/'CONTACT_SHEET.png')
    report=dict(schema='t3b-observed-per-draw-GPU-audit/v1',passed=True,pid=actual['pid'],adapter=actual['adapter'],
        source_draws=sum(r['draws']for r in source_rows),actual_GPU_vertex_records=gpu_vertices,actual_GPU_atlas_uploads_exact=atlases,
        captures=64,frames=source_rows,controls=controls,stencil_depth_fail_replacement_verified=True,effects=effects,files=files,
        additional_original_actor_included=other is not None,UE_executed=False,original_PSP_pixel_equivalence=False,original_D16_depth_equivalence=False,
        complete_level_recovered=False,original_timing_verified=False,
        limits=['D3D11 RGB interpolation/texture sampling/blending and D24S8 differ from complete PSP fixed-point/16-bit rasterization.',
                'Stencil controls verify source-state operations; PSP framebuffer alpha/stencil coupling is not reproduced.',
                'Observed VTYPE11f draws and verified actor subset (optional known28-draw creature); unweighted FX/HUD and the full game are not recovered.'])
    dest.write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps({k:report[k]for k in('passed','source_draws','actual_GPU_vertex_records','actual_GPU_atlas_uploads_exact','captures')}))


if __name__=='__main__':main()
