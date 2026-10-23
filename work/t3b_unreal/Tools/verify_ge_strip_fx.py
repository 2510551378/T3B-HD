"""Independent raw GE strip/UV/state audit plus actual GPU interventions."""
import argparse,hashlib,json,struct,sys
from pathlib import Path
import numpy as np
from PIL import Image,ImageDraw


def check(v,msg):
    if not v:raise ValueError(msg)
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def read(p):return json.loads(p.read_text(encoding='utf-8'))
def file(r):
    p=Path(r['file']);check(sha(p)==r['sha256'],'Changed evidence: '+str(p));return p
def f24(v):return (np.asarray(v,dtype='<u4')<<8).view('<f4').astype(float)


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--run',required=True,type=Path);a=p.parse_args()
    out=a.run;dest=out/'independent_verification.json';check(not dest.exists(),'Never replace a completed audit')
    req=read(out/'request.json');actual=read(out/'actual_gpu_report.json');start=read(out/'started.json');done=read(out/'completed.json')
    check(req['build_exit_code']==done['exit_code']==0 and actual['pid']==start['pid']==done['pid'],'Actual process/build identity differs')
    for s in req['sources']:file(s)
    check(sha(Path(req['command'][0]))==req['executable_sha256'],'Executed EXE changed')
    source=read(file(req['inputs']));raw=file(req['binary']).read_bytes();check(raw[:8]==b'T3BGEF2\0','Wrong FX geometry format')
    check(struct.unpack_from('<4I',raw,8)==(480,272,12,len(source['atlases'])),'Input scope differs')
    project=Path(__file__).resolve().parents[1];sys.path.insert(0,str(project.parent/'psp_parse/tools'))
    from extract_runtime_character import read_ppdmp,layout
    from inventory_original_scene import draw_stream
    from exact_aya_materials import iter_material_draws,decode_texture,unpack_color
    base_path=file(source['base_inputs']);base=read(base_path);baseline=project/'Validation/observed_ge_scene_runs/f99ea978f2644fe3aa63b5af15c39251'
    baseline_audit=read(baseline/'independent_verification.json');check(baseline_audit['passed'],'Base native source audit missing')
    check(file(read(baseline/'request.json')['inputs'])==base_path,'FX was not added to the accepted base scene')
    at=24
    for i,t in enumerate(source['atlases']):
        w,h=struct.unpack_from('<2I',raw,at);at+=8;rgba=raw[at:at+w*h*4];at+=w*h*4
        check((w,h)==(t['width'],t['height'])and hashlib.sha256(rgba).hexdigest()==t['rgba_sha256'],'Input atlas differs')
        check((out/f'atlas_{i}_actual.rgba').read_bytes()==rgba,'Actual GPU texture upload/readback differs')
    origin=np.array(source['fixed_shared_PSP_world_origin']);units=source['metres_per_PSP_world_unit'];unit=units*100
    inverse=np.array([[1/unit,0,0,0],[0,0,1/unit,0],[0,1/unit,0,0],[*origin,1.]])
    frames=[];total_fx=total_fx_vertices=0;cache={};final_fx_ids=[];controls=[];images={};records=[]
    canonical_fields=('register_record','register_word','WORLD_payload','VIEW_payload','PROJECTION_payload','flags','vertices','vertex_sha256','vertex_input_sha256','texture_RGBA_sha256','registers')
    for sample,(frame,old)in enumerate(zip(source['frames'],base['frames'])):
        sid,count=struct.unpack_from('<2I',raw,at);at+=8;check(sid==sample and count==len(frame['draws']),'Wrong sample pairing')
        capture=Path(frame['capture']['path']);check(sha(capture)==frame['capture']['sha256'],'Original GE capture changed')
        cmd,push=read_ppdmp(str(capture));draws={(d['register_record'],d['register_word']):d for d in draw_stream(cmd,push)}
        states={(d['register_record'],d['register_word']):d for d in iter_material_draws(cmd,push)}
        body=next(d for d in old['draws']if d['category']=='body');expected=set()
        for key,d in draws.items():
            r=states[key]['registers'];vt=d['vtype']
            if not(vt&(1<<23))and not((vt>>9)&3)and not((vt>>11)&3)and not((vt>>18)&7)and d['primitive']==4 and r[0x23]&1 and r[0x9c]==body['registers']['0x9c']and d['proj'][-1]==0:expected.add(key)
        observed={(d['register_record'],d['register_word'])for d in frame['draws']if d['category']=='unweighted_strip_fx'}
        check(expected==observed,'Eligible original perspective strips omitted or invented')
        retained=[d for d in frame['draws']if d['category']!='unweighted_strip_fx']
        check([{k:d[k]for k in canonical_fields}for d in retained]==[{k:d[k]for k in canonical_fields}for d in old['draws']],'Base data/state/camera/texture/order changed')
        so=np.fromfile(out/f'sample_{sample}.clip_uv_color_fog_f32',dtype='<f4').reshape(-1,11)
        old_so=np.fromfile(baseline/f'sample_{sample}.clip_uv_color_fog_f32',dtype='<f4').reshape(-1,11)
        so_at=old_so_at=0;fx_ids=[];frame_fx=0;screen_error=0.;total_vertices=0
        for ordinal,row in enumerate(frame['draws']):
            texture,index,flags,n,ref=struct.unpack_from('<5I',raw,at);at+=20
            matrix=np.frombuffer(raw,dtype='<f4',count=16,offset=at).reshape(4,4);at+=64
            fog=np.frombuffer(raw,dtype='<f4',count=4,offset=at);at+=16;fog_rgb=struct.unpack_from('<4I',raw,at);at+=16
            vertices=np.frombuffer(raw,dtype='<f4',count=n*9,offset=at).reshape(n,9);at+=n*36
            check((texture,index,flags,n)==(row['texture'],ordinal,row['flags'],row['vertices'])and hashlib.sha256(vertices.tobytes()).hexdigest()==row['vertex_input_sha256'],'Submitted geometry header/input differs')
            output=so[so_at:so_at+n];so_at+=n;total_vertices+=n
            if row['category']!='unweighted_strip_fx':
                check(output.tobytes()==old_so[old_so_at:old_so_at+n].tobytes(),'Retained actual GPU VS outputs changed');old_so_at+=n;continue
            key=row['register_record'],row['register_word'];d=draws[key];st=states[key];r=st['registers'];vt=d['vtype'];count_source=d['count']
            check(row['registers']=={hex(k):v for k,v in r.items()}and row['WORLD_payload']==d['world']and row['VIEW_payload']==d['view']and row['PROJECTION_payload']==d['proj'],'Original FX state/matrices differ')
            v=d['vertex'];original=push[v['pointer']:v['pointer']+v['bytes']]
            check(hashlib.sha256(struct.pack('<I',vt)+original).hexdigest()==row['vertex_sha256'],'Raw FX geometry changed')
            stride,fields=layout(vt);check(len(original)==stride*count_source,'Original vertex extent differs')
            po=(vt>>7)&3;code,den={1:('b',128),2:('h',32768),3:('f',1)}[po]
            local=np.array([struct.unpack_from('<3'+code,original,i*stride+fields['pos'][0])for i in range(count_source)],dtype=float)/den
            code,den={1:('B',128),2:('H',32768),3:('f',1)}[vt&3]
            uv=np.array([struct.unpack_from('<2'+code,original,i*stride+fields['uv'][0])for i in range(count_source)],dtype='<f4')/np.float32(den)
            uv=uv*f24([r[0x48],r[0x49]]).astype('<f4')+f24([r[0x4a],r[0x4b]]).astype('<f4')
            co=(vt>>2)&7
            if co:
                size=4 if co==7 else 2;color=np.array([list(unpack_color(int.from_bytes(original[i*stride+fields['col'][0]:i*stride+fields['col'][0]+size],'little'),co-4))for i in range(count_source)],dtype=float)/255
            else:color=np.tile(np.array([(r[0x55]>>(8*k))&255 for k in range(3)]+[r[0x58]&255],dtype=float)/255,(count_source,1))
            triangles=[(i,i+1,i+2)if i%2==0 else(i+1,i,i+2)for i in range(count_source-2)];order=np.asarray(triangles).flatten()
            check(row['triangle_source_indices']==[list(t)for t in triangles]and n==len(order),'Strip parity/order/multiplicity differs')
            world=np.column_stack([local,np.ones(count_source)])@f24(d['world']).reshape(3,4,order='F').T
            draw_origin=(world.min(0)+world.max(0))/2;draw_inverse=inverse.copy();draw_inverse[3,:3]=draw_origin
            check(np.array_equal(draw_origin,row['PSP_world_origin_subtracted']),'FX draw-local origin differs from original WORLD bounds center')
            expected_vertex=np.column_stack([((world-draw_origin)*units*100)[:,[0,2,1]],uv,color]).astype('<f4')[order]
            check(vertices.tobytes()==expected_vertex.tobytes(),'FX decoded position/primary color/direct-UV differs')
            different=d['view']!=body['VIEW_payload']or d['proj']!=body['PROJECTION_payload']
            expected_flags=(r[0x21]&1)|((1-(r[0xe7]&1))<<1)|((r[0x1d]&1)<<2)|(((r[0xc9]>>16)&1)<<3)|((r[0x1f]&1)<<4)|((r[0x24]&1)<<5)|((r[0x1c]&1)<<6)|(int(different)<<7)
            expected_flags|=(r[0xc7]&1)<<8|((r[0xc7]>>8)&1)<<9|int(r[0xdf]in(0x76,0xa6))<<10|int(r[0xdf]==0xa6)<<11|4096|int(not(r[0x22]&1))<<13|(r[0x9b]<<14)
            check(flags==expected_flags and ref==(r[0xdc]>>8)&255,'FX sampler/blend/alpha/cull/depth flags differ')
            texture_state=st['texture0'];cache_key=(texture_state['sha256'],hashlib.sha256(st['clut']).hexdigest(),tuple(r[k]for k in (0xc2,0xc3,0xc5,0xa8,0xb8)))
            if cache_key not in cache:cache[cache_key]=decode_texture(texture_state['raw'],r,st['clut'],st['clut_known'])[1]
            facts=cache[cache_key];check(facts['rgba_sha256']==row['texture_RGBA_sha256']==source['atlases'][texture]['rgba_sha256'],'FX effective CLUT binding differs')
            view=np.eye(4);view[:,:3]=f24(d['view']).reshape(4,3);proj=f24(d['proj']).reshape(4,4)
            scale=f24([r[k]for k in (0x42,0x43,0x44)]);center=f24([r[k]for k in (0x45,0x46,0x47)]);offset=np.array([r[k]&65535 for k in (0x4c,0x4d)])/16
            remap=np.diag([scale[0]/240,-scale[1]/136,scale[2]/65535,1.]);remap[3,:3]=[(center[0]-offset[0])/240-1,1-(center[1]-offset[1])/136,center[2]/65535]
            check(matrix.tobytes()==(draw_inverse@view@proj@remap).astype('<f4').tobytes(),'Per-draw FX camera differs')
            expected_fog=draw_inverse@view[:,2];expected_fog[3]+=f24([r[0xcd]])[0];expected_fog*=f24([r[0xce]])[0]
            check(fog.tobytes()==expected_fog.astype('<f4').tobytes()and fog_rgb[:3]==tuple((r[0xcf]>>(8*k))&255 for k in range(3)),'FX fog state differs')
            h=np.column_stack([vertices[:,:3].astype(float),np.ones(n)]);bound=8*np.finfo(np.float32).eps*(np.abs(h)@np.abs(matrix.astype(float)))
            check(np.all(np.abs(output[:,:4]-h@matrix.astype(float))<=bound),'Actual FX GPU clip exceeds F32 dot-product bound')
            check(output[:,4:10].tobytes()==vertices[:,3:].tobytes(),'Actual FX GPU UV/color changed')
            check(np.all(np.abs(output[:,10]-h@fog.astype(float))<=8*np.finfo(np.float32).eps*(np.abs(h)@np.abs(fog.astype(float)))),'Actual FX GPU fog exceeds bound')
            clip=np.column_stack([world,np.ones(count_source)])@view@proj@remap;clip=clip[order];valid=(clip[:,3]>1)&np.all(np.abs(clip[:,:2])<=clip[:,3,None],axis=1)
            if valid.any():screen_error=max(screen_error,float(np.max(np.abs((clip[valid,:2]/clip[valid,3,None]-output[valid,:2]/output[valid,3,None])*[240,136]))))
            fx_ids.append(ordinal+1);frame_fx+=1;total_fx+=1;total_fx_vertices+=n
        check(so_at==len(so)and old_so_at==len(old_so),'Incomplete GPU VS output coverage');check(screen_error<.01,f'Visible FX projection error: sample={sample}, max={screen_error} PSP pixels, threshold=0.01')
        frames.append(dict(sample=sample,added_strip_draws=frame_fx,total_GPU_vertices=total_vertices,max_visible_FX_projection_error_PSP_pixels=screen_error));final_fx_ids.append(fx_ids)
    check(at==len(raw)and total_fx==407 and total_fx_vertices==3081,'Unexpected full FX scope')
    for c in actual['captures']:
        stem=c['stem'];paths=[out/(stem+s)for s in ('.rgba','.owner_u32','.depth_stencil_u32')]
        rgb=np.fromfile(paths[0],dtype='u1').reshape(272,480,4);owner=np.fromfile(paths[1],dtype='<u4').reshape(272,480);depth=np.fromfile(paths[2],dtype='<u4').reshape(272,480)
        check(np.all(rgb[:,:,3]==255),'Source alpha write mask changed');check(np.any(owner),'Empty capture')
        if c['mode']in('no_depth_writes','effects_only'):check(not np.any(depth),'No-write FX/depth control changed depth/stencil')
        png=out/(stem+'.png');check(not png.exists(),'Never overwrite derived PNG');Image.fromarray(rgb).save(png)
        images[stem]=(rgb,owner,depth);records.append(dict(stem=stem,rgba_sha256=sha(paths[0]),owner_sha256=sha(paths[1]),depth_stencil_sha256=sha(paths[2]),png_sha256=sha(png)))
    check(len(images)==91,'Expected84 source +7 synthetic captures')
    for i,expected in enumerate(([48,96,144],[96,191,255],[128,255,255])):
        rgb,owner,depth=images[f'double_source_alpha_{i}'];mask=owner>0
        check(np.all(rgb[mask,:3]==expected)and np.all(owner[mask]==1)and np.max(np.abs((depth[mask]&0xffffff)/0xffffff-.5))<1e-7,'Double-source-alpha analytic control failed')
        controls.append(dict(case=i,RGB=expected,pixels=int(mask.sum())))
    for name in ('fog_control_0','fog_control_1','fog_control_2','stencil_depth_fail_control'):
        for suffix in ('.rgba','.owner_u32','.depth_stencil_u32'):check((out/(name+suffix)).read_bytes()==(baseline/(name+suffix)).read_bytes(),'Legacy analytic control changed')
    for i in range(12):
        rgb,owner,depth=images[f'sample_{i}_source_states'];off=images[f'sample_{i}_no_effects'];fog=images[f'sample_{i}_no_fog']
        check(off[0].tobytes()==(baseline/f'sample_{i}_source_states.rgba').read_bytes(),'Disabling FX does not reproduce accepted baseline RGB')
        check(depth.tobytes()==off[2].tobytes()==(baseline/f'sample_{i}_source_states.depth_stencil_u32').read_bytes(),'FX altered original main depth/stencil')
        check(np.array_equal(owner,fog[1])and np.array_equal(depth,fog[2]),'Fog toggling changed owner/depth')
        old=base['frames'][i];mapping=np.zeros(len(source['frames'][i]['draws'])+1,dtype='<u4');by_key={(d['register_record'],d['register_word']):d['owner']for d in old['draws']}
        for d in source['frames'][i]['draws']:mapping[d['owner']]=by_key.get((d['register_record'],d['register_word']),0)
        check(mapping[off[1]].tobytes()==(baseline/f'sample_{i}_source_states.owner_u32').read_bytes(),'Baseline canonical draw ownership changed')
        changed=int(np.any(rgb[:,:,:3]!=off[0][:,:,:3],axis=2).sum());fx_owned=int(np.isin(owner,final_fx_ids[i]).sum());check(changed>0 and fx_owned>0,'Recovered FX not visible in combined output')
        frames[i].update(changed_RGB_pixels=changed,final_FX_owner_pixels=fx_owned)
    sheet=Image.new('RGB',(1440,1200),(22,22,22));draw=ImageDraw.Draw(sheet)
    for i in range(12):
        x=i%3*480;y=i//3*300;sheet.paste(Image.fromarray(images[f'sample_{i}_source_states'][0]).convert('RGB'),(x,y+28));draw.text((x+8,y+6),f'Sample{i}: original strips + complete accepted scene',fill='white')
    sheet.save(out/'CONTACT_SHEET.png')
    report=dict(schema='t3b-source-strip-FX-GPU-audit/v1',passed=True,pid=actual['pid'],adapter=actual['adapter'],frames=frames,added_strip_draws=total_fx,
        added_expanded_GPU_vertices=total_fx_vertices,total_GPU_vertices=sum(f['total_GPU_vertices']for f in frames),actual_GPU_atlases=len(source['atlases']),captures=91,
        no_FX_RGB_and_canonical_owner_and_depth_byte_identical_to_baseline=True,retained_GPU_vertex_outputs_byte_identical=True,double_source_alpha_controls=controls,files=records,
        UE_executed=False,original_PSP_integer_pixel_equivalence=False,semantic_muzzle_identified=False,original_clock_verified=False,
        limits=['D3D texture filtering/interpolation/blend uses continuous arithmetic and differs from complete PSP integer rasterization.',
                'Perspective depth-tested strips only; sprite rectangles/lines/HUD/framebuffer postprocess and FX semantic attachments remain unresolved.'])
    dest.write_text(json.dumps(report,indent=2),encoding='utf-8');print(json.dumps({k:report[k]for k in ('passed','added_strip_draws','added_expanded_GPU_vertices','total_GPU_vertices','actual_GPU_atlases','captures')}))


if __name__=='__main__':main()
