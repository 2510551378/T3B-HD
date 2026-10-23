"""Compare actual GPU scenes with/without the exact same-capture creature."""
import argparse,hashlib,json
from pathlib import Path
import numpy as np


def read(p):return json.loads(p.read_text(encoding='utf-8'))
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def check(v,msg):
    if not v:raise ValueError(msg)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for k in ('baseline','run','out'):p.add_argument('--'+k,required=True,type=Path)
    a=p.parse_args();check(not a.out.exists(),'Never replace accepted addition audit')
    old_req=read(a.baseline/'request.json');new_req=read(a.run/'request.json')
    def manifest(req):
        item=req['inputs'];path=Path(item['file']);check(sha(path)==item['sha256'],'Changed observed scene input');return read(path)
    old,new=manifest(old_req),manifest(new_req)
    for folder in (a.baseline,a.run):check(read(folder/'independent_verification.json')['passed'],'Scene GPU audit has not passed')
    check(all((a.baseline/f).read_bytes()==(a.run/f).read_bytes()for f in ('actual_vs.dxbc','actual_ps.dxbc')),'Actual compiled shaders differ')
    fields=('register_record','register_word','WORLD_payload','VIEW_payload','PROJECTION_payload','flags','vertices','vertex_sha256','vertex_input_sha256','texture_RGBA_sha256','registers')
    effects=[]
    for i,(before,after)in enumerate(zip(old['frames'],new['frames'])):
        other=[d for d in after['draws']if d['category']=='other_original_actor'];retained=[d for d in after['draws']if d['category']!='other_original_actor']
        check(len(other)==28 and sum(d['vertices']for d in other)==1800,'Wrong added actor subset')
        check([{k:d[k]for k in fields}for d in before['draws']]==[{k:d[k]for k in fields}for d in retained],'Scene data changed beyond additional actor')
        check(not any((d['vtype']>>9)&3 for d in after['excluded_draws']),'Unrecovered weighted draw remains in these captures')
        owner=np.fromfile(a.run/f'sample_{i}_source_states.owner_u32',dtype='<u4').reshape(272,480);mask=np.isin(owner,[d['owner']for d in other])
        before_rgb=np.fromfile(a.baseline/f'sample_{i}_source_states.rgba',dtype='u1').reshape(272,480,4)
        after_rgb=np.fromfile(a.run/f'sample_{i}_source_states.rgba',dtype='u1').reshape(272,480,4)
        effects.append(dict(sample=i,added_creature_draws=28,added_vertices=1800,final_creature_owner_pixels=int(mask.sum()),
            changed_RGB_pixels=int(np.any(before_rgb[:,:,:3]!=after_rgb[:,:,:3],axis=2).sum()),remaining_weighted_excluded_draws=0))
    check(len(effects)==12 and all(e['final_creature_owner_pixels']>0 and e['changed_RGB_pixels']>0 for e in effects),'Actor is not visible in every sample')
    report=dict(passed=True,baseline=str(a.baseline.resolve()),run=str(a.run.resolve()),
        baseline_audit_sha256=sha(a.baseline/'independent_verification.json'),new_audit_sha256=sha(a.run/'independent_verification.json'),
        all_retained_draw_inputs_states_cameras_and_texture_RGBA_identical=True,actual_compiled_VS_PS_byte_identical=True,
        effects=effects,UE_executed=False,whole_game_actor_coverage_verified=False,auditor_sha256=sha(Path(__file__)))
    a.out.write_text(json.dumps(report,indent=2),encoding='utf-8');print(json.dumps(dict(passed=True,samples=12,added_draws=336,added_vertices=21600)))


if __name__=='__main__':main()
