"""Independently inspect GPU Map output and analytic blend/depth controls."""
import argparse,hashlib,json,struct
from pathlib import Path
import numpy as np
from PIL import Image


def check(ok,reason):
    if not ok:raise ValueError(reason)
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def js(p):return json.loads(p.read_text(encoding='utf-8'))


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--run',type=Path,required=True);a=p.parse_args()
    dest=a.run/'root_independent_verification.json';check(not dest.exists(),'Never replace prior audit')
    request=js(a.run/'request.json');actual=js(a.run/'actual_gpu_report.json');done=js(a.run/'process_completed.json')
    started=js(a.run/'process_started.json')
    check(actual['passed']and done['exit_code']==0 and actual['pid']==done['pid']==started['pid'],'Actual GPU process identity differs')
    check(started['run_id']==request['run_id']and actual['width']==512 and actual['height']==768,'Run/dimensions mismatch')
    for row in request['sources']:check(sha(Path(row['file']))==row['sha256'],'Frozen executed source changed')
    check(sha(a.run/'ge_depth_reference.exe')==request['executable_sha256'],'Executed probe changed')
    bundle=Path(request['bundle']['file']);check(sha(bundle)==request['bundle']['sha256'],'GPU input bundle changed')
    for row in request['textures']:
        check(sha(Path(row['source']))==row['sha256'],'Original decoded texture changed')
        gpu=(a.run/('texture_'+str(row['index'])+'_actual.rgba')).read_bytes()
        check(hashlib.sha256(gpu).hexdigest()==row['rgba_sha256'],'Actual GPU texture readback differs from original RGBA')
    raw=bundle.read_bytes();check(raw[:8]==b'T3BGPU1\0'and struct.unpack_from('<4I',raw,8)==(512,768,12,2),'Bundle header differs')
    offset=24
    for row in request['textures']:
        w,h=struct.unpack_from('<2I',raw,offset);offset+=8
        check((w,h)==(row['width'],row['height']),'Texture dimensions differ')
        tex=raw[offset:offset+w*h*4];offset+=w*h*4
        check(hashlib.sha256(tex).hexdigest()==row['rgba_sha256'],'Bundle texture bytes differ')
    # Check actual serialized draw order, ownership IDs and vertex input hashes.
    for frame in request['frames']:
        sample,count=struct.unpack_from('<2I',raw,offset);offset+=8
        check(sample==frame['sample']and count==107,'Sample boundary differs')
        for i,d in enumerate(frame['draws']):
            actor,ordinal,n=struct.unpack_from('<3I',raw,offset);offset+=12
            check(ordinal==i and n==d['vertices']and actor==(0 if d['actor']=='body'else 1),'Serialized draw order differs')
            vertex=raw[offset:offset+n*36];offset+=n*36
            check(hashlib.sha256(vertex).hexdigest()==d['vertex_sha256'],'Submitted vertex inputs changed')
    check(offset==len(raw),'Trailing GPU bundle')
    images={};files=[]
    for c in actual['captures']:
        stem=c['stem'];rgb=a.run/(stem+'.rgba');owner=a.run/(stem+'.owner_u32');depth=a.run/(stem+'.depth_f32')
        check(all(p.stat().st_size==512*768*4 for p in(rgb,owner,depth)),'Incomplete actual GPU readback extent')
        rgba=np.frombuffer(rgb.read_bytes(),dtype='u1').reshape(768,512,4)
        ids=np.frombuffer(owner.read_bytes(),dtype='<u4').reshape(768,512)
        z=np.frombuffer(depth.read_bytes(),dtype='<f4').reshape(768,512)
        check(np.isfinite(z).all()and np.min(z)>=0 and np.max(z)<=1,'Invalid D32 readback')
        check(np.max(ids)<=c['draws']and np.any(ids),'Owner MRT invalid or empty')
        if c['depth_write']:
            check(np.array_equal(z>0,ids>0),'Source-depth writes do not match passing-fragment owner coverage')
        else:check(np.all(z==0),'No-write control unexpectedly changed depth')
        png=a.run/(stem+'.png');check(not png.exists(),'Never replace actual readback PNG')
        Image.frombytes('RGBA',(512,768),rgba.tobytes()).save(png)
        files.append(dict(stem=stem,rgba_sha256=sha(rgb),owner_sha256=sha(owner),depth_sha256=sha(depth),png_sha256=sha(png)))
        images[stem]=(c,rgba,ids,z)
    check(len(images)==52,'Incomplete original plus analytic capture count')
    expected={
        'synthetic_near_then_far_depth_on':([128,0,0,255],1,.8),
        'synthetic_near_then_far_depth_off':([64,0,128,255],2,0.),
        'synthetic_far_then_near_depth_on':([128,0,64,255],2,.8),
        'synthetic_far_then_near_depth_off':([128,0,64,255],2,0.),
    }
    controls=[]
    for name,(color,owner,z)in expected.items():
        c,rgba,ids,depth=images[name];check(c['synthetic'],'Analytic control confused with original capture')
        observed=rgba[384,256].tolist()
        check(observed==color and int(ids[384,256])==owner and abs(float(depth[384,256])-z)<1e-7,'Analytic alpha/depth/order control failed: '+name)
        controls.append(dict(case=name,actual_rgba=observed,expected_rgba=color,actual_owner=int(ids[384,256]),actual_depth=float(depth[384,256])))
    interventions=[]
    for frame in request['frames']:
        weapon_ids=[d['owner_id']for d in frame['draws']if d['actor']=='weapon'];check(len(weapon_ids)==1,'Weapon owner identity missing')
        weapon_id=weapon_ids[0]
        for view in('positive_y','negative_y'):
            stem='sample_'+str(frame['sample'])+'_'+view+'_'
            _,off,off_ids,off_z=images[stem+'no_depth_write'];_,on,on_ids,on_z=images[stem+'source_depth']
            check(np.array_equal(off_ids>0,on_ids>0),'Depth intervention changed union raster/alpha coverage')
            pixel_changes=int(np.any(off[:,:,:3]!=on[:,:,:3],axis=2).sum());owner_changes=int((off_ids!=on_ids).sum())
            check(pixel_changes>0 and owner_changes>0,'Depth intervention did not change actual overlapping model pixels')
            interventions.append(dict(sample=frame['sample'],view=view,changed_RGB_pixels=pixel_changes,
                                      changed_draw_owner_pixels=owner_changes,covered_pixels=int((on_ids>0).sum()),
                                      weapon_final_owner_pixels_without_depth=int((off_ids==weapon_id).sum()),
                                      weapon_final_owner_pixels_with_depth=int((on_ids==weapon_id).sum()),
                                      depth_written_pixels=int((on_z>0).sum())))
    result=dict(schema='ge-original-depth-gpu-intervention-root-audit/v1',passed=True,run_id=request['run_id'],
                request_sha256=sha(a.run/'request.json'),actual_gpu_report_sha256=sha(a.run/'actual_gpu_report.json'),
                process_id=actual['pid'],adapter=actual['adapter'],feature_level=actual['feature_level'],
                depth_format=actual['depth_format'],actual_hardware_captures=52,original_geometry_interventions=24,
                analytic_controls=controls,actual_texture_bytes_exact=True,unchanged_union_coverage_in_all_interventions=True,
                interventions=interventions,files=files,UE_module_replaced=False,original_PSP_pixels_verified=False,
                original_camera_verified=False,original_depth_quantization_verified=False,original_fog_verified=False,
                conclusion='On an owned D3D11 device, original-model alpha blending with main depth writes changes actual occlusion while retaining fractional alpha. Correct sequential blending remains order-dependent.',
                limits=['Controlled +/-Y orthographic calibration; not the original camera or PSP rasterizer.',
                        'D32 depth, D3D11 interpolation/UNORM arithmetic, no original fog/stencil/output color acceptance.',
                        'Nearest-only depth prepass is not equivalent to original sequential depth-writing alpha blend.',
                        'GPU owner is final passing draw, not a complete contribution history for blended pixels.',
                        'This is an independent native GPU reference, not a repaired UE renderer or playable M1.'])
    dest.write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(dict(passed=True,adapter=actual['adapter'],captures=52,analytical_controls=4,
                         original_geometry_interventions=24,changed_RGB_pixels=sum(x['changed_RGB_pixels']for x in interventions),
                         changed_owner_pixels=sum(x['changed_draw_owner_pixels']for x in interventions))))


if __name__=='__main__':main()
