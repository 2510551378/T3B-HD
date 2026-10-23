"""Audit source-world -> recorded GE camera versus actual GPU stream output."""
import argparse
import hashlib
import json
from pathlib import Path
import struct
import numpy as np
from PIL import Image, ImageDraw


def check(v,msg):
    if not v:raise ValueError(msg)
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def read(p):return json.loads(p.read_text(encoding='utf-8'))
def identity(row):
    p=Path(row['file']);check(sha(p)==row['sha256'],'Changed evidence: '+str(p));return p
def f24(payload):return np.array(payload,dtype='<u4').__lshift__(8).view('<f4').astype(np.float64)


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--run',type=Path,required=True)
    p.add_argument('--report-name',default='independent_verification.json');a=p.parse_args()
    check(Path(a.report_name).name==a.report_name,'Report name must be a filename')
    out=a.run;report_file=out/a.report_name;check(not report_file.exists(),'Never replace completed audit')
    request=read(out/'request.json');gpu=read(out/'actual_gpu_report.json')
    done=read(out/'completed.json');started=read(out/'started.json')
    check(done['exit_code']==request['build_exit_code']==0 and done['pid']==started['pid']==gpu['pid'],'Process/build identity differs')
    check(gpu['width']==480 and gpu['height']==272 and not gpu['UE_executed'],'Wrong render scope')
    for row in request['sources']:identity(row)
    identity(request['shader']);check(sha(Path(request['run_command'][0]))==request['executable_sha256'],'EXE changed')
    cameras=read(identity(request['cameras']));camraw=identity(request['camera_binary']).read_bytes()
    check(camraw[:8]==b'T3BCAM1\0' and struct.unpack_from('<3I',camraw,8)==(480,272,12),'Camera header differs')
    check(len(camraw)==836,'Camera binary extent differs')
    source_request=read(identity(cameras['geometry_request']))
    body=read(identity(cameras['body_input']));weapon=read(identity(cameras['weapon_input']))
    source_binary=[identity(m['binary']).read_bytes() for m in (body,weapon)]
    dtype=np.dtype([('position','<f4',3),('normal','<f4',3),('color','u1',4),('secondary','u1',3),('pad','u1')])
    outputs=[]
    for row in source_request['runtime_proofs']:
        proof=read(identity(row));check(proof['passed'],'Production world positions unverified')
        outputs.append(np.fromfile(identity(proof['runtime_output']),dtype=dtype))
        comparison=read(Path(proof['comparison']['file']))
        official=Path(proof['comparison']['file']).parent/'official_outputs.bin'
        check(sha(official)==comparison['official_output_sha256'] and
              official.read_bytes()==Path(proof['runtime_output']['file']).read_bytes(),'World-position reference mismatch')
    origin=np.array(source_request['fixed_shared_PSP_world_origin']);units=source_request['metres_per_PSP_world_unit']
    raw=identity(request['geometry_bundle']).read_bytes();check(raw[:8]==b'T3BGPU1\0','Geometry magic differs')
    check(struct.unpack_from('<4I',raw,8)==(512,768,12,2),'Geometry scope differs');at=24
    for i,t in enumerate(source_request['textures']):
        w,h=struct.unpack_from('<2I',raw,at);at+=8;tex=raw[at:at+w*h*4];at+=w*h*4
        check(hashlib.sha256(tex).hexdigest()==t['rgba_sha256'],'Original texture bundle differs')
        check((out/f'texture_{i}_actual.rgba').read_bytes()==tex,'Actual GPU atlas readback differs')
    matrix_rows=[]
    for i,frame in enumerate(source_request['frames']):
        cam=cameras['frames'][i];check(cam['sample']==i,'Camera sample mismatch')
        check(sha(Path(cam['capture']['path']))==cam['capture']['sha256'],'PPDMP changed')
        sample,n=struct.unpack_from('<2I',raw,at);at+=8;check(sample==i and n==107,'Geometry sample mismatch')
        bf=body['frames'][weapon['frames'][i]['body_frame_index']]
        originals={(d['register_record'],d['register_word']):(0,d) for d in body['draws'][bf['first_draw']:bf['first_draw']+106]}
        wd=weapon['draws'][weapon['frames'][i]['first_draw']];originals[(wd['register_record'],wd['register_word'])]=(1,wd)
        vertices=[];source_world=[];source_registers=None
        for j,draw in enumerate(frame['draws']):
            actor,ordinal,count=struct.unpack_from('<3I',raw,at);at+=12
            check(ordinal==j and count==draw['vertices'],'Original draw order/count differs')
            data=raw[at:at+count*36];at+=count*36
            check(hashlib.sha256(data).hexdigest()==draw['vertex_sha256'],'Frozen vertex input differs')
            array=np.frombuffer(data,dtype='<f4').reshape(count,9);vertices.append(array)
            original_actor,d=originals[(draw['source_register_record'],draw['source_register_word'])]
            check(actor==original_actor and d['VIEW_payload']==cam['view_payload'] and
                  d['PROJECTION_payload']==cam['projection_payload'],'Source draw/camera pairing mismatch')
            regs=struct.unpack_from('<256I',source_binary[actor],d['binary_byte_offset'])
            keys=(0x15,0x16,0x1c,0x42,0x43,0x44,0x45,0x46,0x47,0x4c,0x4d,0xd4,0xd5,0xd6,0xd7)
            selected={k:regs[k]for k in keys}
            if source_registers is None:source_registers=selected
            check(selected==source_registers,'Per-draw original viewport changed')
            start=d['first_output_vertex'];points=outputs[actor]['position'][start:start+count].astype(np.float64)
            expected=(((points-origin)*units*100)[:,[0,2,1]]).astype('<f4')
            check(array[:,:3].tobytes()==expected.tobytes(),'GPU geometry does not match original source world transform')
            source_world.append(points)
        vertices=np.concatenate(vertices);points=np.concatenate(source_world);check(len(points)==3699,'Incomplete frame')
        actual=np.fromfile(out/f'sample_{i}.clip_uv_color_f32',dtype='<f4').reshape(3699,10)
        check(actual[:,4:].tobytes()==vertices[:,3:].tobytes(),'GPU changed original UV/primary color')
        id_in_binary=struct.unpack_from('<I',camraw,20+i*68)[0]
        matrix=np.frombuffer(camraw,dtype='<f4',count=16,offset=24+i*68).reshape(4,4)
        check(id_in_binary==i and matrix.tobytes()==np.array(cam['world_to_clip_row_major_f32'],dtype='<f4').tobytes(),'Matrix/sample upload mismatch')
        homogeneous=np.column_stack([vertices[:,:3].astype(float),np.ones(len(vertices))])
        merged_expected=homogeneous@matrix.astype(float)
        bound=8*np.finfo(np.float32).eps*(np.abs(homogeneous)@np.abs(matrix.astype(float)))
        check(np.all(np.abs(actual[:,:4]-merged_expected)<=bound),'GPU matrix evaluation exceeds float32 bound')
        # Independent original path: source world -> 3x4 VIEW -> 4x4 PROJ -> viewport.
        view=f24(cam['view_payload']).reshape(3,4,order='F')
        proj=f24(cam['projection_payload']).reshape(4,4,order='F')
        view_points=np.column_stack([points,np.ones(len(points))])@view.T
        clip=np.column_stack([view_points,np.ones(len(points))])@proj.T
        ndc=clip[:,:3]/clip[:,3,None]
        # Read actual frozen PRIM register payloads, not producer-derived viewport metadata.
        scale=f24([source_registers[k]for k in (0x42,0x43,0x44)])
        center=f24([source_registers[k]for k in (0x45,0x46,0x47)])
        offset=np.array([source_registers[k]&65535 for k in (0x4c,0x4d)])/16
        check(np.array_equal(scale,cam['viewport_scale']) and np.array_equal(center,cam['viewport_center']) and
              np.array_equal(offset,cam['offset_pixels']),'Producer viewport differs from original registers')
        check(source_registers[0x15]==source_registers[0xd4]==source_registers[0xd6]==0 and
              source_registers[0x16]==source_registers[0xd5]==0x43ddf and source_registers[0xd7]==65535 and
              source_registers[0x1c]==1,'Original region/scissor/depth-clamp differs')
        screen=ndc*scale+center;screen[:,:2]-=offset;screen[:,2]/=65535
        gpu_ndc=actual[:,:3].astype(float)/actual[:,3,None]
        gpu_screen=np.column_stack([(gpu_ndc[:,0]+1)*240,(1-gpu_ndc[:,1])*136,gpu_ndc[:,2]])
        pixel_error=np.abs(gpu_screen[:,:2]-screen[:,:2]);depth_error=np.abs(gpu_screen[:,2]-screen[:,2])
        check(np.isfinite(gpu_screen).all() and float(pixel_error.max())<.01,'Original-camera approximation exceeds 0.01 PSP pixel')
        check(np.all(clip[:,3]>0) and np.all(ndc[:,2]>-1) and np.all(ndc[:,2]<1),
              'Source depth clamp may affect selected geometry; current renderer insufficient')
        check(np.all(actual[:,3]>0) and np.all(gpu_ndc[:,2]>0) and np.all(gpu_ndc[:,2]<1),'GPU clip interval mismatch')
        matrix_rows.append(dict(sample=i,vertices=len(points),max_original_screen_error_pixels=float(pixel_error.max()),
            max_original_normalized_depth_error=float(depth_error.max()),
            source_clip_W_range=[float(clip[:,3].min()),float(clip[:,3].max())],
            source_depth_range=[float(screen[:,2].min()),float(screen[:,2].max())],
            source_depth_clamp_enabled=True,selected_geometry_strictly_inside_Z_clip=True,
            derived_vertical_fov_degrees=cam['derived_vertical_fov_degrees']))
    check(at==len(raw),'Trailing geometry')
    images={};files=[]
    check(len(gpu['captures'])==24,'Incomplete rendered capture set')
    for c in gpu['captures']:
        name=c['stem'];rgba_path=out/(name+'.rgba');id_path=out/(name+'.owner_u32');z_path=out/(name+'.depth_f32')
        rgba=np.fromfile(rgba_path,dtype='u1').reshape(272,480,4)
        ids=np.fromfile(id_path,dtype='<u4').reshape(272,480);z=np.fromfile(z_path,dtype='<f4').reshape(272,480)
        check(0<int(ids.max())<=107 and np.all(rgba[:,:,3]==255),'Missing coverage or incorrect color mask')
        check(np.isfinite(z).all() and np.all(z>=0) and np.all(z<=1),'Invalid GPU depth')
        check(np.array_equal(z>0,ids>0) if c['depth_write'] else np.all(z==0),'Depth write state/readback mismatch')
        png=out/(name+'.png')
        if png.exists():check(np.array_equal(np.array(Image.open(png).convert('RGBA')),rgba),'Existing PNG differs from actual GPU bytes')
        else:Image.fromarray(rgba).save(png)
        files.append(dict(stem=name,rgba_sha256=sha(rgba_path),owner_sha256=sha(id_path),depth_sha256=sha(z_path),png_sha256=sha(png)))
        images[(c['sample'],c['depth_write'])]=(rgba,ids,z)
    interventions=[]
    for i in range(12):
        off,off_ids,_=images[(i,False)];on,on_ids,z=images[(i,True)]
        check(np.array_equal(off_ids>0,on_ids>0),'Depth intervention changed union geometry coverage')
        gun=next(d['owner_id'] for d in source_request['frames'][i]['draws'] if d['actor']=='weapon')
        interventions.append(dict(sample=i,covered_pixels=int((on_ids>0).sum()),
            changed_RGB_pixels=int(np.any(on[:,:,:3]!=off[:,:,:3],axis=2).sum()),
            changed_owner_pixels=int((on_ids!=off_ids).sum()),weapon_final_owner_pixels=int((on_ids==gun).sum())))
    sheet=Image.new('RGB',(480*3,300*4),(22,22,22));draw=ImageDraw.Draw(sheet)
    for i in range(12):
        image=Image.fromarray(images[(i,True)][0]).convert('RGB');x=(i%3)*480;y=(i//3)*300
        sheet.paste(image,(x,y+28));draw.text((x+8,y+6),f'Sample {i}: source camera, depth write ON',fill='white')
    sheet_path=out/'CONTACT_SHEET.png'
    if sheet_path.exists():check(np.array_equal(np.array(Image.open(sheet_path).convert('RGB')),np.array(sheet)),'Existing contact sheet differs')
    else:sheet.save(sheet_path)
    result=dict(schema='t3b-original-camera-native-GPU-audit/v1',passed=True,pid=gpu['pid'],adapter=gpu['adapter'],
        source_camera_PRIMs=1284,actual_GPU_vertex_records=44388,rendered_captures=24,
        viewport_independently_read_from_original_PRIM_registers=True,
        max_original_screen_error_pixels=max(r['max_original_screen_error_pixels'] for r in matrix_rows),
        projection_error_acceptance_PSP_pixels=.01,frames=matrix_rows,depth_interventions=interventions,files=files,
        UE_executed=False,original_pixel_equivalence=False,original_timing_verified=False,
        limits=['Original geometry and camera under D3D11; not a full scene or original framebuffer reproduction.',
                'Depth clamp is enabled in source; all selected vertices and triangle interiors are within Z clip.',
                'No PSP fixed-point coverage/D16 depth/fog/tonemapping equivalence; 0.01 pixel checks are projections only.'])
    report_file.write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps({k:result[k] for k in ('passed','actual_GPU_vertex_records','rendered_captures','max_original_screen_error_pixels')}))


if __name__=='__main__':main()
