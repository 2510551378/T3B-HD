"""Export the independently inventoried original static street to T3BSCN1.

Keeps triangle order, float UV, vertex RGBA and per-draw depth/cull/blend.
No recentering, per-model scaling, artificial geometry or inferred collision.
"""
import argparse
from collections import Counter, defaultdict
import json
from pathlib import Path
import struct

import numpy as np
from PIL import Image

from exact_aya_materials import decode_texture, iter_material_draws, material_parameters, write_rgba_bmp
from export_aya_actual_weapon import affine
from export_aya_source_skin import resolve_output_model
from extract_runtime_character import read_ppdmp
from inventory_original_scene import draw_stream, topology
from recover_original_actor_metadata import identity, sha


def yaw_spawn(world, inverse_reference, units):
    relative=inverse_reference@affine(world)
    rotation=relative[:3,:3]
    yaw=float(np.arctan2(rotation[0,2],rotation[0,0]))
    c,s=np.cos(yaw),np.sin(yaw)
    reconstructed=np.asarray([[c,0,s],[0,1,0],[-s,0,c]])
    error=float(np.abs(rotation-reconstructed).max())
    determinant=float(np.linalg.det(rotation))
    if error>0.0001 or abs(determinant-1)>0.0002 or abs(relative[1,3])>0.001:
        raise ValueError('actor WORLD is not a coplanar yaw-only rigid spawn within float24 tolerance')
    return [float(relative[0,3]*units),float(relative[2,3]*units),yaw],{
        'relative_matrix_rows':relative.tolist(),'max_yaw_rotation_residual':error,
        'rotation_determinant':determinant,'original_vertical_translation':float(relative[1,3]),
        'rotation_tolerance':0.0001,'vertical_tolerance_original_units':0.001}


def check_material(parameters,registers):
    required={'texture_enabled':True,'uv_map_mode':0,'uv_storage_type':3,'uv_through_mode':False,
              'texture_function':0,'texture_alpha_used':True,'color_double':False,
              'alpha_test_enabled':True,'alpha_test_function':6,'alpha_test_ref':0,'alpha_test_mask':255,
              'wrap_u':'repeat','wrap_v':'repeat','min_filter_raw':1,'mag_filter_raw':1,
              'blend_src_factor':2,'blend_dst_factor':3,'blend_equation':0,'cull_mode_raw':0,
              'uv_scale':[1.0,1.0],'uv_offset':[0.0,0.0]}
    if any(parameters.get(k)!=v for k,v in required.items()):
        raise ValueError('source material exceeds the explicitly selected T3BSCNM1 renderer contract')
    if not registers[0x23]&1 or registers[0xde]!=7 or registers[0xe7]not in [0,1]:
        raise ValueError('unexpected original depth state')


def export(args):
    inventory=json.loads(args.inventory.read_text(encoding='utf-8'))
    canonical=json.loads(args.canonical_aya_report.read_text(encoding='utf-8'))
    if not inventory.get('static_render_multiset_equal'):
        raise ValueError('cross-capture static render multiset not verified')
    capture=inventory['captures'][args.reference_capture]
    reference_path=Path(capture['input']['path'])
    if identity(reference_path)!=capture['input']:
        raise ValueError('reference GE bytes changed after inventory')
    if canonical['schema']!='aya-source-skin-export/v2':raise ValueError('unexpected canonical scene scale schema')
    units,floor=float(canonical['pc_units_per_original_unit']),float(canonical['reference_floor'])
    if not np.isfinite(units)or units<=0 or not np.isfinite(floor):raise ValueError('invalid canonical scale/floor')
    selected=[d for d in capture['draws']if d.get('render_sha256_present_in_all_captures')and d['same_framebuffer_as_Aya']and 'geometry_sha256'in d]
    if len(selected)!=140 or sum(d['nondegenerate_triangles']for d in selected)!=10552:
        raise ValueError('selected original street does not equal the verified140draw inventory')
    commands,push=read_ppdmp(str(reference_path));all_draws=list(draw_stream(commands,push))
    draws={(d['register_record'],d['register_word']):d for d in all_draws}
    states={(d['register_record'],d['register_word']):d for d in iter_material_draws(commands,push)}
    mids=sorted({d['material_id']for d in selected});mindex={m:i for i,m in enumerate(mids)}
    if len(mids)!=81:raise ValueError('street requires81 states after splitting mixed depth-write material')
    relative_root=Path(args.output_directory)
    root=resolve_output_model(args.runtime_root,relative_root)
    if any(ch.isspace()for ch in relative_root.as_posix()):raise ValueError('runtime scene paths must be ASCII tokens without spaces')
    texture_root=root/'textures';texture_root.mkdir(parents=True,exist_ok=True)
    inverse_aya=np.linalg.inv(affine(capture['aya_world_payload']))
    actor_path=Path(inventory['inputs']['actor']['path'])
    if identity(actor_path)!=inventory['inputs']['actor']:raise ValueError('original actor metadata changed')
    actor=json.loads(actor_path.read_text(encoding='utf-8'));actor_hashes=[p['vertex_sha256']for p in actor['packets']]
    actors=defaultdict(list)
    for d in all_draws:
        v=d['vertex'];h=sha(struct.pack('<I',d['vtype'])+push[v['pointer']:v['pointer']+v['bytes']])
        if h in set(actor_hashes):actors[tuple(d['world'])].append(h)
    enemy_worlds=[world for world,hashes in actors.items()if hashes==actor_hashes]
    if len(enemy_worlds)!=1:raise ValueError('reference frame must contain exactly the selected complete original enemy')
    enemy_spawn,enemy_validation=yaw_spawn(enemy_worlds[0],inverse_aya,units)
    player_spawn,player_validation=yaw_spawn(capture['aya_world_payload'],inverse_aya,units)
    if max(abs(v)for v in player_spawn)>1e-7:raise ValueError('reference Aya is not identity in her own anchor space')
    player_spawn=[0.0,0.0,0.0]
    resources,textures,originals,vertex_records,packet_records={}, {}, [],bytearray(),[]
    point_sets=[];first=0
    for index,entry in enumerate(selected):
        key=entry['register_record'],entry['register_word'];draw=draws[key];state=states[key]
        if draw['vtype']!=0x11f or draw['primitive']!=3 or draw['index']is not None and (draw['vtype']>>11)&3:
            raise ValueError('selected scene is not unindexed original F32UV/RGBA/POS16 triangle data')
        facts,_=topology(draw,push)
        if facts['geometry_sha256']!=entry['geometry_sha256']or draw['world']!=entry['world']:
            raise ValueError('actual PRIM-time geometry/WORLD differs from inventory')
        if draw['view']!=capture['aya_view_payload']or draw['proj']!=capture['aya_proj_payload']:
            raise ValueError('selected geometry does not use original Aya main camera')
        material=entry['material_id'];parameters=material_parameters(state['registers']);check_material(parameters,state['registers'])
        texture=state['texture0']
        if texture is None or texture['framebuffer']:raise ValueError('street texture bytes unavailable')
        if material not in resources:
            rgba,info=decode_texture(texture['raw'],state['registers'],state['clut'],state['clut_known'])
            rkey=info['rgba_sha256']
            if rkey not in textures:
                basename='street_'+rkey[:16]
                png,bmp=texture_root/(basename+'.png'),texture_root/(basename+'.bmp')
                Image.frombytes('RGBA',(info['width'],info['height']),rgba).save(png)
                write_rgba_bmp(bmp,info['width'],info['height'],rgba)
                textures[rkey]={'rgba_sha256':rkey,'width':info['width'],'height':info['height'],
                    'png':identity(png),'bmp':identity(bmp),'bmp_relative':(relative_root/'textures'/bmp.name).as_posix(),
                    'alpha_preserved':True}
            raw_stem=root/('material_'+material[:16])
            raw_texture=raw_stem.with_suffix('.texture.bin');raw_clut=raw_stem.with_suffix('.clut.bin')
            raw_texture.write_bytes(texture['raw']);raw_clut.write_bytes(state['clut'][:1024])
            resources[material]={'material_index':mindex[material],'material_id':material,
                'texture':textures[rkey],'texture_sha256':texture['sha256'],'clut_sha256':sha(state['clut'][:1024]),
                'raw_texture':identity(raw_texture),'raw_clut':identity(raw_clut),'parameters':parameters,
                'blend_enable':int(parameters['alpha_blend_enabled']),
                'depth_write':int(not(state['registers'][0xe7]&1)),'cull_enable':int(parameters['cull_enabled']),
                'original_register_payloads':{hex(k):v for k,v in sorted(state['registers'].items())},'decoded_texture':info}
        vertex=draw['vertex'];raw=push[vertex['pointer']:vertex['pointer']+vertex['bytes']]
        transform=inverse_aya@affine(draw['world'])
        points=[]
        for offset in range(0,len(raw),20):
            uv=struct.unpack_from('<2f',raw,offset);rgba=struct.unpack_from('<4B',raw,offset+8)
            pos=np.asarray(struct.unpack_from('<3h',raw,offset+12),dtype=float)/32768
            p=(transform[:3,:3]@pos+transform[:3,3]-[0,floor,0])*units
            if not np.isfinite(p).all()or not np.isfinite(uv).all():raise ValueError('nonfinite scene attribute')
            vertex_records.extend(struct.pack('<5f4B',*p,*uv,*rgba));points.append(p)
        packet_records.append((first,draw['count'],mindex[material]));first+=draw['count'];point_sets.append(np.asarray(points))
        originals.append({'draw':index,'first':packet_records[-1][0],'count':draw['count'],'material':mindex[material],
            **entry,'original_WORLD':draw['world'],'original_VIEW':draw['view'],'original_PROJ':draw['proj'],
            'texture_sha256':texture['sha256'],'clut_sha256':sha(state['clut'][:1024]),
            'original_register_payloads':{hex(k):v for k,v in sorted(state['registers'].items())}})
    if len(textures)!=73 or len(vertex_records)!=31656*24:raise ValueError('original texture/vertex inventory count changed')
    content=bytearray(struct.pack('<8s4I8f',b'T3BSCN1\0',1,len(packet_records),first,len(mids),*player_spawn,*enemy_spawn,units,floor))
    for record in packet_records:content.extend(struct.pack('<3I',*record))
    content.extend(vertex_records)
    binary=root/'original_street.bin';binary.write_bytes(content)
    manifest=root/'original_street_materials.txt';lines=['T3BSCNM1 81']
    for mid in mids:
        m=resources[mid];lines.append(f'{m["texture"]["bmp_relative"]} {m["blend_enable"]} {m["depth_write"]} {m["cull_enable"]}')
    manifest.write_text('\n'.join(lines)+'\n',encoding='ascii')
    all_points=np.concatenate(point_sets)
    metadata={'schema':'original-street-scene/v1','binary':identity(binary),'material_manifest':identity(manifest),
        'counts':{'draws':140,'vertices':31656,'triangles':10552,'materials':81,'unique_RGBA_textures':73},
        'inputs':{'inventory':identity(args.inventory),'canonical_Aya':identity(args.canonical_aya_report),'reference_GE':identity(reference_path)},
        'source_geometry_capture_identities':[r['input']for r in inventory['captures']],
        'player_spawn':player_spawn,'enemy_spawn':enemy_spawn,'player_spawn_validation':player_validation,'enemy_spawn_validation':enemy_validation,
        'canonical_units':units,'canonical_floor':floor,'reference_Aya_WORLD':capture['aya_world_payload'],
        'reference_enemy_WORLD':list(enemy_worlds[0]),'reference_VIEW':capture['aya_view_payload'],'reference_PROJ':capture['aya_proj_payload'],
        'coordinate_contract':'PC = canonical_units * (inverse(reference_Aya_WORLD) * original_draw_WORLD * normalized_POS16 - [0,canonical_floor,0]); no recenter/height scaling',
        'vertex_contract':'F32 UV bytes and RGBA bytes preserved; POS16/32768; original triangle order retained',
        'pc_bbox':[all_points.min(0).tolist(),all_points.max(0).tolist()],
        'draws':originals,'materials':[resources[m]for m in mids],'textures':list(textures.values()),
        'unsupported_original_state':{'fog':'Original enable/FOG1/FOG2/color preserved in every draw registers; not encoded in T3BSCNM1.',
                                      'stencil':'Original enable/test/ops/masks preserved; not encoded in T3BSCNM1.',
                                      'original_camera_projection':'Captured for evidence; M1 uses its PC camera/projection.',
                                      'original_depth_direction':'PSP depth-test function7 is recorded; renderer must map visible depth ordering to its PC projection.'},
        'limits':['Observed camera-visible stable street geometry; not the complete original level.',
                  'Collision/navigation/triggers are not recovered by GE geometry extraction.',
                  'Per-draw original order is retained; no speculative transparent sorting or mesh welding is applied.']}
    meta_path=root/'original_street.json';meta_path.write_text(json.dumps(metadata,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf-8')
    report={'schema':'original-street-export/v1','passed':True,**metadata['counts'],'binary':identity(binary),
            'material_manifest':identity(manifest),'metadata':identity(meta_path),'pc_bbox':metadata['pc_bbox'],
            'player_spawn':player_spawn,'enemy_spawn':enemy_spawn,'canonical_units':units,'canonical_floor':floor,
            'unsupported_original_state':metadata['unsupported_original_state'],'runtime_C_executed':False}
    args.report.parent.mkdir(parents=True,exist_ok=True);args.report.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(report,ensure_ascii=False))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--inventory',type=Path,required=True);p.add_argument('--canonical-aya-report',type=Path,required=True)
    p.add_argument('--runtime-root',type=Path,required=True);p.add_argument('--output-directory',type=Path,default=Path('assets/scenes/original_street'))
    p.add_argument('--reference-capture',type=int,default=0);p.add_argument('--report',type=Path,required=True)
    export(p.parse_args())
