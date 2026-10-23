"""Independently check packed street attributes against exact PRIM-time GE data.

Reuses the recorder/state readers, not the scene exporter or its coordinate code.
Never starts PPSSPP or the PC runtime.
"""
import argparse
from collections import Counter
import json
from pathlib import Path
import struct

import numpy as np
from PIL import Image

from exact_aya_materials import decode_texture, iter_material_draws, material_parameters
from extract_runtime_character import layout, read_ppdmp
from export_aya_actual_weapon import matrix_draws
from inventory_original_scene import draw_stream
from recover_original_actor_metadata import identity, sha


def matrix(payload):
    """Decode the PSP column-major 3x4 float24 upload independently."""
    values=struct.unpack('<12f',struct.pack('<12I',*(v<<8 for v in payload)))
    result=np.eye(4,dtype=float)
    for column in range(4):
        for row in range(3):result[row,column]=values[column*3+row]
    return result


def checked(description):
    path=Path(description['path'])
    if identity(path)!=description:raise ValueError('file identity changed: '+str(path))
    return path


def material_key(state):
    r=state['registers'];texture=state['texture0']
    key={'parameters':material_parameters(r),'texture':texture['sha256'],
         'clut':sha(state['clut'][:1024]),'lighting':bool(r.get(0x17,0)&1),
         'depth_test_enabled':bool(r.get(0x23,0)&1),'depth_test_function':r.get(0xde),
         'depth_write_enabled':not bool(r.get(0xe7,0)&1),
         'stencil_fog_masks':{hex(k):r.get(k)for k in [0x1f,0x24,0xcd,0xce,0xcf,0xdc,0xdd,0xe8,0xe9]},
         'material_registers':{hex(k):r.get(k)for k in [0x50,0x51,0x53,0x54,0x55,0x56,0x57,0x58,0x5b,0x5c,0x5d]}}
    return sha(json.dumps(key,sort_keys=True).encode())


def verify(report_path,output_path,runtime_root):
    report=json.loads(report_path.read_text(encoding='utf-8'))
    binary=checked(report['binary']);metadata_path=checked(report['metadata'])
    manifest_path=checked(report['material_manifest'])
    metadata=json.loads(metadata_path.read_text(encoding='utf-8'))
    for item in metadata['inputs'].values():checked(item)
    inventory=json.loads(Path(metadata['inputs']['inventory']['path']).read_text(encoding='utf-8'))
    canonical=json.loads(Path(metadata['inputs']['canonical_Aya']['path']).read_text(encoding='utf-8'))
    units=float(canonical['pc_units_per_original_unit']);floor=float(canonical['reference_floor'])
    data=binary.read_bytes();header=struct.unpack_from('<8s4I8f',data)
    if header[:5]!=(b'T3BSCN1\0',1,140,31656,81):raise ValueError('scene header differs from original inventory')
    expected_size=56+140*12+31656*24
    if len(data)!=expected_size:raise ValueError('binary truncation/trailing data')
    packets=[struct.unpack_from('<3I',data,56+i*12)for i in range(140)]
    vertex_base=56+140*12
    manifest=manifest_path.read_text(encoding='ascii').splitlines()
    if manifest[0]!='T3BSCNM1 81'or len(manifest)!=82:raise ValueError('material manifest count/schema')
    material_lines=[line.split()for line in manifest[1:]]
    for m,line in zip(metadata['materials'],material_lines):
        if len(line)!=4 or line[0]!=m['texture']['bmp_relative']or list(map(int,line[1:]))!=[m['blend_enable'],m['depth_write'],m['cull_enable']]:
            raise ValueError('manifest does not preserve per-material flags')
        if (runtime_root/line[0]).resolve()!=checked(m['texture']['bmp']).resolve():raise ValueError('manifest texture path mismatch')
        checked(m['raw_texture']);checked(m['raw_clut'])
    expected_header_floats=struct.pack('<8f',*metadata['player_spawn'],*metadata['enemy_spawn'],units,floor)
    if data[24:56]!=expected_header_floats:raise ValueError('spawn/scale header rounding differs from metadata')
    reference_inverse=np.linalg.inv(matrix(metadata['reference_Aya_WORLD']))
    spawn_checks={}
    for name,world in [('player',metadata['reference_Aya_WORLD']),('enemy',metadata['reference_enemy_WORLD'])]:
        relative=reference_inverse@matrix(world);yaw=float(np.arctan2(relative[0,2],relative[0,0]))
        c,s=np.cos(yaw),np.sin(yaw);rigid=np.asarray([[c,0,s],[0,1,0],[-s,0,c]])
        residual=float(abs(relative[:3,:3]-rigid).max());det=float(np.linalg.det(relative[:3,:3]))
        if residual>1e-4 or abs(det-1)>2e-4 or abs(relative[1,3])>1e-3:raise ValueError('spawn not yaw-only coplanar rigid')
        target=[relative[0,3]*units,relative[2,3]*units,yaw]
        if not np.allclose(target,metadata[name+'_spawn'],atol=1e-7,rtol=0):raise ValueError('spawn does not match actual WORLD')
        spawn_checks[name]={'max_yaw_rotation_residual':residual,'determinant':det,'source_vertical_translation':float(relative[1,3]),'spawn':list(map(float,target))}
    canonical_source=Path(canonical['output']);canonical_binary=canonical_source.read_bytes()
    aya_header=struct.unpack_from('<8s8I4f',canonical_binary)
    aya_bones,aya_packets,aya_vertices=aya_header[2:5]
    aya_vertex_base=56+aya_bones*4+aya_packets*16
    aya_values=[struct.unpack_from('<8fI8I8f',canonical_binary,aya_vertex_base+i*100)for i in range(aya_vertices)]
    pose_base=aya_vertex_base+aya_vertices*100
    frames=aya_header[5]
    pose_matrices=np.frombuffer(canonical_binary,dtype='<f4',offset=pose_base+frames*4).reshape(frames,aya_bones,3,4)
    first_aya_points=[]
    for v in aya_values:
        p=np.zeros(3)
        for slot in range(v[8]):
            m=pose_matrices[0,v[9+slot]];p+=v[17+slot]*(m[:,:3]@v[:3]+m[:,3])
        first_aya_points.append(p)
    aya_first_min_source_y=float(np.min(first_aya_points,axis=0)[1])
    aya_first_min_y=(aya_first_min_source_y-floor)*units
    errors=[];all_source_signatures=[];texture_rgba={};road=[];all_positions=[];reference_aya_points=[]
    uv_identical=rgba_identical=0
    for capture_index,capture in enumerate(inventory['captures']):
        capture_path=checked(capture['input']);commands,push=read_ppdmp(str(capture_path))
        if capture['input']==metadata['inputs']['reference_GE']:
            aya_metadata=json.loads(checked(inventory['inputs']['aya']).read_text(encoding='utf-8'))
            aya_hashes={p['vertex_sha256']for p in aya_metadata['packets']};body_packets=0
            for body in matrix_draws(commands,push):
                if body['sha256']not in aya_hashes:continue
                body_packets+=1;vt=body['vtype'];stride,fields=layout(vt)
                if(vt>>9)&3!=2 or(vt>>7)&3!=2:raise ValueError('Aya fixture weight/position format')
                raw=push[body['pointer']:body['pointer']+body['size']];weights=((vt>>14)&7)+1
                for offset in range(0,len(raw),stride):
                    pos=np.array(struct.unpack_from('<3h',raw,offset+fields['pos'][0]))/32768
                    w=struct.unpack_from('<'+str(weights)+'H',raw,offset+fields['wt'][0]);p=np.zeros(3)
                    for slot,weight in enumerate(w):
                        if weight:p+=weight/32768*(matrix(body['bones'][slot*12:slot*12+12])@np.r_[pos,1])[:3]
                    pc=(reference_inverse@matrix(body['world'])@np.r_[p,1])[:3];pc[1]-=floor;pc*=units
                    reference_aya_points.append(pc)
            if body_packets!=106:raise ValueError('same GE fixture does not contain complete Aya106 draw group')
        raw_draws={(d['register_record'],d['register_word']):d for d in draw_stream(commands,push)}
        states={(d['register_record'],d['register_word']):d for d in iter_material_draws(commands,push)}
        selected=[d for d in capture['draws']if d.get('render_sha256_present_in_all_captures')and d['same_framebuffer_as_Aya']and 'geometry_sha256'in d]
        if len(selected)!=140:raise ValueError('capture no longer has140 stable main-camera draws')
        signatures=[]
        for index,entry in enumerate(selected):
            key=entry['register_record'],entry['register_word'];draw=raw_draws[key];state=states[key]
            if draw['vtype']!=0x11f or draw['primitive']!=3 or(draw['vtype']>>11)&3:raise ValueError('unexpected vertex/topology format')
            v=draw['vertex'];raw=push[v['pointer']:v['pointer']+v['bytes']]
            if len(raw)!=draw['count']*20 or draw['count']%3:raise ValueError('PRIM/VERTICES size contract')
            geom=sha(struct.pack('<III',draw['vtype'],draw['primitive'],draw['count'])+raw)
            mid=material_key(state)
            if geom!=entry['geometry_sha256']or mid!=entry['material_id']:raise ValueError('raw GE geometry/material identity differs')
            signature=geom+struct.pack('<12I',*draw['world']).hex()+mid;signatures.append(signature)
            if capture['input']!=metadata['inputs']['reference_GE']:continue
            original=metadata['draws'][index];first,count,material=packets[index]
            if (first,count,material)!=(original['first'],draw['count'],original['material']):raise ValueError('draw order/range/material mismatch')
            if first!=(packets[index-1][0]+packets[index-1][1]if index else 0):raise ValueError('vertex range gap/overlap')
            if original['original_WORLD']!=draw['world']or original['original_VIEW']!=draw['view']or original['original_PROJ']!=draw['proj']:raise ValueError('metadata matrix snapshot not PRIM-time state')
            if original['original_register_payloads']!={hex(k):v for k,v in sorted(state['registers'].items())}:raise ValueError('metadata register snapshot not PRIM-time')
            if mid!=metadata['materials'][material]['material_id']:raise ValueError('packed draw material binding')
            flags=[int(bool(state['registers'][0x21]&1)),int(not(state['registers'][0xe7]&1)),int(bool(state['registers'][0x1d]&1))]
            if flags!=list(map(int,material_lines[material][1:])):raise ValueError('source flags differ from material manifest')
            transform=reference_inverse@matrix(draw['world']);points=[]
            for j in range(count):
                source_pos=np.array(struct.unpack_from('<3h',raw,j*20+12),dtype=float)/32768
                q=(transform@np.r_[source_pos,1])[:3];q[1]-=floor;q*=units
                packed_offset=vertex_base+(first+j)*24
                actual=np.array(struct.unpack_from('<3f',data,packed_offset))
                errors.append(float(abs(q-actual).max()));points.append(actual)
                if data[packed_offset+12:packed_offset+20]!=raw[j*20:j*20+8]:raise ValueError('raw float UV bits changed')
                if data[packed_offset+20:packed_offset+24]!=raw[j*20+8:j*20+12]:raise ValueError('vertex RGBA changed')
                uv_identical+=1;rgba_identical+=1
            all_positions.extend(points)
            points=np.asarray(points);tri=points.reshape(-1,3,3)
            normal=np.cross(tri[:,1]-tri[:,0],tri[:,2]-tri[:,0]);centroid=tri.mean(axis=1)
            length=np.linalg.norm(normal,axis=1);horizontal=abs(normal[:,1])>0.99*length
            near=(np.linalg.norm(centroid[:,[0,2]],axis=1)<15)&(abs(centroid[:,1])<0.05)&horizontal
            if near.any():road.append({'draw':index,'vertex_record':v['record'],'near_horizontal_triangles':int(near.sum()),
                'up':int((normal[near,1]>0).sum()),'down':int((normal[near,1]<0).sum()),
                'near_road_pc_y_range':[float(tri[near,:,1].min()),float(tri[near,:,1].max())],
                'WORLD_determinant':float(np.linalg.det(matrix(draw['world'])[:3,:3]))})
            if mid not in texture_rgba:
                rgba,info=decode_texture(state['texture0']['raw'],state['registers'],state['clut'],state['clut_known'])
                resource=metadata['materials'][material]
                if resource['texture_sha256']!=state['texture0']['sha256']or resource['clut_sha256']!=sha(state['clut'][:1024]):raise ValueError('texture/CLUT identity mismatch')
                for extension in ['png','bmp']:
                    image=Image.open(checked(resource['texture'][extension])).convert('RGBA')
                    if image.size!=(info['width'],info['height'])or image.tobytes()!=rgba:raise ValueError('RGBA/alpha changed in '+extension)
                texture_rgba[mid]={'rgba_sha256':sha(rgba),'alpha_zero_pixels':int((np.frombuffer(rgba,dtype=np.uint8)[3::4]==0).sum()),
                    'alpha_partial_pixels':int(((np.frombuffer(rgba,dtype=np.uint8)[3::4]>0)&(np.frombuffer(rgba,dtype=np.uint8)[3::4]<255)).sum())}
        all_source_signatures.append(Counter(signatures))
    if any(s!=all_source_signatures[0]for s in all_source_signatures):raise ValueError('two raw captures no longer match full render multiset')
    if len(errors)!=31656 or max(errors)>2e-5 or uv_identical!=31656 or rgba_identical!=31656:raise ValueError('position/attribute verification incomplete')
    if len(texture_rgba)!=81 or len({t['rgba_sha256']for t in texture_rgba.values()})!=73:raise ValueError('material/texture verification incomplete')
    ground_draws=[r for r in road if r['draw']in [4,5,6,7,8,9]]
    road_min=min(r['near_road_pc_y_range'][0]for r in ground_draws);road_max=max(r['near_road_pc_y_range'][1]for r in ground_draws)
    positions=np.asarray(all_positions)
    captured_aya_min_y=float(np.min(reference_aya_points,axis=0)[1])
    view=matrix(metadata['reference_VIEW']);camera=np.linalg.inv(view)@np.array([0,0,0,1]);camera_pc=(reference_inverse@camera)[:3];camera_pc[1]-=floor;camera_pc*=units
    result={'schema':'original-street-verification/v1','passed':True,'export_report':identity(report_path),
        'binary':identity(binary),'metadata':identity(metadata_path),'canonical_Aya_binary':identity(canonical_source),
        'source_GE_files':[c['input']for c in inventory['captures']],
        'draws_checked':140,'vertices_checked':len(errors),'triangles_checked':10552,'material_states_checked':len(texture_rgba),
        'unique_RGBA_textures_checked':73,'binary_size_bytes':len(data),'maximum_position_rounding_error_pc_units':max(errors),
        'UV_float32_bit_identical_vertices':uv_identical,'RGBA_byte_identical_vertices':rgba_identical,
        'cross_capture_raw_geometry_WORLD_material_multisets_equal':True,'PNG_and_BMP_RGBA_alpha_exact':True,
        'spawn_yaw_rigidity_checks':spawn_checks,'canonical_units':units,'canonical_floor':floor,
        'pc_bbox':[positions.min(0).tolist(),positions.max(0).tolist()],
        'ground_relation':{'near_Aya_horizontal_draws':road,'base_road_draws':[r['draw']for r in ground_draws],'base_road_pc_y_range':[road_min,road_max],
            'Aya_frame0_source_skin_min_original_y':aya_first_min_source_y,
            'Aya_frame0_source_skin_min_pc_y':aya_first_min_y,
            'road_minus_Aya_frame0_min_pc_y_range':[road_min-aya_first_min_y,road_max-aya_first_min_y],
            'same_GE_Aya_min_pc_y':captured_aya_min_y,'same_GE_Aya_vertices':len(reference_aya_points),
            'road_minus_same_GE_Aya_min_pc_y_range':[road_min-captured_aya_min_y,road_max-captured_aya_min_y],
            'camera_pc_position':camera_pc.tolist(),
            'meaning':'Canonical Aya frame0 source skin is a different animation sample; minY measures mesh extent, not an anatomical foot contact marker. No collision has been inferred.'},
        'runtime_C_executed':False}
    output_path.parent.mkdir(parents=True,exist_ok=True);output_path.write_text(json.dumps(result,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf-8')
    print(json.dumps(result,ensure_ascii=False))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--export-report',type=Path,required=True);p.add_argument('--runtime-root',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    args=p.parse_args();verify(args.export_report,args.out,args.runtime_root)
