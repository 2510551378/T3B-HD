"""Compare actual UE street components/Texture2D Source against raw same-frame GE."""
import argparse,hashlib,json,struct,sys
from pathlib import Path
import numpy as np
from PIL import Image


def check(v,msg):
    if not v:raise ValueError(msg)
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def read(p):return json.loads(p.read_text(encoding='utf-8'))
def file(row):
    p=Path(row['file']);check(sha(p)==row['sha256'],'Changed evidence: '+str(p));return p
def image(row):return np.array(Image.open(file(row)).convert('RGBA'))
def f24(v):return (np.array(v,dtype='<u4')<<8).view('<f4').astype(float)


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--run',type=Path,required=True);a=p.parse_args()
    folder=a.run;out=folder/'independent_street_verification.json';check(not out.exists(),'Refuse audit overwrite')
    project=Path(__file__).resolve().parents[1];sys.path.insert(0,str(project.parent/'psp_parse/tools'))
    from extract_runtime_character import read_ppdmp,layout
    from inventory_original_scene import draw_stream
    from exact_aya_materials import iter_material_draws,decode_texture
    r=read(folder/'ue_weapon_ge_paired.json');request=read(folder/'request.json');done=read(folder/'process_completed.json')
    started=read(folder/'process_started.json')
    check(r['passed']and done['exit_code']==0 and r['process_id']==started['pid']==done['pid'],'Process/acquisition failed')
    check(r['run_id']==request['run_id']==started['run_id'],'Run identity mismatch')
    check(sha(folder/'capture_weapon_ge_paired_executed.py')==request['script_sha256']==r['script_sha256'],'Producer identity mismatch')
    file(request['camera_helper']);helper=file(request['street_helper'])
    report=r['paired_street'];snapshot=read(file(report['snapshot']));file(request['street_snapshot'])
    check(report['helper_sha256']==sha(helper),'Scene helper identity mismatch')
    check(len(r['samples'])==1 and r['samples'][0]['sample']==snapshot['source_sample']==0,'Snapshot/time mismatch')
    source=Path(snapshot['capture']['path']);check(sha(source)==snapshot['capture']['sha256'],'Actual source dump changed')
    commands,push=read_ppdmp(str(source))
    draws={(d['register_record'],d['register_word']):d for d in draw_stream(commands,push)}
    states={(d['register_record'],d['register_word']):d for d in iter_material_draws(commands,push)}
    bundle=file(snapshot['binary']).read_bytes();check(bundle[:8]==b'T3BSTG1\0'and struct.unpack_from('<3I',bundle,8)==(140,31656,81),'Snapshot dimensions differ')
    source_dt=np.dtype([('position','<f8',3),('uv','<f4',2),('color','u1',4)])
    actual_dt=np.dtype([('position','<f8',3),('color','<f4',4)])
    components=file(report['readback']).read_bytes();indices=file(report['indices']).read_bytes();uv=file(report['uv']).read_bytes()
    check(len(components)==31656*40 and len(indices)==31656*4 and len(uv)==31656*8,'Actual scene readback extent differs')
    origin=np.array(snapshot['fixed_shared_PSP_world_origin']);units=snapshot['metres_per_PSP_world_unit']
    textures={};checked=0;draw_checks=[]
    for d,actual in zip(snapshot['draws'],report['draws']):
        key=d['register_record'],d['register_word'];raw_draw=draws[key];state=states[key];regs=state['registers']
        check(raw_draw['vtype']==0x11f and raw_draw['primitive']==3 and raw_draw['count']==d['vertices'],'Raw GE geometry mismatch')
        check(raw_draw['world']==d['WORLD_payload']and raw_draw['view']==d['VIEW_payload']and raw_draw['proj']==d['PROJECTION_payload'],'Raw matrices differ')
        check({hex(k):v for k,v in regs.items()}==d['original_registers'],'Actual PRIM register replay differs')
        vertex=raw_draw['vertex'];raw=push[vertex['pointer']:vertex['pointer']+vertex['bytes']]
        check(hashlib.sha256(struct.pack('<I',raw_draw['vtype'])+raw).hexdigest()==d['raw_vertex_sha256'],'Original vertex identity differs')
        stride,offsets=layout(raw_draw['vtype']);count=d['vertices'];first=d['first_vertex']
        local=np.array([struct.unpack_from('<3h',raw,i*stride+offsets['pos'][0])for i in range(count)],dtype=float)/32768
        matrix=f24(raw_draw['world']).reshape(3,4,order='F')
        world=np.column_stack([local,np.ones(count)])@matrix.T;expected=((world-origin)*units*100)[:,[0,2,1]]
        raw_uv=b''.join(raw[i*stride:i*stride+8]for i in range(count))
        colors=np.array([struct.unpack_from('<4B',raw,i*stride+8)for i in range(count)],dtype='u1')
        exported=np.frombuffer(bundle,dtype=source_dt,count=count,offset=20+140*20+first*36)
        actual_data=np.frombuffer(components,dtype=actual_dt,count=count,offset=actual['readback_byte_offset'])
        check(np.ascontiguousarray(expected,dtype='<f8').tobytes()==actual_data['position'].tobytes()==exported['position'].tobytes(),'UE position double bits differ from raw source')
        check(actual_data['color'].tobytes()==(colors.astype(float)/255).astype('<f4').tobytes(),'UE vertex color bits differ')
        check(exported['color'].tobytes()==colors.tobytes(),'Bridge colour bytes differ')
        check(uv[first*8:(first+count)*8]==raw_uv==exported['uv'].tobytes(),'Raw/bridge/actual UE UV bits differ')
        check(indices[first*4:(first+count)*4]==np.arange(count,dtype='<u4').tobytes(),'Triangle order/multiplicity differs')
        check(actual['material_asset']==d['material_asset']and actual['two_sided']==(not bool(d['source_cull'])) and
              actual['actual_sort_priority']==-1000+d['draw'],'Actual material/cull/order binding differs')
        tex=state['texture0'];rgba,facts=decode_texture(tex['raw'],regs,state['clut'],state['clut_known'])
        check(facts['rgba_sha256']==d['texture_rgba_sha256'],'Original material CLUT binding differs')
        textures[facts['rgba_sha256']]=rgba;checked+=count
        draw_checks.append(dict(source_draw=d['draw'],vertices=count,source_cull=d['source_cull'],source_blend=d['source_blend'],source_depth_write=d['source_depth_write']))
    check(len(draw_checks)==140 and checked==31656 and len(textures)==73,'Incomplete scene coverage')
    check(len(report['textures'])==73,'Incomplete actual Texture2D exports')
    for row in report['textures']:
        check(row['srgb']is False,'Street texture changed colour-space interpretation')
        rgba=image(row).tobytes();check(rgba==textures[row['source_rgba_sha256']],'Actual Texture2D Source differs from same-frame GE CLUT pixels')
    # Body/weapon and camera should match the accepted scene-free run, not a new guessed placement.
    old=project/'Validation/original_camera_ue_runs/5a76f5096f5c46be84c5d8f1260a1f29';baseline=read(old/'ue_weapon_ge_paired.json')
    current=r['samples'][0]['views']['original'];prior=baseline['samples'][0]['views']['original']
    for k in ('camera_component_transform','original_camera'):check(current[k]==prior[k],'Scene changed the verified source camera')
    body_points=0
    for name,count in [('body',3456),('weapon',243)]:
        raw=file(r['readbacks'][name]).read_bytes();priorraw=file(baseline['readbacks'][name]).read_bytes()[:count*52]
        check(raw==priorraw,'Same-frame actor component differs from accepted baseline');body_points+=count
    identical_images=[]
    for name in ('hidden','body_only','weapon_only','combined'):
        same=np.array_equal(image(current['images'][name]),image(prior['images'][name]))
        check(same,'Scene-hidden control differs: '+name);identical_images.append(name)
    street=image(current['images']['street_only']);combined=image(current['images']['street_with_aya_weapon'])
    check(street.shape==combined.shape==(272,480,4),'Actual scene image extent differs')
    foreground=np.max(street[:,:,:3],axis=2)>1;changed=np.max(np.abs(street[:,:,:3].astype('i2')-combined[:,:,:3].astype('i2')),axis=2)>1
    check(int(foreground.sum())>50000 and int(changed.sum())>1000,'Street or Aya/weapon are missing from actual scene capture')
    check(r['all_original_packages_unchanged']and not r['new_packages'],'Package protection failed')
    for row in r['protected_packages_before']:file(row)
    result=dict(schema='t3b-paired-street-UE-audit/v1',passed=True,pid=r['process_id'],engine_version=r['engine_version'],
        source_sample=0,scene_draws=len(draw_checks),scene_vertices=checked,actor_vertices=body_points,
        actual_Texture2D_Source_RGBA_exact=73,scene_hidden_controls_pixel_identical=identical_images,
        street_visible_pixels=int(foreground.sum()),pixels_changed_by_Aya_and_gun=int(changed.sum()),draws=draw_checks,
        original_packages_unchanged=len(r['protected_packages_before']),new_packages=0,
        source_fog_stencil_equivalence=False,source_translucent_depth_equivalence=False,
        UE_GE_ordered_cpp_pass_executed=False,original_collision_recovered=False,complete_level_recovered=False,formal_M1_replaced=False)
    out.write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps({k:result[k]for k in ('passed','scene_draws','scene_vertices','actual_Texture2D_Source_RGBA_exact','street_visible_pixels','pixels_changed_by_Aya_and_gun')}))


if __name__=='__main__':main()
