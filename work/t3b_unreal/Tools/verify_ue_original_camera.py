"""Independent original-camera UE property, geometry and raster-marker audit."""
import argparse
import hashlib
import json
from pathlib import Path
import numpy as np
from PIL import Image,ImageDraw


def check(v,msg):
    if not v:raise ValueError(msg)
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def read(p):return json.loads(p.read_text(encoding='utf-8'))
def file(row):
    p=Path(row['file']);check(sha(p)==row['sha256'],'Recorded file changed: '+str(p));return p
def pixels(row):return np.array(Image.open(file(row)).convert('RGBA'))
def identity(t):return t==dict(translation=[0.,0.,0.],scale=[1.,1.,1.],quaternion=[0.,0.,0.,1.])
def f24(values):return (np.array(values,dtype='<u4')<<8).view('<f4').astype(float)


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--run',type=Path,required=True);a=p.parse_args()
    folder=a.run;out=folder/'independent_camera_verification.json';check(not out.exists(),'Refuse audit overwrite')
    r=read(folder/'ue_weapon_ge_paired.json');request=read(folder/'request.json')
    done=read(folder/'process_completed.json');started=read(folder/'process_started.json')
    check(r['passed']and done['exit_code']==0 and r['process_id']==done['pid']==started['pid'],'Acquisition/process identity failed')
    check(request['run_id']==r['run_id']==started['run_id'],'Run identity failed')
    check(sha(folder/'capture_weapon_ge_paired_executed.py')==r['script_sha256']==request['script_sha256'],'Executed producer identity failed')
    helper=file(request['camera_helper']);check(sha(helper)==r['source_camera']['helper_sha256'],'Executed camera adapter identity differs')
    fixture=read(file(request['cameras']));check(r['source_camera']['sha256']==request['cameras']['sha256'],'Camera identity differs')
    wm=read(file(r['input']));bm=read(file(r['body_input']))
    sources={};actual={};uv={}
    dtype=np.dtype([('position','<f4',3),('normal','<f4',3),('color','u1',4),('secondary','u1',3),('pad','u1')])
    component_dtype=np.dtype([('position','<f8',3),('color','<f4',4),('normal','<f4',3)])
    for name in ('body','weapon'):
        proof=read(file(r['runtime_proofs'][name]));check(proof['passed']and proof['all_transform_color_bytes_equal'],'Unverified source positions')
        for s in proof['sources']:file(s)
        raw=file(proof['runtime_output']).read_bytes();comparison=read(file(proof['comparison']))
        official=Path(proof['comparison']['file']).parent/'official_outputs.bin'
        check(sha(official)==comparison['official_output_sha256']and official.read_bytes()==raw,'World output differs from pinned PPSSPP reference')
        sources[name]=np.frombuffer(raw,dtype=dtype);uv[name]=file(proof['runtime_uv']).read_bytes()
        actual[name]=file(r['readbacks'][name]).read_bytes()
    check(len(r['samples'])==len(fixture['frames'])==12,'Incomplete actual UE source-camera samples')
    check(r['all_original_packages_unchanged']and r['new_packages']==([r['other_actor']['created_material_package']]if request.get('other_actor_runtime')else[]),'Source packages modified')
    for row in r['protected_packages_before']:file(row)
    for row in r['new_packages']:file(row)
    check(r['render_settings']['width']==480 and r['render_settings']['height']==272,'Unexpected image extent')
    origin=np.array(fixture['fixed_shared_PSP_world_origin']);units=fixture['metres_per_PSP_world_unit']*100
    inverse_source=np.array([[1/units,0,0,0],[0,0,1/units,0],[0,1/units,0,0],[*origin,1]])
    swap=np.array([[0,0,1,0],[1,0,0,0],[0,1,0,0],[0,0,0,1]])
    checked=0;results=[];combinations=[]
    for entry,frame,cam in zip(r['samples'],wm['frames'],fixture['frames']):
        i=frame['sample'];check(entry['sample']==cam['sample']==i and entry['capture']==frame['capture']==cam['capture']['key'],'Sample pairing differs')
        check(sha(Path(cam['capture']['path']))==cam['capture']['sha256'],'Original PPDMP changed')
        for name,count,start in [('body',3456,frame['paired_body_first_vertex']),('weapon',243,frame['first_output_vertex'])]:
            info=entry['actors'][name];check(info['vertices']==count and identity(info['actor_transform'])and identity(info['component_transform']),'Actual geometry actor changed')
            raw=sources[name][start:start+count]
            points=(raw['position'].astype(float)-origin)*(units/100)*100;points=np.ascontiguousarray(points[:,[0,2,1]])
            data=np.frombuffer(actual[name],dtype=component_dtype,count=count,offset=info['readback_byte_offset'])
            check(data['position'].tobytes()==points.tobytes(),'Actual component position bits differ')
            check(data['color'].tobytes()==(raw['color'].astype(float)/255).astype('<f4').tobytes(),'Actual component colors differ')
            check(data['normal'].tobytes()==np.ascontiguousarray(raw['normal'][:,[0,2,1]]).tobytes(),'Actual component normals differ')
            if 'topology_uv'in info:
                check(file(info['topology_uv']['indices']).read_bytes()==np.arange(count,dtype='<u4').tobytes(),'Original triangle order changed')
                check(file(info['topology_uv']['uv']).read_bytes()==uv[name][start*8:(start+count)*8],'Original UV changed')
            if name=='body':body_points=data['position'].copy()
            checked+=count
        e=entry['views']['original'];record=e['original_camera'];world=np.array(record['camera_component_world_matrix'])
        transform=e['camera_component_transform'];check(transform['scale']==[1.,1.,1.],'Camera scale is not unit')
        x,y,z,w=transform['quaternion']
        rotation=np.array([[1-2*(y*y+z*z),2*(x*y-z*w),2*(x*z+y*w)],
                           [2*(x*y+z*w),1-2*(x*x+z*z),2*(y*z-x*w)],
                           [2*(x*z-y*w),2*(y*z+x*w),1-2*(x*x+y*y)]])
        check(np.max(np.abs(world[:3,:3]-rotation.T))<1e-12 and np.array_equal(world[3,:3],transform['translation']),'Camera Matrix differs from component quaternion/location')
        view=np.linalg.inv(world)@swap;projection=np.array(record['actual_custom_projection_matrix'])
        view_original=np.eye(4);view_original[:,:3]=f24(cam['view_payload']).reshape(4,3)
        proj_original=f24(cam['projection_payload']).reshape(4,4)
        target=inverse_source@view_original@proj_original@np.array(cam['clip_remap_row_major'])
        check(record['actual_use_custom_projection']is True,'Custom projection is disabled')
        check(np.max(np.abs(view@projection*record['homogeneous_normalization']-target))<1e-10,'UE camera/custom projection does not compose to original camera')
        # GPU marker image only contains six opaque, unlit coloured quads at original body vertices.
        control=e['marker_control'];check(control['synthetic_control']and control['material_opaque']and control['material_unlit'],'Marker control must be isolated')
        marker=pixels(control['image']);check(marker.shape==(272,480,4),'Marker image dimensions differ')
        rgb=marker[:,:,:3].astype(float);maximum=rgb.max(axis=2);bits=rgb>maximum[:,:,None]*.6
        marker_errors=[]
        for point in control['points']:
            index=point['body_vertex_index'];position=body_points[index]
            check(np.array_equal(position,point['world_position']),'Control is not located at the claimed actual body vertex')
            clip=np.r_[position,1.]@target;expected=np.array([(clip[0]/clip[3]+1)*240,(1-clip[1]/clip[3])*136])
            mask=(maximum>40)&np.all(bits==np.array(point['rgb'],dtype=bool),axis=2)
            yy,xx=np.nonzero(mask);check(len(xx)>2,'Marker colour missing from actual GPU image')
            observed=np.array([xx.mean()+.5,yy.mean()+.5]);error=float(np.linalg.norm(observed-expected))
            check(error<=1.,f'Actual GPU marker differs by >1 PSP pixel: sample={i}, RGB={point["rgb"]}, error={error}')
            marker_errors.append(dict(body_vertex_index=index,rgb=point['rgb'],expected_pixel=expected.tolist(),
                                      actual_pixel_centroid=observed.tolist(),error_pixels=error,mask_pixels=len(xx)))
        images={name:pixels(row)for name,row in e['images'].items()}
        check(all(im.shape==(272,480,4)for im in images.values()),'Rendered dimensions differ')
        for name in ('body_only','weapon_only','combined'):check(np.any(images[name][:,:,:3]>1),'Empty rendered geometry: '+name)
        if i==0:
            hidden=images['hidden'][:,:,:3]
            check(np.max(hidden)<=1 and np.all(hidden==hidden[:,:,:1]),'Hidden control has geometry/colour beyond grayscale 1-LSB noise')
        combinations.append(images['combined'])
        results.append(dict(sample=i,marker_checks=marker_errors,
            max_marker_error_pixels=max(m['error_pixels']for m in marker_errors),
            camera_property_composition_max_error=float(np.max(np.abs(view@projection*record['homogeneous_normalization']-target)))))
    check(checked==44388,'Incomplete geometry checks')
    sheet=Image.new('RGB',(1440,1200),(22,22,22));draw=ImageDraw.Draw(sheet)
    for i,im in enumerate(combinations):
        x=(i%3)*480;y=(i//3)*300;sheet.paste(Image.fromarray(im).convert('RGB'),(x,y+28));draw.text((x+8,y+6),f'UE source camera - sample {i}',fill='white')
    check(not(folder/'CONTACT_SHEET.png').exists(),'Contact sheet already exists');sheet.save(folder/'CONTACT_SHEET.png')
    result=dict(schema='t3b-original-camera-UE-raster-audit/v1',passed=True,engine_version=r['engine_version'],pid=r['process_id'],
        sample_count=12,component_vertices_checked=checked,actual_GPU_marker_checks=72,
        max_marker_centroid_error_PSP_pixels=max(x['max_marker_error_pixels']for x in results),
        marker_acceptance_PSP_pixels=1.,samples=results,
        original_packages_unchanged=len(r['protected_packages_before']),new_packages=len(r['new_packages']),
        UE_GE_ordered_cpp_pass_executed=False,original_depth_blending_equivalence=False,
        original_final_pixel_equivalence=False,original_timing_verified=False,formal_M1_replaced=False)
    out.write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps({k:result[k]for k in ('passed','sample_count','actual_GPU_marker_checks','max_marker_centroid_error_PSP_pixels')}))


if __name__=='__main__':main()
