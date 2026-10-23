"""Independently audit original GE inputs, actual D3D11 uploads/VS/framebuffers and controls."""
import argparse
import hashlib
import json
import struct
import sys
from pathlib import Path
import numpy as np
from PIL import Image


def check(v,msg):
    if not v:raise ValueError(msg)
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def read(p):return json.loads(p.read_text(encoding='utf-8'))
def checked(item):
    p=Path(item['file']);check(sha(p)==item['sha256'],'Retained evidence changed: '+str(p));return p
def f24(values):return(np.asarray(values,dtype='<u4')<<8).view('<f4').astype(float)


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--run',type=Path,required=True);args=p.parse_args();out=args.run
    check(not(out/'independent_verification.json').exists(),'Never replace a completed GPU proof')
    request=read(out/'request.json');actual=read(out/'actual_gpu_report.json');started=read(out/'started.json');done=read(out/'completed.json')
    check(request['build_exit_code']==done['exit_code']==0 and actual['pid']==started['pid']==done['pid'],'Actual GPU process/build identity differs')
    for source in request['sources']:checked(source)
    checked(request['executable']);adapter=checked(request['adapter']).read_text(encoding='utf-8')
    original=(out/'ge_strip_fx_reference.cpp').read_text(encoding='utf-8')
    check(adapter==original.replace('int main(int argc,char** argv) {','int T3BStripLegacyMain(int argc,char** argv) {'),'GPU adapter changes more than legacy entry name')
    inputs=read(checked(request['inputs']));proof=read(checked(inputs['proof']));check(inputs['passed']and proof['passed'],'Source evidence not passed')
    project=Path(__file__).resolve().parents[1];sys.path.insert(0,str(project.parent/'psp_parse/tools'))
    from extract_runtime_character import read_ppdmp
    from inventory_original_scene import draw_stream
    from exact_aya_materials import iter_material_draws,decode_texture
    from analyze_fx_node_time import sidecar
    raw=checked(request['binary']).read_bytes();check(raw[:8]==b'T3BPCG1\0'and struct.unpack_from('<4I',raw,8)==(480,272,3,len(inputs['textures'])),'GPU input scope differs');at=24
    for i,t in enumerate(inputs['textures']):
        w,h=struct.unpack_from('<2I',raw,at);at+=8;rgba=raw[at:at+w*h*4];at+=w*h*4
        check((w,h)==(t['width'],t['height'])and hashlib.sha256(rgba).hexdigest()==t['RGBA_sha256'],'Source texture bytes differ')
        check((out/('atlas_%d_actual.rgba'%i)).read_bytes()==rgba,'Actual GPU texture upload/readback differs')
    check((out/'white_actual.rgba').read_bytes()==b'\xff'*4,'White intervention upload differs')
    frames=[];bindings=[];source_rows=iter(inputs['draws']);total_vertices=0
    for sample in range(3):
        sid,count=struct.unpack_from('<2I',raw,at);at+=8;check(sid==sample and count==8,'Matched GPU frame/draw scope differs')
        block=next(b for b in proof['matched_blocks']if b['GE_sample']==sample);commands,push=read_ppdmp(str(checked(block['capture'])))
        draws={(d['register_record'],d['register_word']):d for d in draw_stream(commands,push)}
        states={(s['register_record'],s['register_word']):s for s in iter_material_draws(commands,push)}
        streams={k:np.fromfile(out/k/('sample_%d.clip_uv_color_fog_f32'%sample),dtype='<f4').reshape(-1,11)for k in ('ge','runtime','previous')}
        check(streams['ge'].tobytes()==streams['runtime'].tobytes(),'Actual GPU runtime VS differs from direct GE input')
        cursor=0;max_projection_error=0.;frame_flags=set()
        for ordinal in range(count):
            row=next(source_rows);m=row['matched_primitive'];key=m['record'],m['word'];d=draws[key];state=states[key];r=state['registers']
            texture,flags,ref=struct.unpack_from('<3I',raw,at);at+=12;frame_flags.add(flags)
            matrix=np.frombuffer(raw,dtype='<f4',count=16,offset=at).reshape(4,4);at+=64;fog=np.frombuffer(raw,dtype='<f4',count=4,offset=at);at+=16
            fog_rgb=list(struct.unpack_from('<4I',raw,at));at+=16;regs=list(struct.unpack_from('<256I',raw,at));at+=1024
            check(regs==[r.get(k,0)for k in range(256)]and m['WORLD_payload']==d['world']and m['VIEW_payload']==d['view']and m['PROJECTION_payload']==d['proj'],'Raw GE state/matrices differ')
            vt,n,mode,palette_size=struct.unpack_from('<4I',raw,at);at+=16;source,parent=struct.unpack_from('<4I',raw,at),struct.unpack_from('<4I',raw,at+16);at+=32
            palette=raw[at:at+palette_size];at+=palette_size;indices=struct.unpack_from('<%dI'%n,raw,at);at+=n*4
            before=raw[at:at+n*16];at+=n*16;after=raw[at:at+n*16];at+=n*16;expanded=struct.unpack_from('<I',raw,at)[0];at+=4
            vertex=np.frombuffer(raw,dtype='<f4',count=expanded*9,offset=at).reshape(expanded,9);at+=expanded*36
            op=m['CPU_palette_operation'];binding=m['source_color_binding'];ge_vertex=d['vertex'];ge_bytes=push[ge_vertex['pointer']:ge_vertex['pointer']+ge_vertex['bytes']]
            check(vt==d['vtype']==0x11e and n==d['count']and mode==op['mode']and list(source)==op['source_bits']and list(parent)==op['parent_bits'],'Source runtime operands differ')
            check(before==sidecar(binding['vertices_before']['raw'])and after==ge_bytes==sidecar(binding['vertices_after']['raw'])and list(indices)==binding['color_indices']and palette==sidecar(op['source_palette']['raw']),'Original palette/reference/vertex bindings differ')
            stem=out/('sample_%d_draw_%d'%(sample,ordinal));check(Path(str(stem)+'_production_palette.rgba').read_bytes()==sidecar(op['expected_palette']['raw'])and Path(str(stem)+'_production_vertices.bin').read_bytes()==ge_bytes,'Executed production buffers differ')
            local=np.array([struct.unpack_from('<3h',ge_bytes,k*16+8)for k in range(n)],dtype='<f4')/np.float32(32768)
            uv=np.array([struct.unpack_from('<2H',ge_bytes,k*16)for k in range(n)],dtype='<f4')/np.float32(32768)
            uv=(uv*f24([r[0x48],r[0x49]]).astype('<f4')).astype('<f4')+f24([r[0x4a],r[0x4b]]).astype('<f4')
            color=np.array([list(ge_bytes[k*16+4:k*16+8])for k in range(n)],dtype='<f4')/np.float32(255)
            order=np.asarray([i for k in range(n-2)for i in([k+1,k,k+2]if k&1 else[k,k+1,k+2])]);expected_vertex=np.column_stack([local,uv,color]).astype('<f4')[order]
            check(vertex.tobytes()==expected_vertex.tobytes()and hashlib.sha256(vertex.tobytes()).hexdigest()==row['vertex_input_sha256'],'GPU submitted attributes differ from independently decoded GE')
            W=np.eye(4);W[:,:3]=f24(d['world']).reshape(4,3);V=np.eye(4);V[:,:3]=f24(d['view']).reshape(4,3);P=f24(d['proj']).reshape(4,4)
            scale=f24([r[k]for k in (0x42,0x43,0x44)]);center=f24([r[k]for k in (0x45,0x46,0x47)]);offset=np.array([r[k]&65535 for k in (0x4c,0x4d)])/16
            remap=np.diag([scale[0]/240,-scale[1]/136,scale[2]/65535,1]);remap[3,:3]=[(center[0]-offset[0])/240-1,1-(center[1]-offset[1])/136,center[2]/65535]
            check(matrix.tobytes()==(W@V@P@remap).astype('<f4').tobytes(),'Source local-to-GPU clip matrix differs')
            expected_fog=W@V[:,2];expected_fog[3]+=f24([r[0xcd]])[0];expected_fog*=f24([r[0xce]])[0]
            check(fog.tobytes()==expected_fog.astype('<f4').tobytes()and fog_rgb[:3]==[(r[0xcf]>>(8*k))&255 for k in range(3)],'Source fog state differs')
            flags_expected=1|((1-(r[0xe7]&1))<<1)|((r[0x1d]&1)<<2)|(((r[0xc9]>>16)&1)<<3)|((r[0x1f]&1)<<4)|((r[0x24]&1)<<5)|((r[0x1c]&1)<<6)
            flags_expected|=(r[0xc7]&1)<<8|((r[0xc7]>>8)&1)<<9|1024|2048|4096|(r[0x9b]<<14)
            check(flags==flags_expected and ref==(r[0xdc]>>8)&255,'Source blend/alpha/depth/cull/sampler flags differ')
            rgba,facts=decode_texture(state['texture0']['raw'],r,state['clut'],state['clut_known'])
            check(facts['rgba_sha256']==inputs['textures'][texture]['RGBA_sha256']==m['texture_RGBA_sha256'],'Actual source CLUT/texture binding differs')
            output=streams['ge'][cursor:cursor+expanded];old=streams['previous'][cursor:cursor+expanded];cursor+=expanded;total_vertices+=expanded
            h=np.column_stack([vertex[:,:3].astype(float),np.ones(expanded)]);bound=8*np.finfo(np.float32).eps*(np.abs(h)@np.abs(matrix.astype(float)))
            check(np.all(np.abs(output[:,:4]-h@matrix.astype(float))<=bound),'Actual GPU clip position exceeds F32 dot bound')
            check(output[:,4:10].tobytes()==vertex[:,3:].tobytes(),'Actual GPU UV/color differs')
            check(np.all(np.abs(output[:,10]-h@fog.astype(float))<=8*np.finfo(np.float32).eps*(np.abs(h)@np.abs(fog.astype(float)))),'Actual GPU fog exceeds F32 bound')
            check(old[:,:6].tobytes()==output[:,:6].tobytes()and old[:,10].tobytes()==output[:,10].tobytes(),'Previous-color control changed transform/UV/fog')
            original_clip=h@W@V@P@remap;valid=(original_clip[:,3]>1)&np.all(np.abs(original_clip[:,:2])<=original_clip[:,3,None],axis=1)
            if valid.any():max_projection_error=max(max_projection_error,float(np.max(np.abs((original_clip[valid,:2]/original_clip[valid,3,None]-output[valid,:2]/output[valid,3,None])*[240,136]))))
            bindings.append(dict(sample=sample,draw=ordinal,GE_record=m['record'],texture_RGBA_sha256=facts['rgba_sha256']))
        check(cursor==len(streams['ge'])and max_projection_error<0.01,'GPU stream coverage/projection threshold differs')
        check(len(frame_flags)==1,'Last-state hardware getters cover only one raster/sampler family per frame')
        frames.append(dict(sample=sample,draws=count,GPU_vertices=cursor,max_projection_error_PSP_pixels=max_projection_error))
    check(at==len(raw)and total_vertices==144,'Unconsumed input or unexpected GPU vertex count')
    records={};pixel_checks=[]
    for c in actual['captures']:
        stem=c['stem'];color_path=out/(stem+'.rgba');ids_path=out/(stem+'.owner_u32');z_path=out/(stem+'.depth_stencil_u32')
        rgba=np.fromfile(color_path,dtype='u1').reshape(272,480,4);owner=np.fromfile(ids_path,dtype='<u4').reshape(272,480);depth=np.fromfile(z_path,dtype='<u4').reshape(272,480)
        check(np.all(rgba[:,:,3]==255),'GPU alpha write mask differs');Image.fromarray(rgba).save(out/(stem+'.png'));records[stem]=(rgba,owner,depth)
    check(len(records)==13 and len(actual['actual_state_checks'])==12,'GPU capture/state-readback scope differs')
    for state in actual['actual_state_checks']:
        flag=state['flags'];check(state['cull']==(3 if flag&4 else 1)and state['front_ccw']==int(not(flag&16384))and state['depth_clip']==int(not(flag&64)),'Actual raster readback differs')
        check(state['filter']==21 and state['address_u']==(3 if flag&256 else 1)and state['address_v']==(3 if flag&512 else 1)and state['max_lod']==0,'Actual sampler readback differs')
    for sample in range(3):
        ge,prod,previous,no_texture=[records['sample_%d_%s'%(sample,k)]for k in ('ge','runtime','previous','no_texture')]
        check(all(a.tobytes()==b.tobytes()for a,b in zip(ge,prod)),'Actual GE-vs-production framebuffers differ')
        check(np.any(prod[1])and not np.any(previous[1])and not np.any(previous[0][:,:,:3]),'Previous-color intervention did not remove the selected effect')
        check(all(not np.any(x[2])for x in (ge,prod,previous,no_texture)),'Original no-depth-write effect modified main depth/stencil')
        check(np.array_equal(prod[1],no_texture[1])and np.any(prod[0]!=no_texture[0]),'Texture intervention changed geometry/alpha coverage or had no RGB effect')
        changed=np.any(prod[0][:,:,:3]!=previous[0][:,:,:3],axis=2);check(np.all(prod[1][changed]>0),'Palette RGB changed outside drawn owner coverage')
        pixel_checks.append(dict(sample=sample,owner_pixels=int(np.count_nonzero(prod[1])),RGB_pixels=int(np.count_nonzero(np.any(prod[0][:,:,:3],axis=2))),
                                 texture_RGB_delta_pixels=int(np.count_nonzero(np.any(prod[0][:,:,:3]!=no_texture[0][:,:,:3],axis=2)))))
    rgb,owner,depth=records['additive_calibration'];check(np.any(owner)and np.all(rgb[owner>0,:3]==[128,255,255])and np.any(depth),'Actual additive/double-alpha calibration differs')
    report=dict(schema='native-GPU-original-palette-proof/v1',passed=True,request=dict(file=str((out/'request.json').resolve()),sha256=sha(out/'request.json')),
                actual_adapter=actual['adapter'],actual_pid=actual['pid'],frames=frames,pixel_checks=pixel_checks,bindings=bindings,
                captures=13,source_state_draws=24,actual_GPU_vertices=total_vertices,all_GE_and_production_framebuffers_bytes_equal=True,
                actual_UE_module_executed=False,PSP_final_pixel_equivalence=False,default_M1_binding_replaced=False,
                limits=['Native D3D11 GE-input and production paths share the validated source-state renderer; this is not original PSP framebuffer ground truth.',
                        'Rendering isolates the selected effect on black. Source geometry/matrices/CLUT/blend states are retained, but scene occlusion and full game composition are not validated.',
                        'Projection uses original matrices and passes the0.01 PSP-pixel bound. Full PSP fixed-point rasterization/D16 equivalence remains outside this reference.'])
    (out/'independent_verification.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    options='<option value="runtime">新运行时</option><option value="ge">原 GE 输入重现</option><option value="previous">改写前颜色对照</option><option value="no_texture">不使用贴图对照</option>'
    html='''<!doctype html><meta charset="utf-8"><title>原版武器特效 GPU 验证</title><style>body{background:#191919;color:#ddd;font:16px system-ui;max-width:1020px;margin:30px auto}select{padding:8px;margin:8px}img{width:960px;max-width:100%;image-rendering:pixelated;background:black}p{line-height:1.6}</style><h1>原版武器特效 GPU 验证</h1><p>独立特效验证；480×272 原矩阵与材质，尚非完整 M1 或高清美术。改写前颜色对照保持相同当前矩阵与 UV。</p><select id="frame"><option value="0">记录 1</option><option value="1">记录 2</option><option value="2">记录 3</option></select><select id="mode">'''+options+'''</select><img id="view"><script>const f=document.querySelector('#frame'),m=document.querySelector('#mode'),v=document.querySelector('#view');function update(){v.src=`sample_${f.value}_${m.value}.png`}f.onchange=m.onchange=update;update();</script>'''
    (out/'PREVIEW.html').write_text(html,encoding='utf-8')
    print(json.dumps(dict(passed=True,captures=13,GPU_vertices=total_vertices,pixel_checks=pixel_checks,max_projection_error=max(f['max_projection_error_PSP_pixels']for f in frames))))


if __name__=='__main__':main()
