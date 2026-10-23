"""Export observed unweighted world draws + verified Aya/gun with per-draw cameras."""
import argparse,hashlib,json,struct,sys
from pathlib import Path
import numpy as np
from PIL import Image
from extract_runtime_character import read_ppdmp,layout
from inventory_original_scene import draw_stream
from exact_aya_materials import iter_material_draws,decode_texture,material_parameters


def check(v,msg):
    if not v:raise ValueError(msg)
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def read(p):return json.loads(p.read_text(encoding='utf-8'))
def f24(v):return (np.array(v,dtype='<u4')<<8).view('<f4').astype(float)


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--out',type=Path,required=True);p.add_argument('--other-actor-proof',type=Path);a=p.parse_args()
    check(not a.out.exists(),'Never replace observed scene evidence');a.out.mkdir(parents=True)
    root=Path(__file__).resolve().parents[1];project=root.parent/'t3b_unreal';sys.path.insert(0,str(project/'Tools'))
    from run_ge_depth_reference import read_proof
    req_path=project/'Validation/ge_depth_reference_runs/6bb0e3db0bcd40cb98ba9f66aceae654/request.json';req=read(req_path)
    manifests=[read(Path(req[k]['file']))for k in ('body_input','weapon_input')]
    for k,m in zip(('body_input','weapon_input'),manifests):check(sha(Path(req[k]['file']))==req[k]['sha256'],'Actor input changed')
    data=[];uv=[]
    for row,m in zip(req['runtime_proofs'],manifests):
        check(sha(Path(row['file']))==row['sha256'],'Actor proof changed');d,u=read_proof(Path(row['file']),m);data.append(d);uv.append(u)
    dt=np.dtype([('position','<f4',3),('normal','<f4',3),('color','u1',4),('secondary','u1',3),('pad','u1')])
    arrays=[np.frombuffer(d,dtype=dt)for d in data];uvs=[np.frombuffer(d,dtype='<f4').reshape(-1,2)for d in uv]
    bm,wm=manifests
    other=None
    if a.other_actor_proof:
        proof=read(a.other_actor_proof);other_path=Path(proof['input_manifest']['file'])
        check(sha(other_path)==proof['input_manifest']['sha256'],'Other actor input changed');other=read(other_path)
        d,u=read_proof(a.other_actor_proof,other);arrays.append(np.frombuffer(d,dtype=dt));uvs.append(np.frombuffer(u,dtype='<f4').reshape(-1,2))
        check(other['same_GE_dump_pairing']and other['captures']==wm['captures'],'Other actor is not from the same original captures')
    origin=np.array(req['fixed_shared_PSP_world_origin']);units=req['metres_per_PSP_world_unit']
    scale=units*100;inverse=np.array([[1/scale,0,0,0],[0,0,1/scale,0],[0,1/scale,0,0],[*origin,1]])
    atlases={};frames=[];blobs=[]
    for sample,frame in enumerate(wm['frames']):
        capture=wm['captures'][sample];pp=Path(capture['path']);check(sha(pp)==capture['sha256'],'Original GE dump changed')
        commands,push=read_ppdmp(str(pp));states={(d['register_record'],d['register_word']):d for d in iter_material_draws(commands,push)}
        bf=bm['frames'][frame['body_frame_index']]
        actors={(d['register_record'],d['register_word']):(0,d)for d in bm['draws'][bf['first_draw']:bf['first_draw']+106]}
        wd=wm['draws'][frame['first_draw']];actors[(wd['register_record'],wd['register_word'])]=(1,wd)
        if other:
            of=other['frames'][sample]
            for desc in other['draws'][of['first_draw']:of['first_draw']+of['draw_count']]:actors[(desc['register_record'],desc['register_word'])]=(2,desc)
        rows=[];source_actor_count=0;excluded=[];frame_blob=[]
        for d in draw_stream(commands,push):
            key=d['register_record'],d['register_word'];state=states[key];r=state['registers'];v=d['vertex']
            raw=push[v['pointer']:v['pointer']+v['bytes']];vertex_sha=hashlib.sha256(struct.pack('<I',d['vtype'])+raw).hexdigest()
            if key not in actors and d['vtype']!=0x11f:
                excluded.append(dict(record=key[0],word=key[1],vtype=d['vtype'],vertices=d['count']));continue
            check(d['primitive']==3 and d['count']%3==0,'Selected world draw is not triangle-list')
            check(all(x is not None for k in ('world','view','proj')for x in d[k]),'Missing explicit source matrices')
            check(r[0x23]==1 and r[0xde]==7 and r[0xdf]==0x32 and r[0xdb]==0xff0006,'Unobserved GE depth/blend/alpha contract')
            check(r[0x20]==r[0x25]==r[0x28]==r[0xe8]==r[0xe9]==0,'Unsupported dither/color-test/logic/mask')
            check(r[0x15]==r[0xd4]==0 and r[0x16]==r[0xd5]==0x43ddf and r[0xd6]==0 and r[0xd7]==65535,'Unsupported viewport/scissor/depth range')
            check(r[0xd2]==3 and r[0x9b]==0,'Unsupported source framebuffer/cull mode')
            check(not(r[0x24]&1)or(r[0xdc]==1 and r[0xdd]==0x20201),'Unsupported stencil function/reference/ops')
            params=material_parameters(r)
            check(params['texture_enabled']and params['texture_function']==0 and params['texture_alpha_used']and
                  params['uv_map_mode']==0 and params['uv_scale']==[1.,1.]and params['uv_offset']==[0.,0.]and
                  params['wrap_u']==params['wrap_v']=='repeat'and params['min_filter_raw']==params['mag_filter_raw']==1 and
                  ((r[0xc2]>>16)&7)==0,'Unsupported texture contract')
            tex=state['texture0'];check(tex is not None and not tex['framebuffer'],'Missing original texture backing')
            rgba,facts=decode_texture(tex['raw'],r,state['clut'],state['clut_known']);rgba_sha=facts['rgba_sha256']
            if rgba_sha not in atlases:
                png=a.out/('original_'+rgba_sha[:16]+'.png');Image.frombytes('RGBA',(facts['width'],facts['height']),rgba).save(png)
                atlases[rgba_sha]=dict(index=len(atlases),width=facts['width'],height=facts['height'],rgba=rgba,
                                      png=dict(file=str(png.resolve()),sha256=sha(png)),rgba_sha256=rgba_sha)
            vertices=np.empty((d['count'],9),dtype='<f4')
            if key in actors:
                actor,desc=actors[key];check(vertex_sha==desc['vertex_sha256'],'Actual actor geometry changed')
                check(d['world']==desc['WORLD_payload']and d['view']==desc['VIEW_payload']and d['proj']==desc['PROJECTION_payload'],'Actor camera/WORLD mismatch')
                first=desc['first_output_vertex'];source=arrays[actor][first:first+d['count']]
                check(not np.any(source['secondary']),'Secondary specular needs a separate pipeline')
                world=source['position'].astype(float);color=source['color'].astype(float)/255
                vertices[:,3:5]=uvs[actor][first:first+d['count']];category=('body','weapon','other_original_actor')[actor];source_actor_count+=1
            else:
                check(r[0x17]==1 and all(r[k]==0 for k in range(0x18,0x1c))and r[0x53]==7 and
                      r[0x54]==0 and r[0x5c]==0xffffff and r[0x5d]==255,'Unproven unweighted vertex lighting')
                stride,off=layout(d['vtype']);check(stride==20 and len(raw)==d['count']*20,'Unknown unweighted vertex layout')
                local=np.array([struct.unpack_from('<3h',raw,i*20+off['pos'][0])for i in range(d['count'])],dtype=float)/32768
                mat=f24(d['world']).reshape(3,4,order='F');world=np.column_stack([local,np.ones(len(local))])@mat.T
                color=np.array([struct.unpack_from('<4B',raw,i*20+8)for i in range(d['count'])],dtype=float)/255
                vertices[:,3:5]=[struct.unpack_from('<2f',raw,i*20)for i in range(d['count'])];category='unweighted_world'
            vertices[:,:3]=((world-origin)*units*100)[:,[0,2,1]];vertices[:,5:]=color
            view=np.eye(4);view[:,:3]=f24(d['view']).reshape(4,3);proj=f24(d['proj']).reshape(4,4)
            vp_scale=f24([r[k]for k in (0x42,0x43,0x44)]);vp_center=f24([r[k]for k in (0x45,0x46,0x47)])
            offset=np.array([r[k]&65535 for k in (0x4c,0x4d)])/16
            remap=np.diag([2*vp_scale[0]/480,-2*vp_scale[1]/272,vp_scale[2]/65535,1.])
            remap[3,:3]=[2*(vp_center[0]-offset[0])/480-1,1-2*(vp_center[1]-offset[1])/272,vp_center[2]/65535]
            matrix=(inverse@view@proj@remap).astype('<f4')
            fog_plane=(inverse@view[:,2]);fog_plane[3]+=f24([r[0xcd]])[0];fog_plane=(fog_plane*f24([r[0xce]])[0]).astype('<f4')
            fog_rgb=[(r[0xcf]>>(8*k))&255 for k in range(3)]+[0]
            different_camera=d['view']!=wd['VIEW_payload']or d['proj']!=wd['PROJECTION_payload']
            flags=(int(params['alpha_blend_enabled'])|((1-(r[0xe7]&1))<<1)|((r[0x1d]&1)<<2)|
                   (int(params['color_double'])<<3)|((r[0x1f]&1)<<4)|((r[0x24]&1)<<5)|((r[0x1c]&1)<<6)|(int(different_camera)<<7))
            ordinal=len(rows);index=atlases[rgba_sha]['index']
            block=struct.pack('<5I',index,ordinal,flags,d['count'],(r[0xdc]>>8)&255)+matrix.tobytes()+fog_plane.tobytes()+struct.pack('<4I',*fog_rgb)+vertices.tobytes()
            frame_blob.append(block)
            rows.append(dict(owner=ordinal+1,texture=index,flags=flags,vertices=d['count'],category=category,
                register_record=key[0],register_word=key[1],vertex_sha256=vertex_sha,vertex_input_sha256=hashlib.sha256(vertices.tobytes()).hexdigest(),
                WORLD_payload=d['world'],VIEW_payload=d['view'],PROJECTION_payload=d['proj'],registers={hex(k):v for k,v in r.items()},
                different_from_main_camera=different_camera,texture_RGBA_sha256=rgba_sha))
        check(source_actor_count==107+(28 if other else 0),'Incomplete original actor draw set')
        frames.append(dict(sample=sample,capture=capture,draws=rows,excluded_draws=excluded));blobs.append(b''.join(frame_blob))
    binary=a.out/'observed_scene_gpu.bin'
    with binary.open('wb')as f:
        f.write(b'T3BGEF1\0'+struct.pack('<4I',480,272,12,len(atlases)))
        for t in atlases.values():f.write(struct.pack('<2I',t['width'],t['height']));f.write(t['rgba'])
        for frame,blob in zip(frames,blobs):f.write(struct.pack('<2I',frame['sample'],len(frame['draws'])));f.write(blob)
    result=dict(schema='t3b-observed-per-draw-scene-GPU-input/v1',passed=True,frames=frames,
        atlases=[{k:v for k,v in t.items()if k!='rgba'}for t in atlases.values()],binary=dict(file=str(binary.resolve()),sha256=sha(binary)),
        actor_provenance=dict(file=str(req_path),sha256=sha(req_path)),fixed_shared_PSP_world_origin=origin.tolist(),metres_per_PSP_world_unit=units,
        producer_sha256=sha(Path(__file__)),complete_level=False,original_timing_verified=False,
        limits=['All observed unweighted VTYPE11f triangle draws and verified Aya/gun only; other characters/FX/HUD remain excluded.',
                'Per-draw cameras preserved; geometry/texture identities do not recover game-object semantics.'])
    if other:
        result['other_actor_proof']=dict(file=str(a.other_actor_proof.resolve()),sha256=sha(a.other_actor_proof))
        result['limits'][0]='All observed unweighted VTYPE11f triangle draws, verified Aya/gun and the exact known28-draw creature. Other unweighted FX/HUD remain excluded.'
    (a.out/'inputs.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps(dict(passed=True,frames=12,atlases=len(atlases),draws=sum(len(f['draws'])for f in frames),vertices=sum(d['vertices']for f in frames for d in f['draws']))))


if __name__=='__main__':main()
