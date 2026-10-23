"""Infer weapon-relative FX anchors; never promote them to confirmed sockets."""
import argparse,hashlib,json
from pathlib import Path
import numpy as np


def read(p):return json.loads(p.read_text(encoding='utf-8'))
def check(v,msg):
    if not v:raise ValueError(msg)
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def identity(p):return dict(file=str(p.resolve()),sha256=sha(p))
def f24(v):return (np.array(v,dtype='<u4')<<8).view('<f4').astype(float)
def affine(v):
    m=np.eye(4);m[:,:3]=np.array(v).reshape(4,3);return m


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--scene-inputs',type=Path,required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args()
    check(not a.out.exists(),'Never replace anchor evidence');a.out.mkdir(parents=True)
    scene=read(a.scene_inputs);root=Path(__file__).resolve().parents[1]
    weapon_path=root/'out/WEAPON_GE_PAIRED_20261020/inputs_v1/inputs.json';weapon=read(weapon_path);binary=Path(weapon['binary']['file'])
    check(sha(binary)==weapon['binary']['sha256'],'Weapon transform inputs changed');raw=binary.read_bytes()
    gpu=root.parent/'t3b_unreal/Validation/ge_strip_fx_runs/eb127720dab34700b91773818e73350e/independent_verification.json'
    check(read(gpu)['passed'],'FX GPU source recovery has not passed')
    proof_path=root/'out/WEAPON_GE_PAIRED_20261020/runtime_v1/verification.json';proof=read(proof_path)
    check(proof['passed']and proof['input_sha256']==weapon['binary']['sha256'],'Weapon runtime proof differs')
    dtype=np.dtype([('position','<f4',3),('normal','<f4',3),('color','u1',4),('secondary','u1',3),('pad','u1')]);runtime=np.fromfile(proof['runtime_output']['file'],dtype=dtype)
    records=[];selected=[];points=[];all_inputs=[];max_transform_error=0.
    for i,(frame,wf)in enumerate(zip(scene['frames'],weapon['frames'])):
        check(frame['capture']['sha256']==weapon['captures'][i]['sha256'],'Scene and gun capture identities differ')
        d=weapon['draws'][wf['first_draw']];at=d['binary_byte_offset'];values=np.frombuffer(raw,dtype='<f4',count=243*16,offset=at+1464).reshape(243,16)
        check(d['vtype']==0x522 and d['weight_slots']==1 and np.all(values[:,6]==values[0,6])and not np.any(values[:,7:14]),'Gun is not the verified single-weight rigid draw')
        world=affine(np.frombuffer(raw,dtype='<f4',count=12,offset=at+1024));bone=affine(np.frombuffer(raw,dtype='<f4',count=12,offset=at+1072).astype(float)*float(values[0,6]));rigid=bone@world;inverse=np.linalg.inv(rigid)
        expected=np.column_stack([values[:,:3].astype(float),np.ones(243)])@rigid;actual=runtime[d['first_output_vertex']:d['first_output_vertex']+243]['position'].astype(float)
        terms=np.abs(np.column_stack([values[:,:3].astype(float),np.ones(243)]))@np.abs(bone)@np.abs(world)
        bound=16*np.finfo(np.float32).eps*terms[:,:3]
        check(np.all(np.abs(expected[:,:3]-actual)<=bound),'Rigid gun derivation exceeds original F32 arithmetic bound')
        max_transform_error=max(max_transform_error,float(np.max(np.abs(expected[:,:3]-actual))))
        body=next(x for x in frame['draws']if x['category']=='body');main_view=affine(f24(body['VIEW_payload']));main_proj=f24(body['PROJECTION_payload']).reshape(4,4)
        candidates=[]
        for fx in frame['draws']:
            if fx['category']!='unweighted_strip_fx':continue
            view=affine(f24(fx['VIEW_payload']));proj=f24(fx['PROJECTION_payload']).reshape(4,4)
            common=np.array([0.,0.,0.,1.])@affine(f24(fx['WORLD_payload']))@view@np.linalg.inv(main_view)
            local=common@inverse
            row=dict(sample=i,record=fx['register_record'],word=fx['register_word'],source_vertices=fx['source_vertices'],vtype=fx['vtype'],
                texture_RGBA_sha256=fx['texture_RGBA_sha256'],FX_local_origin_in_main_PSP_world=common[:3].tolist(),FX_origin_in_raw_weapon_local=local[:3].tolist(),
                matching_main_projection_XYW=bool(np.array_equal(proj[:,[0,1,3]],main_proj[:,[0,1,3]])),source_semantic_name=None)
            candidates.append(row)
            # Repeated14/15-vertex strips are an observation-based cluster, not a named engine socket.
            if fx['vtype']==0x11e and fx['source_vertices']in(14,15):
                check(row['matching_main_projection_XYW'],'Candidate FX uses a different XYW projection')
                records.append(row)
        all_inputs.extend(candidates)
        group=[r for r in records if r['sample']==i]
        if group:
            check(len(group)==2 and np.array_equal(group[0]['FX_origin_in_raw_weapon_local'],group[1]['FX_origin_in_raw_weapon_local']),'Candidate pair has distinct origins')
            selected.append(i);points.append(group[0]['FX_origin_in_raw_weapon_local'])
    check(selected==[1,2,11],'Observed candidate sample set changed')
    points=np.asarray(points);center=points.mean(0);offsets=points-center
    local=np.frombuffer(raw,dtype='<f4',count=243*16,offset=weapon['draws'][0]['binary_byte_offset']+1464).reshape(243,16)[:,:3].astype(float)
    result=dict(schema='source-FX-weapon-local-anchor-candidates/v1',passed=True,scene=identity(a.scene_inputs),weapon=identity(weapon_path),GPU_audit=identity(gpu),weapon_proof=identity(proof_path),
        inferred_socket_confirmed=False,source_attachment_record_located=False,anatomical_muzzle_name_confirmed=False,original_timing_verified=False,
        candidate_samples=selected,independent_sample_origins=points.tolist(),candidate_raw_weapon_local_mean=center.tolist(),
        max_sample_distance_from_mean_raw_local=float(np.linalg.norm(offsets,axis=1).max()),raw_weapon_vertex_bounds=[local.min(0).tolist(),local.max(0).tolist()],
        nearest_original_weapon_vertex_to_mean=dict(index=int(np.linalg.norm(local-center,axis=1).argmin()),distance_raw_local=float(np.linalg.norm(local-center,axis=1).min())),
        max_rigid_derivation_error_PSP_units=max_transform_error,paired_observations=records,all_recovered_strip_origins=all_inputs,
        producer_sha256=sha(Path(__file__)),limits=['Six draw observations contain only3 independent sample origins; sample1/2 are adjacent similar shooting poses.',
            'A stable gun-relative FX origin supports a muzzle-emitter hypothesis but does not locate the original named attachment object or establish gameplay/muzzle direction.',
            'No M1 binding or source animation was replaced using this candidate.'])
    (a.out/'candidates.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps(dict(passed=True,candidate_samples=selected,mean=center.tolist(),max_local_residual=result['max_sample_distance_from_mean_raw_local'])))


if __name__=='__main__':main()
