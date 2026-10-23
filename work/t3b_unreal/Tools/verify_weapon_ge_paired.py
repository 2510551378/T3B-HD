"""Audit same-dump weapon/body component data and actual UE image controls."""
import argparse,hashlib,json
from pathlib import Path
import numpy as np
from PIL import Image


def check(ok,reason):
    if not ok:raise ValueError(reason)
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def identity(t):return t==dict(translation=[0.,0.,0.],scale=[1.,1.,1.],quaternion=[0.,0.,0.,1.])
def verified_file(row):
    p=Path(row['file']);check(sha(p)==row['sha256'],'Recorded file changed: '+str(p));return p
def pixels(row):return np.asarray(Image.open(verified_file(row)).convert('RGBA'))


def main():
    p=argparse.ArgumentParser();p.add_argument('--report',type=Path,required=True);a=p.parse_args()
    out=a.report.parent/'root_independent_verification.json';check(not out.exists(),'Never replace prior audit')
    r=json.loads(a.report.read_text(encoding='utf-8'));check(r['passed'],'Actual acquisition failed')
    done=json.loads((a.report.parent/'process_completed.json').read_text(encoding='utf-8'))
    request=json.loads((a.report.parent/'request.json').read_text(encoding='utf-8'))
    check(done['pid']==r['process_id']and done['exit_code']==0 and request['run_id']==r['run_id'],'Actual process binding differs')
    check(sha(a.report.parent/'capture_weapon_ge_paired_executed.py')==r['script_sha256']==request['script_sha256'],'Executed source changed')
    wm=json.loads(verified_file(r['input']).read_text(encoding='utf-8'))
    bm=json.loads(verified_file(r['body_input']).read_text(encoding='utf-8'))
    check(wm['passed']and wm['same_GE_dump_pairing']and wm['original_camera_match'],'Unverified source pairing')
    for c in wm['captures']:check(sha(Path(c['path']))==c['sha256'],'Original shared GE dump changed')
    check(len(wm['frames'])==len(r['samples'])==12,'Incomplete actual paired sequence')
    for f,d in zip(wm['frames'],wm['draws']):
        bf=bm['frames'][f['body_frame_index']]
        check(f['capture']==bf['capture']==d['capture']and f['sample']==bf['sample']==d['sample'],'Body/weapon source sample differs')
        for bd in bm['draws'][bf['first_draw']:bf['first_draw']+106]:
            check(bd['VIEW_payload']==d['VIEW_payload']and bd['PROJECTION_payload']==d['PROJECTION_payload'],'Original cameras differ')

    source_dtype=np.dtype([('position','<f4',3),('normal','<f4',3),('color','u1',4),('secondary','u1',3),('pad','u1')])
    actual_dtype=np.dtype([('position','<f8',3),('color','<f4',4),('normal','<f4',3)])
    sources={};uvs={};readbacks={}
    for name in ('body','weapon'):
        proof=json.loads(verified_file(r['runtime_proofs'][name]).read_text(encoding='utf-8'))
        check(proof['passed']and proof['all_transform_color_bytes_equal'],'Production-core evaluation failed')
        for s in proof['sources']:check(sha(Path(s['file']))==s['sha256'],'Evaluated production source changed')
        raw=verified_file(proof['runtime_output']).read_bytes()
        comp=json.loads(verified_file(proof['comparison']).read_text(encoding='utf-8'))
        official=Path(proof['comparison']['file']).parent/'official_outputs.bin'
        check(sha(official)==comp['official_output_sha256']and official.read_bytes()==raw,'Output differs from original software reference')
        sources[name]=np.frombuffer(raw,dtype=source_dtype)
        uvs[name]=verified_file(proof['runtime_uv']).read_bytes()
        readbacks[name]=verified_file(r['readbacks'][name]).read_bytes()
    expected_texture=pixels(wm['staged_original_texture'])
    actual_texture=pixels(r['weapon_texture']['actual_source_png'])
    check(np.array_equal(expected_texture,actual_texture),'Actual imported weapon source RGBA differs from original GE texture')
    material=next(iter(wm['materials'].values()))
    check(hashlib.sha256(actual_texture.tobytes()).hexdigest()==material['rgba_sha256'],'Actual source texture differs from decoded CLUT RGBA')
    check(all(not v['two_sided']for v in r['materials'].values()),'Source culling differs')
    old=Path(__file__).resolve().parents[1]/'Validation/ge_sample_series_runs/30e6de5c441f4e55ba482b1c1f02d427/ue_ge_series.json'
    old_r=json.loads(old.read_text(encoding='utf-8'));check(old_r['passed'],'Prior body control unavailable')
    old_by_sample={e['sample']:e for e in old_r['samples']if e['group']=='slot0_fire_verified'}
    origin=np.array(r['fixed_shared_PSP_world_origin']);units=r['metres_per_PSP_world_unit']
    results=[];body_same=[];distinct={v:set()for v in('positive_y','negative_y')};checked_vertices=0
    for entry,f in zip(r['samples'],wm['frames']):
        check(entry['capture']==f['capture']and entry['sample']==f['sample'],'Actual sample order differs')
        bd=bm['draws'][bm['frames'][f['body_frame_index']]['first_draw']:bm['frames'][f['body_frame_index']]['first_draw']+106]
        wd=wm['draws'][f['first_draw']];target=(wd['register_record'],wd['register_word'])
        before=all((d['register_record'],d['register_word'])<target for d in bd)
        after=all((d['register_record'],d['register_word'])>target for d in bd)
        check(before or after,'Unsupported source draw interleaving')
        expected_order='body_then_weapon'if before else'weapon_then_body'
        check(entry['observed_GE_order']==expected_order,'Actual order classification differs')
        sample=f['sample'];result=dict(sample=sample,views={},observed_GE_order=expected_order)
        for name,count,first in [('body',3456,f['paired_body_first_vertex']),('weapon',243,f['first_output_vertex'])]:
            e=entry['actors'][name];check(e['vertices']==count and identity(e['actor_transform'])and identity(e['component_transform']),'Actor conversion differs')
            check(e['actual_translucency_sort_priority']==((0 if before else 1)if name=='body'else(1 if before else 0)),'Body/weapon component draw priority differs')
            source=sources[name][first:first+count]
            actual=np.frombuffer(readbacks[name],dtype=actual_dtype,count=count,offset=e['readback_byte_offset'])
            expected=(source['position'].astype(np.float64)-origin)*units*100
            expected=np.ascontiguousarray(expected[:,[0,2,1]])
            check(actual['position'].tobytes()==expected.tobytes(),'Actual paired position double bits differ')
            check(actual['normal'].tobytes()==np.ascontiguousarray(source['normal'][:,[0,2,1]]).tobytes(),'Actual paired normal bits differ')
            check(actual['color'].tobytes()==(source['color'].astype(np.float64)/255).astype('<f4').tobytes(),'Actual paired color bits differ')
            if 'topology_uv'in e:
                check(verified_file(e['topology_uv']['indices']).read_bytes()==np.arange(count,dtype='<u4').tobytes(),'Original triangle order/multiplicity differs')
                check(verified_file(e['topology_uv']['uv']).read_bytes()==uvs[name][first*8:(first+count)*8],'Original UV bits differ')
            checked_vertices+=count
        for view,y in [('positive_y',340.),('negative_y',-340.)]:
            e=entry['views'][view];t=e['camera_component_transform']
            check(t['translation']==[0.,y,88.]and t['scale']==[1.,1.,1.],'Actual camera position differs')
            expected_q=np.array([0.,0.,-2**-.5 if y>0 else 2**-.5,2**-.5])
            check(np.max(np.abs(np.array(t['quaternion'])-expected_q))<1e-14,'Actual camera rotation differs')
            im={name:pixels(row)for name,row in e['images'].items()}
            control=pixels(r['samples'][0]['views'][view]['images']['hidden'])
            check(all(v.shape==(768,512,4)for v in im.values()),'Unexpected actual image extent')
            weapon_mask=np.max(np.abs(im['weapon_only'][:,:,:3].astype('i2')-control[:,:,:3].astype('i2')),axis=2)>1
            changed=np.max(np.abs(im['combined'][:,:,:3].astype('i2')-im['body_only'][:,:,:3].astype('i2')),axis=2)>1
            check(int(weapon_mask.sum())>30 and int(changed.sum())>30,'Weapon was not visibly rendered into paired output')
            outside=int((changed&~weapon_mask).sum())
            # An actual image diagnostic, not a raster-equivalence acceptance rule.
            result['views'][view]=dict(weapon_visible_pixels=int(weapon_mask.sum()),combined_changed_pixels=int(changed.sum()),
                                       changed_outside_weapon_control_pixels=outside)
            distinct[view].add(hashlib.sha256(im['combined'].tobytes()).hexdigest())
            if view=='positive_y':
                same=np.array_equal(im['body_only'],pixels(old_by_sample[sample]['png']))
                body_same.append(same);check(same,'Body-only image differs from original72-sample replay control')
        results.append(result)
    check(checked_vertices==44388 and all(len(v)>1 for v in distinct.values()),'Incomplete or static actual replay')
    for name,count in [('body',3456),('weapon',243)]:check(len(readbacks[name])==12*count*52,'Trailing/incomplete actual actor data')
    for e in r['protected_packages_before']:verified_file(e)
    check(r['all_original_packages_unchanged']and len(r['new_packages'])==(0 if 'reused_material'in r else 1),'Unexpected package mutations')
    for e in r['new_packages']:verified_file(e)
    result=dict(schema='weapon-ge-paired-root-independent-audit/v1',passed=True,report_sha256=sha(a.report),
                same_GE_dump_samples=12,body_and_weapon_vertices_checked=44388,all_position_normal_color_bits_exact=True,
                sampled_topology_uv_exact=True,actual_weapon_texture_RGBA_exact=True,body_only_old_control_pixel_equal_samples=sum(body_same),
                unique_combined_pixel_images={k:len(v)for k,v in distinct.items()},protected_packages=len(r['protected_packages_before']),
                new_isolated_weapon_material_packages=len(r['new_packages']),original_GE_actor_order_verified=True,samples=results,original_main_depth_write_verified=False,
                original_GPU_vertex_identity_verified=False,original_timing_verified=False,named_socket_reconstructed=False,
                muzzle_semantics_confirmed=False,formal_M1_replaced=False)
    out.write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({k:v for k,v in result.items()if k!='samples'}))


if __name__=='__main__':main()
