"""Independently audit source actor inputs, scene uploads and actual GPU occlusion."""
import argparse,collections,hashlib,json,struct,sys
from pathlib import Path
import numpy as np
from PIL import Image

def check(v,s):
    if not v:raise ValueError(s)
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def read(p):return json.loads(p.read_text(encoding='utf-8'))
def checked(i):
    p=Path(i['file']);check(sha(p)==i['sha256'],'Evidence identity differs: '+str(p));return p
def f24(v):return(np.asarray(v,dtype='<u4')<<8).view('<f4').astype(float)

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--run',type=Path,required=True);a=p.parse_args();out=a.run
    check(not(out/'independent_verification.json').exists(),'Never replace a completed proof')
    req=read(out/'request.json');actual=read(out/'actual_gpu_report.json');start=read(out/'started.json');done=read(out/'completed.json')
    check(req['build_exit_code']==done['exit_code']==0 and actual['pid']==start['pid']==done['pid'],'Actual build/process identity differs')
    checked(req['executable'])
    for row in req['sources']:checked(row)
    for row in req['adapters']:
        original=(out/row['source']).read_text(encoding='utf-8');check(checked(row).read_text(encoding='utf-8')==original.replace(row['before'],row['after']),'Entry adapter altered renderer')
    scene=read(checked(req['scene']));raw=checked(req['scene_binary']).read_bytes();checked(req['palette']);checked(req['palette_request'])
    skin=read(checked(scene['skin_inputs']));comparison_path=checked(scene['lighting_comparison']);comparison=read(comparison_path)
    skin_binary=checked(skin['binary']).read_bytes();lit_path=checked(scene['production_skin_output']);official=comparison_path.parent/'official_outputs.bin'
    check(comparison['passed'] and sha(official)==comparison['official_output_sha256'] and lit_path.read_bytes()==official.read_bytes(),'Skin/light software reference differs')
    for identity in skin['provenance']:checked(identity)
    checked(skin['CPU_GE_proof']);checked(scene['CPU_GE_proof'])
    for i in comparison['reference_sources']+comparison['compatibility_headers']:checked(i)
    project=Path(__file__).resolve().parents[1];sys.path.insert(0,str(project.parent/'psp_parse/tools'))
    from extract_runtime_character import read_ppdmp,layout
    from inventory_original_scene import draw_stream
    from export_aya_actual_weapon import matrix_draws
    from exact_aya_materials import iter_material_draws,decode_texture
    dt=np.dtype([('position','<f4',3),('normal','<f4',3),('color','u1',4),('secondary','u1',3),('pad','u1')]);lit=np.frombuffer(lit_path.read_bytes(),dtype=dt)
    check(raw[:8]==b'T3BSFC1\0' and struct.unpack_from('<4I',raw,8)==(480,272,3,len(scene['atlases'])),'Scene scope differs');at=24
    for i,t in enumerate(scene['atlases']):
        w,h=struct.unpack_from('<2I',raw,at);at+=8;rgba=raw[at:at+w*h*4];at+=w*h*4
        check(w==t['width'] and h==t['height'] and hashlib.sha256(rgba).hexdigest()==t['rgba_sha256'] and (out/('atlas_%d_actual.rgba'%i)).read_bytes()==rgba,'Actual texture upload differs')
    coverage=[];source_actor_vertices=0;total_vertices=0;all_draws=0
    for frame in scene['frames']:
        sample=frame['sample'];cmds,push=read_ppdmp(str(checked(frame['capture'])))
        sources={(d['register_record'],d['register_word']):d for d in draw_stream(cmds,push)}
        states={(d['register_record'],d['register_word']):d for d in iter_material_draws(cmds,push)}
        mats={(d['register_record'],d['register_word']):d for d in matrix_draws(cmds,push)}
        actors={(d['record'],d['word']):d for d in skin['draws'] if d['sample']==sample}
        sid,n=struct.unpack_from('<2I',raw,at);at+=8;check(sid==sample and n==len(frame['draws']),'Scene frame differs')
        ge=np.fromfile(out/'ge'/('sample_%d.clip_uv_color_fog_f32'%sample),dtype='<f4').reshape(-1,11)
        runtime=np.fromfile(out/'runtime'/('sample_%d.clip_uv_color_fog_f32'%sample),dtype='<f4').reshape(-1,11)
        check(ge.tobytes()==runtime.tobytes(),'Actual GE/production VS outputs differ');cursor=0;max_error=0.;target_ids=[];triangles={}
        source_order=[]
        for ordinal,row in enumerate(frame['draws']):
            key=row['record'],row['word'];source_order.append(key);d=sources[key];r=states[key]['registers'];vt=d['vtype'];count=d['count'];stride,off=layout(vt)
            source=push[d['vertex']['pointer']:d['vertex']['pointer']+d['vertex']['bytes']]
            check(hashlib.sha256(struct.pack('<I',vt)+source).hexdigest()==row['source_vertex_sha256'],'Actual source geometry differs')
            texidx,order,flags,nv,ref=struct.unpack_from('<5I',raw,at);at+=20
            matrix=np.frombuffer(raw,dtype='<f4',count=16,offset=at).reshape(4,4);at+=64;fog=np.frombuffer(raw,dtype='<f4',count=4,offset=at);at+=16;fog_rgb=struct.unpack_from('<4I',raw,at);at+=16
            vertices=np.frombuffer(raw,dtype='<f4',count=nv*9,offset=at).reshape(nv,9);at+=nv*36
            check(order==ordinal and row['owner']==order+1 and texidx==row['texture'] and nv==row['vertices'] and hashlib.sha256(vertices.tobytes()).hexdigest()==row['vertex_input_sha256'],'Serialized scene draw differs')
            target=row['category']=='CPU_correlated_effect';check(target==bool(flags&4096),'Effect control category differs')
            expected_flags=(r[0x21]&1)|((1-(r[0xe7]&1))<<1)|((r[0x1d]&1)<<2)|(((r[0xc9]>>16)&1)<<3)|((r[0x1f]&1)<<4)|((r[0x24]&1)<<5)|((r[0x1c]&1)<<6)
            expected_flags|=(r[0xc7]&1)<<8|((r[0xc7]>>8)&1)<<9|int(r[0xdf]==0xa6)*3072|int(target)*4096|int(not(r[0x22]&1))*8192|(r[0x9b]<<14)
            check(flags==row['flags']==expected_flags and ref==(r[0xdc]>>8)&255,'Original source draw state differs')
            check(row['registers']=={hex(k):v for k,v in r.items()},'Retained register state differs')
            W=np.eye(4);W[:,:3]=f24(d['world']).reshape(4,3);V=np.eye(4);V[:,:3]=f24(d['view']).reshape(4,3);P=f24(d['proj']).reshape(4,4)
            if key in actors:
                actor=actors[key];m=mats[key];sa=actor['binary_byte_offset'];source_actor_vertices+=count
                check(skin_binary[sa:sa+1024]==struct.pack('<256I',*[r.get(k,0)for k in range(256)]),'Raw skinning registers differ')
                check(skin_binary[sa+1024:sa+1072]==f24(m['world']).astype('<f4').tobytes() and skin_binary[sa+1072:sa+1456]==f24([x or 0 for x in m['bones']]).astype('<f4').tobytes(),'Raw skinning matrix input differs')
                slots=((vt>>14)&7)+1;check(struct.unpack_from('<2I',skin_binary,sa+1456)==(count,slots),'Skinning extent differs')
                decoded=[]
                for i in range(count):
                    base=i*stride
                    decoded.append([x/32768 for x in struct.unpack_from('<3h',source,base+off['pos'][0])]+[x/128 for x in struct.unpack_from('<3b',source,base+off['nrm'][0])]+[x/32768 for x in struct.unpack_from('<%dH'%slots,source,base+off['wt'][0])]+[0]*(8-slots)+[x/32768 for x in struct.unpack_from('<2H',source,base+off['uv'][0])])
                decoded=np.asarray(decoded,dtype='<f4');check(skin_binary[sa+1464:sa+1464+count*64]==decoded.tobytes(),'Decoded actor input differs from actual original vertices')
                result=lit[actor['first_output_vertex']:actor['first_output_vertex']+count];world=result['position'].astype(float);origin=(world.min(0)+world.max(0))/2
                pos=(world-origin).astype('<f4');transform=np.eye(4);transform[3,:3]=origin;uv=decoded[:,14:];color=result['color'].astype('<f4')/np.float32(255)
                original_h=np.column_stack([world,np.ones(count)]);original_clip=original_h@V@P
            else:
                pos=np.asarray([struct.unpack_from('<3h',source,i*stride+off['pos'][0])for i in range(count)],dtype='<f4')/np.float32(32768);transform=W
                uv=np.asarray([struct.unpack_from('<2H'if vt&3==2 else '<2f',source,i*stride+off['uv'][0])for i in range(count)],dtype='<f4')
                if vt&3==2:uv/=np.float32(32768)
                uv=(uv*f24([r[0x48],r[0x49]]).astype('<f4')).astype('<f4')+f24([r[0x4a],r[0x4b]]).astype('<f4')
                color=np.asarray([list(source[i*stride+off['col'][0]:i*stride+off['col'][0]+4])for i in range(count)],dtype='<f4')/np.float32(255)
                original_clip=np.column_stack([pos.astype(float),np.ones(count)])@W@V@P
            indices=np.arange(count) if d['primitive']==3 else np.asarray([i for k in range(count-2)for i in([k+1,k,k+2]if k&1 else[k,k+1,k+2])])
            expected=np.column_stack([pos,uv,color]).astype('<f4')[indices];check(expected.tobytes()==vertices.tobytes(),'Submitted scene geometry/UV/color differs')
            vp=f24([r[k]for k in(0x42,0x43,0x44)]);center=f24([r[k]for k in(0x45,0x46,0x47)]);offset=np.asarray([r[k]&65535 for k in(0x4c,0x4d)])/16
            R=np.diag([vp[0]/240,-vp[1]/136,vp[2]/65535,1]);R[3,:3]=[(center[0]-offset[0])/240-1,1-(center[1]-offset[1])/136,center[2]/65535]
            check(matrix.tobytes()==(transform@V@P@R).astype('<f4').tobytes(),'Source camera/projection differs')
            expected_fog=transform@V[:,2];expected_fog[3]+=f24([r[0xcd]])[0];expected_fog*=f24([r[0xce]])[0]
            check(fog.tobytes()==expected_fog.astype('<f4').tobytes()and fog_rgb[:3]==tuple((r[0xcf]>>(8*k))&255 for k in range(3)),'Source fog differs')
            output=ge[cursor:cursor+nv];cursor+=nv;h=np.column_stack([vertices[:,:3].astype(float),np.ones(nv)])
            check(np.all(np.abs(output[:,:4]-h@matrix.astype(float))<=8*np.finfo(np.float32).eps*(np.abs(h)@np.abs(matrix.astype(float)))),'Actual GPU clip values exceed bound')
            check(output[:,4:10].tobytes()==vertices[:,3:].tobytes(),'Actual GPU UV/color differs')
            check(np.all(np.abs(output[:,10]-h@fog.astype(float))<=8*np.finfo(np.float32).eps*(np.abs(h)@np.abs(fog.astype(float)))),'Actual GPU fog differs')
            original=(original_clip@R)[indices];valid=(original[:,3]>1e-6)&np.all(np.abs(original[:,:2])<=original[:,3,None],axis=1)
            if valid.any():max_error=max(max_error,float(np.max(np.abs((original[valid,:2]/original[valid,3,None]-output[valid,:2]/output[valid,3,None])*[240,136]))))
            if target:target_ids.append(ordinal+1);triangles[ordinal+1]=output[:,:4].astype(float).reshape(-1,3,4)
            state=states[key];rgba,facts=decode_texture(state['texture0']['raw'],r,state['clut'],state['clut_known']);check(facts['rgba_sha256']==row['texture_RGBA_sha256']==scene['atlases'][texidx]['rgba_sha256'],'Source CLUT binding differs')
        check(source_order==sorted(source_order)and len(target_ids)==8 and cursor==len(ge)and max_error<0.01,'Draw order/coverage/projection differs')
        total_vertices+=cursor;all_draws+=n;records={}
        for variant in ('ge','runtime','previous','no_effect','isolated','before_effect','after_effect'):
            stem=out/('sample_%d_%s'%(sample,variant));rgb=np.fromfile(str(stem)+'.rgba',dtype='u1').reshape(272,480,4);owner=np.fromfile(str(stem)+'.owner_u32',dtype='<u4').reshape(272,480);depth=np.fromfile(str(stem)+'.depth_stencil_u32',dtype='<u4').reshape(272,480)
            check(np.all(rgb[:,:,3]==255),'Alpha write mask differs');Image.fromarray(rgb).save(str(stem)+'.png');records[variant]=(rgb,owner,depth)
        check(all(x.tobytes()==y.tobytes()for x,y in zip(records['ge'],records['runtime'])),'GE/production framebuffer differs')
        check(all(x.tobytes()==y.tobytes()for x,y in zip(records['previous'],records['no_effect'])),'Previous-color intervention differs from no-effect scene')
        check(records['runtime'][2].tobytes()==records['no_effect'][2].tobytes()==records['previous'][2].tobytes(),'Target effect changed scene main depth/stencil')
        iso=np.isin(records['isolated'][1],target_ids);after=np.isin(records['after_effect'][1],target_ids);lost=iso&~after
        check(not np.any(after&~iso) and lost.any(),'Scene depth did not reduce isolated effect coverage')
        before=records['before_effect'];post=records['after_effect'];check(before[2].tobytes()==post[2].tobytes(),'Effect prefix changed source depth/stencil')
        check(np.all((before[2][lost]&0xffffff)>0),'Lost effect coverage lacks prior source depth')
        tested=0;largest_margin=0.
        for owner_id in target_ids:
            ys,xs=np.where(lost&(records['isolated'][1]==owner_id));depths=(before[2][ys,xs]&0xffffff).astype(float)/16777215
            found=np.zeros(len(xs),dtype=bool)
            for clip in triangles[owner_id]:
                ndc=clip[:,:3]/clip[:,3,None];screen=np.column_stack([(ndc[:,0]+1)*240,(1-ndc[:,1])*136])
                matrix=np.vstack([screen.T,np.ones(3)])
                if abs(np.linalg.det(matrix))<1e-10:continue
                bary=np.column_stack([xs+.5,ys+.5,np.ones(len(xs))])@np.linalg.inv(matrix).T
                inside=np.all(bary>=-0.002,axis=1)&np.all(bary<=1.002,axis=1);z=bary@ndc[:,2]
                # A lost last isolated fragment must fail the source GEQUAL depth.
                match=inside&(z<depths-2/16777215);found|=match
                if match.any():largest_margin=max(largest_margin,float(np.max(depths[match]-z[match])))
            check(found.all(),'A lost effect pixel does not fail original scene depth');tested+=len(xs)
        changed=np.any(records['runtime'][0][:,:,:3]!=records['no_effect'][0][:,:,:3],axis=2)
        final=np.isin(records['runtime'][1],target_ids);check(changed.any()and np.all(final[changed]),'Effect changed RGB outside final target coverage')
        delta=np.any(post[0][:,:,:3]!=before[0][:,:,:3],axis=2);check(np.all(after[delta]),'Prefix RGB delta outside effect coverage')
        categories=collections.Counter(row['category']for row in frame['draws']);visible=collections.Counter()
        for row in frame['draws']:visible[row['category']]+=int(np.count_nonzero(records['runtime'][1]==row['owner']))
        check(all(visible[k]>0 for k in('body','weapon','other_original_actor','unweighted_world','CPU_correlated_effect')),'Required source scene component invisible')
        coverage.append(dict(sample=sample,draw_categories=dict(categories),visible_owner_pixels=dict(visible),GPU_vertices=cursor,max_projection_error_PSP_pixels=max_error,
                             isolated_effect_pixels=int(iso.sum()),scene_effect_pixels=int(final.sum()),source_depth_rejected_pixels=tested,RGB_delta_pixels=int(changed.sum()),largest_depth_margin=largest_margin))
    check(at==len(raw)and source_actor_vertices==skin['total_vertices']==16497 and all_draws==838 and len(actual['captures'])==21,'Incomplete source/actual GPU coverage')
    proof=dict(passed=True,actual_pid=actual['pid'],adapter=actual['adapter'],captures=21,source_draws=all_draws,GPU_vertices=total_vertices,frames=coverage,
               request=dict(file=str((out/'request.json').resolve()),sha256=sha(out/'request.json')),source_actor_vertices=source_actor_vertices,
               UE_executed=False,complete_scene=False,PSP_framebuffer_equivalence=False,default_M1_replaced=False,
               limits=['Only observed known actor/world draws and the24 CPU-correlated effect draws. Other strips, sprites, HUD and framebuffer passes are excluded.',
                       'Native D3D11 reference uses D24S8; source GEQUAL occlusion is validated within this model, not PSP fixed-point/D16 final framebuffer equality.',
                       'GE and production color paths share the source-state renderer. Original authored animation timing and gameplay remain unverified.'])
    (out/'independent_verification.json').write_text(json.dumps(proof,indent=2),encoding='utf-8')
    html='''<!doctype html><meta charset="utf-8"><title>原场景与原版颜色特效</title><style>body{background:#171a1d;color:#eee;font:16px system-ui;max-width:1000px;margin:30px auto}img{width:960px;max-width:100%;image-rendering:pixelated}select{padding:8px;margin:8px}p{line-height:1.6}</style><h1>Aya／原枪／异形／街景与原版颜色特效</h1><p>3份同帧原GE记录；native D3D11验证，原素材，尚非UE可玩M1。只含已核对的角色、街景和选定特效；其他FX、sprites与HUD尚未合并。切换“关闭选定特效”查看其实际贡献。</p><select id="frame"><option value="0">记录1</option><option value="1">记录2</option><option value="2">记录3</option></select><select id="mode"><option value="runtime">生产颜色流程</option><option value="ge">直接原GE输入</option><option value="no_effect">关闭选定特效</option><option value="previous">改写前颜色对照</option><option value="isolated">孤立特效</option><option value="before_effect">特效之前的场景</option><option value="after_effect">特效之后的场景</option></select><img id="view"><script>const f=document.querySelector('#frame'),m=document.querySelector('#mode'),v=document.querySelector('#view');function update(){v.src=`sample_${f.value}_${m.value}.png`}f.onchange=m.onchange=update;update();</script>'''
    (out/'PREVIEW.html').write_text(html,encoding='utf-8');print(json.dumps(dict(passed=True,captures=21,source_draws=all_draws,GPU_vertices=total_vertices,frames=coverage)))

if __name__=='__main__':main()
