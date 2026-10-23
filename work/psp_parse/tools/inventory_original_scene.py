"""Inventory original main-camera scene PRIMs, retaining exact index topology.

Does not export a level or claim that visible static draws include collision
or unseen geometry. Existing actor/matrix/material parsers are not modified.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import json
from pathlib import Path
import struct

import numpy as np

from exact_aya_materials import decode_texture, iter_material_draws, material_parameters
from export_aya_actual_weapon import WEAPON_SHA, affine
from extract_runtime_character import layout, read_ppdmp
from recover_original_actor_metadata import identity, sha


def draw_stream(commands, push):
    matrices = {'world': [None]*12, 'view': [None]*12, 'proj': [None]*16}
    cursor = dict(world=0, view=0, proj=0)
    nums, data = {0x3a:'world',0x3c:'view',0x3e:'proj'}, {0x3b:'world',0x3d:'view',0x3f:'proj'}
    vertex = index = vt = previous_primitive = None
    for record, (kind, size, pointer) in enumerate(commands):
        if pointer + size > len(push):
            raise ValueError('record outside push buffer')
        if kind == 2: vertex = {'record':record,'bytes':size,'pointer':pointer}
        elif kind == 3: index = {'record':record,'bytes':size,'pointer':pointer}
        elif kind == 1:
            for offset in range(0,size,4):
                word=struct.unpack_from('<I',push,pointer+offset)[0];cmd,value=word>>24,word&0xffffff
                if cmd == 0x12: vt=value
                elif cmd in nums: cursor[nums[cmd]]=value&15
                elif cmd in data:
                    key=data[cmd];at=cursor[key]
                    if at < len(matrices[key]):matrices[key][at]=value
                    cursor[key]=(at+1)&15
                elif cmd == 4 and vertex is not None and vt is not None:
                    primitive=(value>>16)&7
                    resolved=previous_primitive if primitive==7 else primitive
                    if primitive!=7:previous_primitive=primitive
                    yield {'vertex':dict(vertex),'index':None if index is None else dict(index),'vtype':vt,
                           'primitive_raw':primitive,'primitive':resolved,'count':value&0xffff,
                           'register_record':record,'register_word':offset//4,
                           **{k:list(v)for k,v in matrices.items()}}


def topology(draw,push):
    vt,count=draw['vtype'],draw['count'];stride,fields=layout(vt)
    if (vt>>18)&7 or (vt>>9)&3 or (vt>>23)&1 or not ((vt>>7)&3):
        raise ValueError('morphed/weighted/through/missing-position scene format unresolved')
    vertex=draw['vertex'];raw=push[vertex['pointer']:vertex['pointer']+vertex['bytes']]
    if not stride or len(raw)%stride:raise ValueError('VERTICES byte count is not a complete interleaved array')
    stored=len(raw)//stride;it=(vt>>11)&3
    if it:
        index=draw['index']
        if index is None:raise ValueError('indexed PRIM lacks recorded INDICES')
        size,code={1:(1,'B'),2:(2,'H'),3:(4,'I')}[it]
        if index['bytes']!=count*size:raise ValueError('INDICES bytes != PRIM count * index width')
        indices_raw=push[index['pointer']:index['pointer']+index['bytes']]
        order=list(struct.unpack('<'+str(count)+code,indices_raw))
        if order and stored!=max(order)+1:raise ValueError('recorder prefix array does not end at maxIndex+1')
    else:
        indices_raw=b'';order=list(range(count))
        if stored!=count:raise ValueError('unindexed VERTICES count differs from PRIM count')
    if any(i>=stored for i in order):raise ValueError('actual vertex index outside recorded prefix')
    po=(vt>>7)&3;code,den={1:('b',128),2:('h',32768),3:('f',1)}[po]
    positions=np.asarray([struct.unpack_from('<3'+code,raw,i*stride+fields['pos'][0])for i in range(stored)],dtype=float)/den
    if not np.isfinite(positions).all():raise ValueError('nonfinite vertex position')
    primitive=draw['primitive'];triangles=[]
    if primitive==3:
        if count%3:raise ValueError('triangle list count not divisible by three')
        triangles=[tuple(order[i:i+3])for i in range(0,count,3)]
    elif primitive==4:
        triangles=[(order[i+1],order[i],order[i+2])if i&1 else(order[i],order[i+1],order[i+2])for i in range(max(0,count-2))]
    elif primitive==5:
        triangles=[(order[0],order[i],order[i+1])for i in range(1,count-1)]
    else:raise ValueError('nontriangle primitive '+str(primitive))
    degenerate=sum(len(set(t))<3 or np.all(np.cross(positions[t[1]]-positions[t[0]],positions[t[2]]-positions[t[0]])==0)for t in triangles)
    used=positions[np.asarray(sorted(set(order)),dtype=int)]
    world=affine(draw['world']);points=used@world[:3,:3].T+world[:3,3]
    sig=sha(struct.pack('<III',vt,primitive,count)+raw+indices_raw)
    attributes={}
    if 'uv'in fields:
        code,den,components={1:('B',128,2),2:('H',32768,2),3:('f',1,2)}[vt&3]
        uv=np.asarray([struct.unpack_from('<2'+code,raw,i*stride+fields['uv'][0])for i in sorted(set(order))],dtype=float)/den
        attributes.update(original_uv_bbox=[uv.min(0).tolist(),uv.max(0).tolist()],uv_outside_unit_square_vertices=int(np.any((uv<0)|(uv>1),axis=1).sum()))
    if (vt>>2)&7==7:
        rgba=np.asarray([struct.unpack_from('<4B',raw,i*stride+fields['col'][0])for i in sorted(set(order))],dtype=np.uint8)
        packed=rgba[:,0].astype(np.uint32)|(rgba[:,1].astype(np.uint32)<<8)|(rgba[:,2].astype(np.uint32)<<16)|(rgba[:,3].astype(np.uint32)<<24)
        attributes.update(original_vertex_rgba_min=rgba.min(0).tolist(),original_vertex_rgba_max=rgba.max(0).tolist(),
                          original_vertex_rgba32_values=np.unique(packed).tolist(),
                          original_nonwhite_rgb_vertices=int(np.any(rgba[:,:3]!=255,axis=1).sum()),
                          original_nonopaque_vertex_alpha=int((rgba[:,3]!=255).sum()))
    return {'geometry_sha256':sig,'vertex_payload_sha256':sha(struct.pack('<I',vt)+raw),
            'stride':stride,'layout':fields,'stored_vertices':stored,'referenced_vertices':len(set(order)),
            'index_type':it,'minimum_index':min(order)if order else None,'maximum_index':max(order)if order else None,
            'index_payload_sha256':None if not indices_raw else sha(indices_raw),
            'triangles_including_degenerate':len(triangles),'degenerate_triangles':int(degenerate),
            'nondegenerate_triangles':len(triangles)-int(degenerate),
            'world_bbox':[points.min(0).tolist(),points.max(0).tolist()],**attributes},points


def inventory(captures,aya_path,actor_path,out):
    aya=json.loads(aya_path.read_text(encoding='utf-8'));actor=json.loads(actor_path.read_text(encoding='utf-8'))
    aya_hashes={p['vertex_sha256']for p in aya['packets']}
    excluded=aya_hashes|{p['vertex_sha256']for p in actor['packets']}|{WEAPON_SHA}
    raw_root=Path(__file__).resolve().parent.parent/'raw'
    result={'schema':'original-scene-prim-inventory/v1','inputs':{'aya':identity(aya_path),'actor':identity(actor_path)},
            'source_evidence':[identity(raw_root/name)for name in ['Record.cpp','RecordFormat.h','GPUState.cpp','GPUState.h']], 'captures':[],
            'contract':{'indexed_vertex_bytes':'(maxIndex+1)*vertex_stride prefix, no minIndex subtraction',
                        'index_count':'PRIM count, with actual u8/u16/u32 INDICES bytes',
                        'register_timing':'execute each GE command before that exact PRIM; later words in same REGISTERS are excluded',
                        'triangle_strip':'expand consecutive triples; swap first two indices on odd strip triangles',
                        'matrix_initial_state':'only explicit matrix writes accepted; unobserved INIT matrices remain unresolved'},
            'limitations':['Main-camera and two-capture stability are static candidates, not proof of object semantics or original level completeness.',
                           'Occluded/culled/off-camera geometry, original collision, triggers and navigation are absent from this visual inventory.',
                           'WORLD/VIEW/PROJ are captured per draw; lighting, alpha, texture function and vertex colors need corresponding renderer behavior.']}
    for capture in captures:
        commands,push=read_ppdmp(str(capture));draws=list(draw_stream(commands,push))
        states={(d['register_record'],d['register_word']):d for d in iter_material_draws(commands,push)}
        aya_draws=[d for d in draws if sha(struct.pack('<I',d['vtype'])+push[d['vertex']['pointer']:d['vertex']['pointer']+d['vertex']['bytes']])in aya_hashes]
        if len(aya_draws)!=106:raise ValueError('capture lacks exactly the known106 Aya draws')
        reference=aya_draws[0]
        if any(d['view']!=reference['view']or d['proj']!=reference['proj']for d in aya_draws):raise ValueError('Aya main camera state changes within known mesh')
        if None in reference['world']+reference['view']+reference['proj']:raise ValueError('main camera matrices not fully explicit')
        reference_state=states[(reference['register_record'],reference['register_word'])]
        inv_aya=np.linalg.inv(affine(reference['world']))
        record={'input':identity(capture),'aya_world_payload':reference['world'],'aya_view_payload':reference['view'],
                'aya_proj_payload':reference['proj'],'aya_framebuffer_payload':reference_state['registers'].get(0x9c),
                'all_prim_count':len(draws),'excluded_known_actor_draws':0,'rejection_counts':{},'draws':[],'materials':{}}
        rejects=Counter();texture_cache={};allpoints=[]
        for d in draws:
            raw=push[d['vertex']['pointer']:d['vertex']['pointer']+d['vertex']['bytes']]
            vertex_sha=sha(struct.pack('<I',d['vtype'])+raw)
            if vertex_sha in excluded:record['excluded_known_actor_draws']+=1;continue
            if d['vtype']&(1<<23):rejects['2D_through_mode']+=1;continue
            if None in d['view']+d['proj']:rejects['VIEW_or_PROJ_not_explicit']+=1;continue
            if d['view']!=reference['view']or d['proj']!=reference['proj']:rejects['different_VIEW_or_PROJ']+=1;continue
            if None in d['world']:rejects['WORLD_not_explicit']+=1;continue
            entry={k:d[k]for k in ['vtype','primitive','primitive_raw','count','register_record','register_word','world','view','proj']}
            entry['vertex_record']=d['vertex']['record'];entry['index_record']=None if d['index']is None else d['index']['record']
            state=states[(d['register_record'],d['register_word'])];r=state['registers'];entry['same_framebuffer_as_Aya']=r.get(0x9c)==reference_state['registers'].get(0x9c)
            entry['original_register_payloads']={hex(k):v for k,v in sorted(r.items())}
            entry['lighting_enabled']=bool(r.get(0x17,0)&1)
            entry['vertex_fields']={'uv':d['vtype']&3,'color':(d['vtype']>>2)&7,'normal':(d['vtype']>>5)&3,'position':(d['vtype']>>7)&3,'weights':(d['vtype']>>9)&3,'indices':(d['vtype']>>11)&3}
            try:
                facts,points=topology(d,push);entry.update(facts)
                relative=points@inv_aya[:3,:3].T+inv_aya[:3,3]
                entry['aya_relative_bbox']=[relative.min(0).tolist(),relative.max(0).tolist()];allpoints.append(points)
            except ValueError as error:
                entry['geometry_error']=str(error);rejects['geometry: '+str(error)]+=1
            params=material_parameters(r);entry['material_parameters']=params
            texture=state['texture0']
            material_key={'parameters':params,'texture':None if texture is None else texture['sha256'],
                          'clut':sha(state['clut'][:1024]),'lighting':entry['lighting_enabled'],
                          'depth_test_enabled':bool(r.get(0x23,0)&1),'depth_test_function':r.get(0xde),
                          'depth_write_enabled':not bool(r.get(0xe7,0)&1),
                          'stencil_fog_masks':{hex(k):r.get(k)for k in [0x1f,0x24,0xcd,0xce,0xcf,0xdc,0xdd,0xe8,0xe9]},
                          'material_registers':{hex(k):r.get(k)for k in [0x50,0x51,0x53,0x54,0x55,0x56,0x57,0x58,0x5b,0x5c,0x5d]}}
            mid=sha(json.dumps(material_key,sort_keys=True).encode());entry['material_id']=mid
            if mid not in record['materials']:
                resource={'material_id':mid,**material_key,'status':'unresolved'}
                try:
                    if not params['texture_enabled']:
                        resource['status']='untextured_original_color_state'
                    elif texture is None:raise ValueError('missing TEXTURE0')
                    elif texture['framebuffer']:raise ValueError('framebuffer-backed texture')
                    else:
                        cache=(texture['sha256'],sha(state['clut'][:1024]),r.get(0xc2),r.get(0xc3),r.get(0xc5),r.get(0xa8),r.get(0xb8))
                        if cache not in texture_cache:texture_cache[cache]=decode_texture(texture['raw'],r,state['clut'],state['clut_known'])[1]
                        resource.update(status='original_RGBA_decoded',**texture_cache[cache])
                except (ValueError,KeyError)as error:resource['reason']=str(error)
                record['materials'][mid]=resource
            entry['material_status']=record['materials'][mid]['status']
            if entry['material_status']=='unresolved':entry['material_error']=record['materials'][mid]['reason']
            if 'geometry_sha256'in entry:
                entry['instance_sha256']=sha(bytes.fromhex(entry['geometry_sha256'])+struct.pack('<12I',*d['world']))
                entry['render_sha256']=sha(bytes.fromhex(entry['instance_sha256'])+bytes.fromhex(mid))
            record['draws'].append(entry)
        record['rejection_counts']=dict(rejects)
        if allpoints:
            p=np.concatenate(allpoints);q=p@inv_aya[:3,:3].T+inv_aya[:3,3]
            record['world_bbox']=[p.min(0).tolist(),p.max(0).tolist()];record['aya_relative_bbox']=[q.min(0).tolist(),q.max(0).tolist()]
        result['captures'].append(record)
    for record in result['captures']:
        others=[r for r in result['captures']if r is not record]
        for d in record['draws']:
            for field in ['geometry_sha256','instance_sha256','render_sha256']:
                d[field+'_present_in_all_captures']=field in d and all(any(o.get(field)==d[field]for o in r['draws'])for r in others)
        draws=record['draws'];geoms=[d for d in draws if 'geometry_sha256'in d]
        record['summary']={'main_camera_candidate_draws':len(draws),'triangle_capable_draws':len(geoms),
            'triangles_including_degenerate':sum(d['triangles_including_degenerate']for d in geoms),
            'nondegenerate_triangles':sum(d['nondegenerate_triangles']for d in geoms),
            'primitives':dict(Counter(str(d['primitive'])for d in draws)),'vtypes':dict(Counter(hex(d['vtype'])for d in draws)),
            'index_types':dict(Counter(str(d['vertex_fields']['indices'])for d in draws)),
            'material_count':len(record['materials']),'material_statuses':dict(Counter(m['status']for m in record['materials'].values())),
            'material_error_draws':dict(Counter(d.get('material_error')for d in draws if d.get('material_error'))),
            'same_framebuffer_draws':sum(d['same_framebuffer_as_Aya']for d in draws),
            'geometry_stable_draws':sum(d['geometry_sha256_present_in_all_captures']for d in draws),
            'WORLD_instance_stable_draws':sum(d['instance_sha256_present_in_all_captures']for d in draws),
            'full_render_signature_stable_draws':sum(d['render_sha256_present_in_all_captures']for d in draws)}
        stable=[d for d in geoms if d['render_sha256_present_in_all_captures']and d['same_framebuffer_as_Aya']]
        mids={d['material_id']for d in stable}
        record['static_candidate_summary']={'draws':len(stable),'referenced_vertices':sum(d['referenced_vertices']for d in stable),
            'nondegenerate_triangles':sum(d['nondegenerate_triangles']for d in stable),'WORLD_instances':len({tuple(d['world'])for d in stable}),
            'material_states':len(mids),'unique_decoded_RGBA':len({record['materials'][m].get('rgba_sha256')for m in mids}),
            'material_formats':dict(Counter(record['materials'][m].get('format')for m in mids)),
            'nonwhite_rgb_vertices':sum(d.get('original_nonwhite_rgb_vertices',0)for d in stable),
            'nonopaque_vertex_alpha':sum(d.get('original_nonopaque_vertex_alpha',0)for d in stable),
            'unique_vertex_RGBA_values':len({v for d in stable for v in d.get('original_vertex_rgba32_values',[])}),
            'UV_outside_unit_square_vertices':sum(d.get('uv_outside_unit_square_vertices',0)for d in stable)}
        if stable:
            record['static_candidate_summary']['world_bbox']=[np.min([d['world_bbox'][0]for d in stable],axis=0).tolist(),np.max([d['world_bbox'][1]for d in stable],axis=0).tolist()]
            record['static_candidate_summary']['aya_relative_bbox']=[np.min([d['aya_relative_bbox'][0]for d in stable],axis=0).tolist(),np.max([d['aya_relative_bbox'][1]for d in stable],axis=0).tolist()]
    result['static_render_multiset_equal']=all(Counter(d['render_sha256']for d in r['draws']if d['render_sha256_present_in_all_captures'])==Counter(d['render_sha256']for d in result['captures'][0]['draws']if d['render_sha256_present_in_all_captures'])for r in result['captures'])
    out.parent.mkdir(parents=True,exist_ok=True);out.write_text(json.dumps(result,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf-8')
    md=['# Original main-camera scene recovery inventory','','Evidence describes observed main-camera draws, not the complete original level or collision.','']
    for record in result['captures']:
        md += ['## '+Path(record['input']['path']).parent.name,'','```json',json.dumps(record['summary'],indent=2),'```','','Stable original scene candidates:','','```json',json.dumps(record['static_candidate_summary'],indent=2),'```','',
               'World bbox: `'+str(record.get('world_bbox'))+'`','',
               'Aya-relative bbox: `'+str(record.get('aya_relative_bbox'))+'`','']
    md += ['## Matrix and topology contract','']+['- '+k+': '+v for k,v in result['contract'].items()]
    md += ['','## Limits','']+['- '+v for v in result['limitations']]
    out.with_suffix('.md').write_text('\n'.join(md)+'\n',encoding='utf-8')
    print(json.dumps([{'capture':Path(r['input']['path']).parent.name,**r['summary']}for r in result['captures']],ensure_ascii=False))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--capture',type=Path,action='append',required=True)
    p.add_argument('--aya-metadata',type=Path,required=True);p.add_argument('--actor-metadata',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    a=p.parse_args();inventory(a.capture,a.aya_metadata,a.actor_metadata,a.out)
