"""Recover observed street from the same retained GE frame as Aya+gun sample0."""
import argparse,hashlib,json,struct
from pathlib import Path
from collections import defaultdict
import numpy as np
from PIL import Image
from extract_runtime_character import read_ppdmp,layout
from inventory_original_scene import draw_stream
from exact_aya_materials import iter_material_draws,decode_texture,material_parameters


def check(v,msg):
    if not v:raise ValueError(msg)
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def read(p):return json.loads(p.read_text(encoding='utf-8'))
def f24(v):return (np.array(v,dtype='<u4')<<8).view('<f4').astype(float)


def recover(out,sample=0):
    class Args:pass
    a=Args();a.out=out
    check(not a.out.exists(),'Do not replace recovered scene evidence');a.out.mkdir(parents=True)
    root=Path(__file__).resolve().parents[1];project=root.parent/'t3b_unreal'
    old_path=root.parent/'t3b_hd/assets/scenes/original_street/original_street.json';old=read(old_path)
    stage_path=project/'Content/SourceData/manifest.json';stage=read(stage_path)
    cam_path=root/'out/AYA_ORIGINAL_GE_CAMERA_20261021/recovery_v2/cameras.json';cameras=read(cam_path);camera=cameras['frames'][sample]
    path=Path(camera['capture']['path']);check(sha(path)==camera['capture']['sha256'],'Original paired dump changed')
    commands,push=read_ppdmp(str(path));states={(d['register_record'],d['register_word']):d for d in iter_material_draws(commands,push)}
    candidates=defaultdict(list)
    for d in old['draws']:candidates[d['vertex_payload_sha256']].append(d)
    materials={m['material_index']:m for m in old['materials']};textures={};rows=[];vertex_chunks=[];first=0
    origin=np.array(cameras['fixed_shared_PSP_world_origin']);units=cameras['metres_per_PSP_world_unit']
    dt=np.dtype([('position','<f8',3),('uv','<f4',2),('color','u1',4)])
    for d in draw_stream(commands,push):
        v=d['vertex'];raw=push[v['pointer']:v['pointer']+v['bytes']]
        vertex_id=hashlib.sha256(struct.pack('<I',d['vtype'])+raw).hexdigest()
        if vertex_id not in candidates:continue
        state=states[(d['register_record'],d['register_word'])];r=state['registers'];tex=state['texture0']
        check(d['vtype']==0x11f and d['primitive']==3 and d['count']%3==0,'Unsupported street vertex format')
        check(d['view']==camera['view_payload'] and d['proj']==camera['projection_payload'],'Street uses different camera')
        check(tex is not None and not tex['framebuffer'],'Unresolved source texture')
        params=material_parameters(r)
        rgba,facts=decode_texture(tex['raw'],r,state['clut'],state['clut_known'])
        compatible=[e for e in candidates[vertex_id] if params==materials[e['material']]['parameters'] and
                    facts['rgba_sha256']==materials[e['material']]['texture']['rgba_sha256']]
        check(compatible,'Actual CLUT/material differs from imported scene candidate')
        exact=[e for e in compatible if e['world']==d['world']]
        choice=exact or compatible
        check(len({e['material']for e in choice})==1,'Ambiguous scene material binding')
        old_draw=choice[0];material_index=old_draw['material'];old_mat=materials[material_index]
        imported=stage['scene']['materials'][material_index]
        check(Image.open(project/'Content/SourceData'/imported['texture']).convert('RGBA').tobytes()==rgba,'Staged original RGBA differs')
        check(imported['cull']==old_mat['cull_enable'] and imported['blend']==old_mat['blend_enable'] and
              imported['depth_write']==old_mat['depth_write'],'Imported state binding differs')
        if facts['rgba_sha256']not in textures:
            png=a.out/('original_'+facts['rgba_sha256'][:16]+'.png')
            Image.frombytes('RGBA',(facts['width'],facts['height']),rgba).save(png)
            textures[facts['rgba_sha256']]=dict(file=str(png.resolve()),sha256=sha(png),rgba_sha256=facts['rgba_sha256'],
                asset=imported['texture_asset'],width=facts['width'],height=facts['height'])
        check(all(r[k]==0 for k in range(0x18,0x1c)) and r[0x17]==1 and r[0x53]==7 and
              r[0x54]==0 and r[0x5c]==0xffffff and r[0x5d]==255,'Unproven source vertex lighting')
        # With no enabled lights, COLOR_0 as ambient and full-white global ambient,
        # the pinned software-lighting integer formula preserves all RGBA channels.
        check(all(((2*c+1)*511)>>10==c for c in range(256)),'Ambient RGBA identity failed')
        stride,offsets=layout(d['vtype']);check(stride==20 and len(raw)==d['count']*20,'Original vertex extent differs')
        source=np.array([struct.unpack_from('<3h',raw,i*20+offsets['pos'][0]) for i in range(d['count'])],dtype=float)/32768
        world=f24(d['world']).reshape(3,4,order='F');world_points=np.column_stack([source,np.ones(len(source))])@world.T
        transformed=((world_points-origin)*units*100)[:,[0,2,1]]
        vertices=np.empty(d['count'],dtype=dt);vertices['position']=transformed
        vertices['uv']=[struct.unpack_from('<2f',raw,i*20)for i in range(d['count'])]
        vertices['color']=[struct.unpack_from('<4B',raw,i*20+8)for i in range(d['count'])]
        vertex_chunks.append(vertices.tobytes())
        rows.append(dict(draw=len(rows),source_old_draw=old_draw['draw']if len(choice)==1 else None,
            source_old_draw_candidates=[e['draw']for e in choice],WORLD_matches_old_reference=bool(exact),
            temporal_object_identity_verified=False,first_vertex=first,vertices=d['count'],material=material_index,
            register_record=d['register_record'],register_word=d['register_word'],vertex_record=v['record'],
            raw_vertex_sha256=vertex_id,WORLD_payload=d['world'],VIEW_payload=d['view'],PROJECTION_payload=d['proj'],
            original_registers={hex(k):v for k,v in r.items()},texture_rgba_sha256=facts['rgba_sha256'],
            texture_payload_sha256=tex['sha256'],clut_ram_sha256=hashlib.sha256(state['clut']).hexdigest(),
            material_asset=imported['asset'],source_blend=imported['blend'],source_depth_write=imported['depth_write'],source_cull=imported['cull'],
            vertex_output_sha256=hashlib.sha256(vertices.tobytes()).hexdigest()))
        first+=d['count']
    check(rows and first>0,'No observed scene instances')
    if sample==0:check(len(rows)==140 and first==31656 and len(textures)==73,'Original sample0 scene coverage changed')
    body=[(d['record'],d['word'])for d in camera['draws']if d['actor']==0]
    check(max((d['register_record'],d['register_word'])for d in rows)<min(body),'Scene/actor ordering requires per-packet actor rendering')
    binary=a.out/'paired_street_snapshot.bin'
    with binary.open('wb')as f:
        f.write(b'T3BSTG1\0'+struct.pack('<3I',len(rows),first,81))
        for d in rows:f.write(struct.pack('<5I',d['register_record'],d['register_word'],d['first_vertex'],d['vertices'],d['material']))
        for data in vertex_chunks:f.write(data)
    result=dict(schema='t3b-paired-original-street-snapshot/v1',passed=True,source_sample=sample,
        capture=camera['capture'],camera=dict(file=str(cam_path),sha256=sha(cam_path)),
        old_scene=dict(file=str(old_path),sha256=sha(old_path)),stage_manifest=dict(file=str(stage_path),sha256=sha(stage_path)),
        binary=dict(file=str(binary.resolve()),sha256=sha(binary)),draws=rows,draw_count=len(rows),vertices=first,
        textures=list(textures.values()),texture_count=len(textures),materials=stage['scene']['materials'],
        fixed_shared_PSP_world_origin=origin.tolist(),metres_per_PSP_world_unit=units,
        producer_sha256=sha(Path(__file__)),original_fog_enabled=True,original_stencil_enabled=True,
        UE_fog_stencil_equivalence=False,complete_level_recovered=False,original_collision_recovered=False,
        limits=['Only observed original street resource instances from the same captured sample as Aya+weapon.',
                'No extrapolation to other samples, off-camera geometry, enemies, FX or original collision.',
                'A reused geometry with different WORLD is not proof that one persistent object moved.',
                'Existing UE standard materials do not implement source fog/stencil/main-depth blend contract.'])
    (a.out/'snapshot.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    return result


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--out',required=True,type=Path)
    p.add_argument('--sample',type=int,default=0);a=p.parse_args();check(0<=a.sample<12,'Sample outside retained capture series')
    result=recover(a.out,a.sample)
    print(json.dumps(dict(passed=True,draws=result['draw_count'],vertices=result['vertices'],textures=result['texture_count'])))


if __name__=='__main__':main()
