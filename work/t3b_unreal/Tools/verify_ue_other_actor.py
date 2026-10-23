"""Audit actual UE same-capture creature geometry, source texture and GPU images."""
import argparse,hashlib,json
from pathlib import Path
import numpy as np
from PIL import Image,ImageDraw


def check(v,msg):
    if not v:raise ValueError(msg)
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def read(p):return json.loads(p.read_text(encoding='utf-8'))
def file(row):
    p=Path(row['file']);check(sha(p)==row['sha256'],'Changed evidence: '+str(p));return p
def image(row):return np.array(Image.open(file(row)).convert('RGBA'))
def identity(t):return t==dict(translation=[0.,0.,0.],scale=[1.,1.,1.],quaternion=[0.,0.,0.,1.])


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--run',type=Path,required=True);a=p.parse_args()
    folder=a.run;dest=folder/'independent_other_actor_verification.json';check(not dest.exists(),'Never replace completed actor audit')
    project=Path(__file__).resolve().parents[1]
    r=read(folder/'ue_weapon_ge_paired.json');req=read(folder/'request.json');start=read(folder/'process_started.json');done=read(folder/'process_completed.json')
    check(r['passed']and done['exit_code']==0 and r['process_id']==start['pid']==done['pid'],'UE process identity failed')
    check(r['run_id']==req['run_id']==start['run_id']and r['script_sha256']==req['script_sha256']==sha(folder/'capture_weapon_ge_paired_executed.py'),'Executed acquisition identity differs')
    actor=r['other_actor'];check(sha(file(req['other_actor_helper']))==actor['helper_sha256'],'Executed helper differs')
    proof=read(file(req['other_actor_runtime']));check(file(req['other_actor_runtime'])==file(actor['runtime_proof']),'Actor runtime proof differs')
    source=read(file(actor['input']));check(file(actor['input'])==file(proof['input_manifest']),'Evaluated actor manifest differs')
    check(proof['passed']and proof['all_transform_color_bytes_equal']and proof['all_uv_bytes_equal'],'Production skin/light not verified')
    native_folder=project/'Validation/observed_ge_scene_runs/f99ea978f2644fe3aa63b5af15c39251'
    native_audit=read(native_folder/'independent_verification.json');native=read(file(read(native_folder/'request.json')['inputs']))
    check(native_audit['passed']and native_audit['additional_original_actor_included']and file(native['other_actor_proof'])==file(actor['runtime_proof']),'Original GE source inputs were not independently validated')
    comparison=read(file(proof['comparison']));official=Path(proof['comparison']['file']).parent/'official_outputs.bin'
    check(sha(official)==comparison['official_output_sha256']and official.read_bytes()==file(proof['runtime_output']).read_bytes(),'Source transform/light output differs from pinned software reference')
    for s in proof['sources']:file(s)
    for row in r['protected_packages_before']:file(row)
    check(r['all_original_packages_unchanged']and r['new_packages']==[actor['created_material_package']],'Unexpected package changes')
    package=file(actor['created_material_package']);expected=project/'Content/T3B/NativeCandidates/OtherActorGEPaired'/('Run_'+r['run_id'])/'M_Creature_SourceCull.uasset'
    check(package.resolve()==expected.resolve(),'New asset is not the isolated source-cull candidate')
    check(actor['material']['two_sided']is False and 'TRANSLUCENT'in actor['material']['blend_mode']and 'UNLIT'in actor['material']['shading_model'],'Actual source cull/blend/unlit material differs')
    source_dtype=np.dtype([('position','<f4',3),('normal','<f4',3),('color','u1',4),('secondary','u1',3),('pad','u1')])
    actual_dtype=np.dtype([('position','<f8',3),('color','<f4',4),('normal','<f4',3)])
    original=np.fromfile(file(proof['runtime_output']),dtype=source_dtype);uv_source=file(proof['runtime_uv']).read_bytes()
    actual=file(actor['components']).read_bytes();indices=file(actor['indices']).read_bytes();uv=file(actor['uv']).read_bytes()
    origin=np.array(r['fixed_shared_PSP_world_origin']);units=r['metres_per_PSP_world_unit']
    weapon=read(file(r['input']));check(source['captures']==weapon['captures']and len(actor['frames'])==len(r['samples'])==12,'Actor/scene time pairing differs')
    material_id=next(iter(source['materials']));rgba=image(source['materials'][material_id]['png'])
    check(actor['texture']['srgb']is False and actor['texture']['source_rgba_sha256']==material_id and np.array_equal(image(actor['texture']),rgba),'Actual Texture2D Source RGBA differs from same-draw original CLUT')
    old_folder=project/'Validation/paired_street_series_ue_runs/f13b293ea4de4f258b16b4d7250f9339';baseline=read(old_folder/'ue_weapon_ge_paired.json')
    check(read(old_folder/'independent_street_series_verification.json')['passed'],'Baseline scene not verified')
    check(read(folder/'independent_camera_verification.json')['passed']and read(folder/'independent_street_series_verification.json')['passed'],'Base geometry/camera/scene audits missing')
    at=ix_at=uv_at=checked=0;frames=[];pictures=[]
    for i,(f,e,entry)in enumerate(zip(source['frames'],actor['frames'],r['samples'])):
        check(f['sample']==e['sample']==entry['sample']==i and f['capture']==e['capture']==entry['capture'],'Actor source sample differs')
        src=source['draws'][f['first_draw']:f['first_draw']+28];check(len(e['draws'])==28,'Missing actor packet')
        for d,q in zip(src,e['draws']):
            n=d['vertex_count'];first=d['first_output_vertex'];v=original[first:first+n]
            actual_rows=np.frombuffer(actual,dtype=actual_dtype,count=n,offset=q['readback_byte_offset'])
            expected=((v['position'].astype(float)-origin)*units*100)[:,[0,2,1]]
            check(actual_rows['position'].tobytes()==expected.astype('<f8').tobytes(),'Actual component world positions differ from original GE reconstruction')
            check(actual_rows['normal'].tobytes()==np.ascontiguousarray(v['normal'][:,[0,2,1]]).tobytes(),'Actual original normals differ')
            check(actual_rows['color'].tobytes()==(v['color'].astype(float)/255).astype('<f4').tobytes(),'Actual source primary color bits differ')
            check(not np.any(v['secondary']),'Secondary specular cannot be silently dropped')
            check((q['readback_byte_offset'],q['index_byte_offset'],q['uv_byte_offset'])==(at,ix_at,uv_at),'Actor stream overlaps or skips data')
            check(uv[uv_at:uv_at+n*8]==uv_source[first*8:(first+n)*8],'Actual original UV bits differ')
            check(indices[ix_at:ix_at+n*4]==np.arange(n,dtype='<u4').tobytes(),'Original triangle order/multiplicity differs')
            check(q['packet']==d['packet']and q['vertices']==n and q['actual_sort_priority']==-100+d['packet']and q['material_asset']==actor['material']['asset']and identity(q['component_transform']),'Component identity/material/order differs')
            at+=n*52;ix_at+=n*4;uv_at+=n*8;checked+=n
        current=entry['views']['original']['images'];prior=baseline['samples'][i]['views']['original']['images']
        for name in ('body_only','weapon_only','combined','street_only','street_with_aya_weapon'):
            check(np.array_equal(image(current[name]),image(prior[name])),'Hidden creature changed baseline control: '+name)
        only=image(current['other_actor_only']);all_actors=image(current['street_with_all_original_actors']);previous=image(current['street_with_aya_weapon'])
        visible=int(np.any(only[:,:,:3]>1,axis=2).sum());changed=int(np.any(np.abs(all_actors[:,:,:3].astype('i2')-previous[:,:,:3].astype('i2'))>1,axis=2).sum())
        check(only.shape==all_actors.shape==(272,480,4)and visible>100 and changed>100,'Creature is missing from actual GPU output')
        frames.append(dict(sample=i,draws=28,vertices=1800,creature_only_visible_pixels=visible,combined_changed_pixels=changed));pictures.append(all_actors)
    check(checked==21600 and(at,ix_at,uv_at)==(len(actual),len(indices),len(uv)),'Incomplete component coverage/trailing data')
    sheet=Image.new('RGB',(1440,1200),(22,22,22));draw=ImageDraw.Draw(sheet)
    for i,im in enumerate(pictures):
        x=i%3*480;y=i//3*300;sheet.paste(Image.fromarray(im).convert('RGB'),(x,y+28));draw.text((x+8,y+6),f'UE sample{i}: original creature / Aya / gun / street',fill='white')
    sheet.save(folder/'OTHER_ACTOR_CONTACT_SHEET.png')
    report=dict(schema='t3b-same-capture-creature-UE-audit/v1',passed=True,pid=r['process_id'],engine_version=r['engine_version'],frames=frames,
        actor_component_vertices_checked=checked,draws=336,Texture2D_Source_RGBA_exact=True,all_60_baseline_control_images_pixel_identical=True,
        source_GPU_audit_sha256=sha(native_folder/'independent_verification.json'),original_packages_unchanged=len(r['protected_packages_before']),new_packages=1,
        original_clock_verified=False,UE_GE_ordered_cpp_pass_executed=False,source_main_depth_blend_equivalence=False,formal_M1_replaced=False,
        limits=['Actual UE component readbacks are CPU data; camera markers separately verify GPU projection.',
                'Ordinary translucent materials still differ from original per-draw main-depth writes/fog/stencil; full game and HD materials are unfinished.'])
    dest.write_text(json.dumps(report,indent=2),encoding='utf-8');print(json.dumps({k:report[k]for k in ('passed','actor_component_vertices_checked','draws','Texture2D_Source_RGBA_exact')}))


if __name__=='__main__':main()
