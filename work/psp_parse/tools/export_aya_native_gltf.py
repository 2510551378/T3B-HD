"""Export an explicitly approximate native-SRT glTF candidate and decode-test it.

Existing affine runtime assets are never replaced. Original source weights,
float24 commands and quaternion magnitudes remain in portable provenance.
"""
import argparse
import copy
import csv
import json
from pathlib import Path
import shutil
import struct
import subprocess

import numpy as np
from PIL import Image

from analyze_aya_local_srt import srt_fit
from recover_original_actor_metadata import identity, sha

SPEC='https://registry.khronos.org/glTF/specs/2.0/glTF-2.0.html'


def pinned(description):
    path=Path(description['path'])
    if identity(path)!=description:raise ValueError('input identity changed: '+str(path))
    return path


def write_json(path,value):
    path.write_text(json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf-8')


class Buffer:
    def __init__(self):self.data=bytearray();self.views=[];self.accessors=[]
    def add(self,values,kind,component=5126,target=None,bounds=False):
        dtype={5126:'<f4',5123:'<u2'}[component];a=np.asarray(values,dtype=dtype)
        while len(self.data)%4:self.data.append(0)
        offset=len(self.data);raw=a.tobytes();self.data.extend(raw)
        view={'buffer':0,'byteOffset':offset,'byteLength':len(raw)}
        if target:view['target']=target
        self.views.append(view);count=len(a)
        accessor={'bufferView':len(self.views)-1,'byteOffset':0,'componentType':component,'count':count,'type':kind}
        if bounds:
            flat=a.reshape(count,-1);accessor.update(min=flat.min(0).tolist(),max=flat.max(0).tolist())
        self.accessors.append(accessor);return len(self.accessors)-1


def export(clip_report_path,out):
    clip=json.loads(clip_report_path.read_text(encoding='utf-8'))
    inputs={key:pinned(value)for key,value in clip['inputs'].items()}
    manifest=json.loads(inputs['manifest'].read_text(encoding='utf-8'))
    metadata=json.loads(inputs['metadata'].read_text(encoding='utf-8'))
    materials=json.loads(inputs['materials'].read_text(encoding='utf-8'))
    if len(manifest['frames'])!=60 or len(metadata['bones'])!=44 or len(metadata['packets'])!=106:raise ValueError('candidate requires verified44bone106packet60sample Aya')
    if sha(Path(clip['output']).read_bytes())!=clip['sha256']:raise ValueError('affine clip bytes changed')
    out.mkdir(parents=True,exist_ok=True);(out/'raw').mkdir(exist_ok=True);(out/'textures').mkdir(exist_ok=True)
    parents=[b['parent']for b in metadata['bones']];roots=[i for i,p in enumerate(parents)if p<0]
    if roots!=[0,43]:raise ValueError('expected two proven source roots0 and43')
    raw_sources=[];q=[];translation=[];original_ge=[];B=None
    for i,frame in enumerate(manifest['frames']):
        path=Path(frame['sourceBlock']['file']);raw=path.read_bytes()
        if len(raw)!=44*0x130:raise ValueError('source snapshot truncation')
        destination=out/'raw'/f'source_{i:04d}.bin';destination.write_bytes(raw)
        raw_sources.append({'frame':i,'ticks':frame['ticks'],'original':identity(path),'file':destination.relative_to(out).as_posix(),'sha256':sha(raw)})
        values=np.frombuffer(raw,dtype='<f4').reshape(44,76)
        if not np.isfinite(values[:,:7]).all():raise ValueError('nonfinite source quaternion/translation')
        q.append(values[:,:4].copy());translation.append(values[:,4:7].copy())
        current_B=values[:,32:48].reshape(44,4,4).transpose(0,2,1).copy()
        if B is None:B=current_B
        elif not np.array_equal(B,current_B):raise ValueError('bind compensation not constant across capture')
        original_ge.append([r['matrix']for r in frame['records']])
    q=np.asarray(q,dtype=float);translation=np.asarray(translation,dtype=float)
    norm=np.linalg.norm(q,axis=2);unit_q=q/norm[:,:,None];scales=norm*norm
    hemisphere_flips=0
    for bone in range(44):
        for sample in range(1,60):
            if unit_q[sample-1,bone]@unit_q[sample,bone]<0:unit_q[sample,bone]*=-1;hemisphere_flips+=1
    scale=float(B[0,0,0]);C=np.diag([scale,scale,scale,1]);inverse_C=np.linalg.inv(C)
    joint_bind=np.asarray([C@np.linalg.inv(b.astype(float))for b in B])
    local_bind=np.asarray([joint_bind[i]if p<0 else np.linalg.inv(joint_bind[p])@joint_bind[i]for i,p in enumerate(parents)])
    vertices=[v for packet in metadata['packets']for v in packet['vertices']]
    if len(vertices)!=3456:raise ValueError('original vertex inventory changed')
    source_position=np.asarray([v['position_raw']for v in vertices],dtype=float)/32768
    position=source_position*scale
    uv=np.asarray([v['uv_raw']for v in vertices],dtype=float)/32768
    normals=np.asarray([v['normal_raw']for v in vertices],dtype=float)
    normal_lengths=np.linalg.norm(normals,axis=1)
    if np.any(normal_lengths==0):raise ValueError('zero source normal: omit or explicitly handle before claiming unit glTF normals')
    normals/=normal_lengths[:,None]
    joints=np.zeros((3456,4),dtype=np.uint16);raw_weights=np.zeros((3456,4),dtype=float)
    original_influences=[]
    for index,vertex in enumerate(vertices):
        if len(vertex['influences'])>4:raise ValueError('need additional JOINTS/WEIGHTS set, never truncate influences')
        pairs=[]
        for slot,(bone,weight)in enumerate(vertex['influences']):
            joints[index,slot]=bone+1;raw_weights[index,slot]=weight
            raw=int(round(weight*32768))
            if raw/32768!=weight:raise ValueError('source weight is not proven quantized16/32768')
            pairs.append({'source_bone':bone,'weight':weight,'original_uint16':raw})
        original_influences.append(pairs)
    sums=raw_weights.sum(axis=1);weights=raw_weights/sums[:,None]
    times=np.asarray(clip['sample_times_seconds'],dtype='<f4')
    tick_times=np.asarray([(f['ticks']-manifest['frames'][0]['ticks'])/clip['saved_cpu_hz']for f in manifest['frames']],dtype='<f4')
    if not np.array_equal(times,tick_times)or len(times)!=60 or np.any(np.diff(times)<=0):raise ValueError('stored time/capture ticks mismatch')
    buffer=Buffer()
    attributes={'POSITION':buffer.add(position,'VEC3',target=34962,bounds=True),
        'NORMAL':buffer.add(normals,'VEC3',target=34962),'TEXCOORD_0':buffer.add(uv,'VEC2',target=34962),
        'JOINTS_0':buffer.add(joints,'VEC4',5123,target=34962),'WEIGHTS_0':buffer.add(weights,'VEC4',target=34962)}
    inverse_bind=np.asarray([np.eye(4)]+[b.astype(float)@inverse_C for b in B])
    ib_accessor=buffer.add(inverse_bind.transpose(0,2,1).reshape(45,16),'MAT4')
    time_accessor=buffer.add(times,'SCALAR',bounds=True)
    units=float(clip['pc_units_per_original_unit']);floor=float(clip['reference_floor'])
    nodes=[{'name':'Scene_units_and_floor','translation':[0,-floor*units,0],'scale':[units]*3,'children':[1,46],
        'extras':{'synthetic':True,'canonical_units':units,'canonical_floor':floor}},
        {'name':'Source_skeleton_root','children':[r+2 for r in roots],'extras':{'synthetic':True,'reason':'preserves source roots0 and43 without assigning anatomy'}}]
    bind_errors=[]
    for bone in range(44):
        _,fit=srt_fit(local_bind[bone]);bind_errors.append(fit['max_matrix_component_residual'])
        children=[i+2 for i,p in enumerate(parents)if p==bone]
        node={'name':f'source_bone_{bone:02d}','translation':fit['translation'],'rotation':fit['unit_rotation_quaternion_xyzw'],
            'scale':fit['column_scale'],'extras':{'source_index':bone,'source_parent':parents[bone],
                'bind_policy':'algebraic C*inverse(B80), source semantics remain candidate','SRT_projection_max_error':fit['max_matrix_component_residual']}}
        if children:node['children']=children
        nodes.append(node)
    nodes.append({'name':'Aya_source_mesh','mesh':0,'skin':0,'extras':{'source_packets':106,'mesh_transform':'identity; joint transforms determine skinned placement'}})
    animation={'name':'Aya_original_fire_reverse_60_samples','samplers':[],'channels':[],
        'extras':{'source_frames':60,'saved_cpu_hz':clip['saved_cpu_hz'],'preview_policy':'clamp; glTF does not define application playback/loop policy',
            'interpolation_limit':'LINEAR glTF quaternion slerp +TRS differs from affine matrix interpolation between stored source samples'}}
    for bone in range(44):
        for path,values,kind in [('translation',translation[:,bone],'VEC3'),('rotation',unit_q[:,bone],'VEC4'),('scale',np.repeat(scales[:,bone,None],3,axis=1),'VEC3')]:
            output_accessor=buffer.add(values,kind)
            animation['samplers'].append({'input':time_accessor,'output':output_accessor,'interpolation':'LINEAR'})
            animation['channels'].append({'sampler':len(animation['samplers'])-1,'target':{'node':bone+2,'path':path}})
    gltf_materials=[];images=[];samplers=[];textures=[];texture_provenance=[]
    for index,m in enumerate(materials['materials']):
        png=Path(m['png']);raw=png.read_bytes()
        if sha(raw)!=m['png_sha256']:raise ValueError('verified original material PNG changed')
        image=Image.open(png).convert('RGBA')
        if sha(image.tobytes())!=m['rgba_sha256']:raise ValueError('PNG RGBA differs from exact original palette decode')
        filename=f'textures/aya_{index:03d}_{m["rgba_sha256"][:16]}.png';(out/filename).write_bytes(raw)
        params=m['parameters']
        if type(params['cull_enabled']) is not bool or (params['cull_enabled'] and params['cull_mode_raw'] != 0):
            raise ValueError('native identity winding only verified for original GE cull mode0')
        images.append({'uri':filename});samplers.append({'magFilter':9729,'minFilter':9729,
            'wrapS':10497 if params['wrap_u']=='repeat'else 33071,'wrapT':10497 if params['wrap_v']=='repeat'else 33071})
        textures.append({'source':index,'sampler':index})
        gltf_materials.append({'name':f'Aya_original_RGBA_{index:03d}','pbrMetallicRoughness':{'baseColorTexture':{'index':index},
            'baseColorFactor':[1,1,1,1],'metallicFactor':0,'roughnessFactor':1},'extensions':{'KHR_materials_unlit':{}},
            'alphaMode':'BLEND'if params['alpha_blend_enabled']else'MASK'if params['alpha_test_enabled']else'OPAQUE',
            'doubleSided':not params['cull_enabled'],'extras':{'source_material_id':m['material_id'],'original_GE_parameters':params,
                'cull_policy':'original_GE_enable_preserved_native_identity_winding',
                'C_runtime_flags':15,'candidate_policy':'unlit original texture baseline; original GE cull enable preserved; other render states require separate verification',
                'unsupported':['source blended main-pass depth writes','GE colorDouble and complete GE lighting',
                    'C legacy source-local posed-face shade cannot be represented as static glTF COLOR_0 animation','GE cull pixel coverage and nonidentity transforms require runtime verification']}})
        texture_provenance.append({'original':identity(png),'file':filename,'copied_sha256':sha(raw),'RGBA_sha256':m['rgba_sha256']})
    packet_material={}
    for p in materials['packets']:
        if not p['consistent_across_captures']or len(p['runtime_material_indices'])!=1:
            raise ValueError('source packet material is not uniquely verified across captures')
        if p['vertex_sha256']!=metadata['packets'][p['packet']]['vertex_sha256']:
            raise ValueError('material binding geometry differs from source packet')
        packet_material[p['packet']]=p['runtime_material_indices'][0]
    primitives=[];first=0
    for i,p in enumerate(metadata['packets']):
        count=p['vertex_count'];indices=buffer.add(np.arange(first,first+count,dtype=np.uint16),'SCALAR',5123,target=34963)
        primitives.append({'attributes':dict(attributes),'indices':indices,'material':packet_material[i],'mode':4,
            'extras':{'source_draw':i,'first_source_vertex':first,'source_vertex_count':count,'source_vtype':p['vtype'],
                'source_geometry_sha256':p['vertex_sha256'],'source_palette_state':p['palette_state']}})
        first+=count
    provenance={'schema':'aya-native-gltf-provenance/v1','specification':SPEC,'inputs':{'source_clip_report':identity(clip_report_path),**{k:identity(v)for k,v in inputs.items()}},
        'copied_source_records':raw_sources,'copied_original_textures':texture_provenance,
        'source_parent':parents,'source_roots':roots,'source_original_influences':original_influences,
        'source_original_weight_sums':sums.tolist(),'native_weights_explicitly_normalized':True,
        'source_GE_command_words_by_frame_bone':original_ge,'source_nonunit_quaternions_xyzw':q.tolist(),
        'source_quaternion_squared_norm_uniform_scale':scales.tolist(),'source_local_translation_xyz':translation.tolist(),
        'C_rows':C.tolist(),'B80_static_columnmajor_words':[struct.unpack('<16I',np.asarray(b.T,dtype='<f4').tobytes())for b in B],
        'inverse_bind_formula':'IBM_i=B80_i*inverse(C); bind_global_i=C*inverse(B80_i); synthetic root IBM=identity',
        'actual_times_seconds':times.tolist(),'quaternion_hemisphere_flips':hemisphere_flips,
        'bind_local_SRT_projection_max_error':max(bind_errors),'source_texture_resolution':'original RGBA, no HD generation',
        'source_runtime_replaced':False,'UE_import_executed':False,'baseline_source_flags':15,
        'limits':['This is a native skeletal interchange candidate, not a replacement for the verified affine runtime.',
            'Normalized glTF weights intentionally differ from raw PSP weights; raw values/uint16 numerators are preserved here.',
            'Independent float24 GE truncation is not directly expressible by normalized-quaternion SRT tracks.',
            'Between keys, glTF LINEAR rotation uses spherical interpolation and differs from the source replay affine interpolation.',
            'Original blend/depth-write/color policy and posed face shading are not exactly represented by standard unlit glTF.',
            'Reference joint transforms are an algebraic construction from static compensation, not a claim of recovered authored reference-pose semantics.']}
    for key,path in inputs.items():shutil.copyfile(path,out/'raw'/f'input_{key}.json')
    write_json(out/'provenance.json',provenance)
    gltf={'asset':{'version':'2.0','generator':'T3B source SRT candidate exporter; UE importer NOT executed',
        'extras':{'source_provenance':'provenance.json','fidelity':'approximate native interchange; original affine runtime unchanged'}},
        'extensionsUsed':['KHR_materials_unlit'],'scene':0,'scenes':[{'name':'Aya_original_source_candidate','nodes':[0]}],
        'nodes':nodes,'skins':[{'name':'Aya_source_44_plus_synthetic_root','joints':list(range(1,46)),'skeleton':1,'inverseBindMatrices':ib_accessor,
            'extras':{'source_parent':parents,'source_index_to_skin_joint':[i+1 for i in range(44)],'synthetic_skin_joint':0}}],
        'meshes':[{'name':'Aya_original_3456_vertices_106_packets','primitives':primitives,
            'extras':{'original_weight_sums':sums.tolist(),'original_influences':original_influences,'weight_policy':'WEIGHTS_0 normalized explicitly; preserved source weights in extras/provenance'}}],
        'animations':[animation],'materials':gltf_materials,'images':images,'samplers':samplers,'textures':textures,
        'buffers':[{'uri':'aya_native.bin','byteLength':len(buffer.data)}],'bufferViews':buffer.views,'accessors':buffer.accessors}
    (out/'aya_native.bin').write_bytes(buffer.data);write_json(out/'aya_native.gltf',gltf)
    return verify(out/'aya_native.gltf',out/'verification.json')


# Independent decode/evaluation: this path reads serialized JSON/buffer layouts,
# not the exporter vertex arrays, local matrices, hierarchy or its SRT helper.
def verify(gltf_path,report_path):
    gltf=json.loads(gltf_path.read_text(encoding='utf-8'));root=gltf_path.parent
    provenance=json.loads((root/'provenance.json').read_text(encoding='utf-8'))
    subframe_limit='Midpoint comparison is against the C replay GE-affine interpolation convention, not a measurement of the original PSP at unobserved subframes.'
    if subframe_limit not in provenance['limits']:provenance['limits'].append(subframe_limit)
    buffers=[(root/b['uri']).read_bytes()for b in gltf['buffers']]
    def accessor(index):
        a=gltf['accessors'][index];view=gltf['bufferViews'][a['bufferView']]
        code,width={5126:('f',4),5123:('H',2)}[a['componentType']];components={'SCALAR':1,'VEC2':2,'VEC3':3,'VEC4':4,'MAT4':16}[a['type']]
        stride=view.get('byteStride',width*components);offset=view.get('byteOffset',0)+a.get('byteOffset',0);blob=buffers[view['buffer']]
        rows=[struct.unpack_from('<'+code*components,blob,offset+i*stride)for i in range(a['count'])]
        return np.asarray(rows,dtype=float)
    def rotation(q):
        q=np.asarray(q)/np.linalg.norm(q);v=q[:3];w=q[3]
        # Vector quaternion rotation, rather than the export H(q) equation.
        columns=[]
        for axis in np.eye(3):columns.append(axis+2*np.cross(v,np.cross(v,axis)+w*axis))
        return np.asarray(columns).T
    def trs(node):
        result=np.eye(4);result[:3,:3]=rotation(node.get('rotation',[0,0,0,1]))@np.diag(node.get('scale',[1,1,1]));result[:3,3]=node.get('translation',[0,0,0]);return result
    def slerp(a,b,t):
        a=a/np.linalg.norm(a);b=b/np.linalg.norm(b);dot=float(a@b)
        if dot<0:b=-b;dot=-dot
        if dot>0.9995:
            q=(1-t)*a+t*b;return q/np.linalg.norm(q)
        angle=np.arccos(np.clip(dot,-1,1));return(np.sin((1-t)*angle)*a+np.sin(t*angle)*b)/np.sin(angle)
    animation=gltf['animations'][0];track=[]
    for channel in animation['channels']:
        s=animation['samplers'][channel['sampler']];track.append((channel['target']['node'],channel['target']['path'],accessor(s['input'])[:,0],accessor(s['output'])))
    nodes=gltf['nodes'];parents={}
    for i,node in enumerate(nodes):
        for child in node.get('children',[]):
            if child in parents:raise ValueError('glTF hierarchy has multiple parents')
            parents[child]=i
    def global_matrices(seconds=None):
        current=copy.deepcopy(nodes)
        if seconds is not None:
            for node,path,times,values in track:
                right=int(np.searchsorted(times,seconds,side='right'));lo=max(0,min(len(times)-1,right-1));hi=min(len(times)-1,lo+1)
                f=0 if hi==lo else np.clip((seconds-times[lo])/(times[hi]-times[lo]),0,1)
                value=slerp(values[lo],values[hi],f)if path=='rotation'else(1-f)*values[lo]+f*values[hi]
                current[node][path]=value
        result={}
        def get(i):
            if i not in result:result[i]=(get(parents[i])if i in parents else np.eye(4))@trs(current[i])
            return result[i]
        return np.asarray([get(i)for i in range(len(nodes))])
    primitives=gltf['meshes'][0]['primitives'];attrs=primitives[0]['attributes']
    position=accessor(attrs['POSITION']);uv=accessor(attrs['TEXCOORD_0']);weights=accessor(attrs['WEIGHTS_0']);joints=accessor(attrs['JOINTS_0']).astype(int)
    skin=gltf['skins'][0];IBM=accessor(skin['inverseBindMatrices']).reshape(45,4,4).transpose(0,2,1)
    if not np.array_equal(IBM[:,3,:],np.tile([0,0,0,1],(45,1))):raise ValueError('inverseBindMatrices fourth row is not affine')
    times=track[0][2];original_influences=provenance['source_original_influences']
    raw_weight=np.zeros_like(weights)
    for index,pairs in enumerate(original_influences):
        for slot,pair in enumerate(pairs):
            if joints[index,slot]!=pair['source_bone']+1:raise ValueError('joint mapping lost source index')
            if pair['weight']!=pair['original_uint16']/32768:raise ValueError('raw weight provenance changed')
            raw_weight[index,slot]=pair['weight']
    normalized_expected=raw_weight/raw_weight.sum(axis=1)[:,None]
    if not np.array_equal(weights.astype('<f4'),normalized_expected.astype('<f4')):raise ValueError('candidate weight policy not explicit normalization')
    if not np.array_equal(times.astype('<f4'),np.asarray(provenance['actual_times_seconds'],dtype='<f4')):raise ValueError('animation timestamps changed')
    if len(times)!=60 or len(primitives)!=106 or len(position)!=3456 or len(skin['joints'])!=45:raise ValueError('native candidate inventory mismatch')
    for row,weight in zip(joints,weights):
        active=row[weight>0]
        if len(set(active.tolist()))!=len(active):raise ValueError('duplicate nonzero glTF joint influence')
    for i,buffer in enumerate(gltf['buffers']):
        if buffer['byteLength']!=len(buffers[i]):raise ValueError('glTF buffer byteLength mismatch')
    for view in gltf['bufferViews']:
        if view.get('byteOffset',0)%4 or view.get('byteOffset',0)+view['byteLength']>len(buffers[view['buffer']]):raise ValueError('unaligned or out-of-bounds bufferView')
    all_indices=[]
    for i,p in enumerate(primitives):
        if p['mode']!=4 or p['attributes']!=attrs:raise ValueError('primitive attribute/topology drift')
        indices=accessor(p['indices'])[:,0].astype(int);expected=p['extras']
        if list(indices)!=list(range(expected['first_source_vertex'],expected['first_source_vertex']+expected['source_vertex_count'])):raise ValueError('source draw order changed')
        all_indices.extend(indices.tolist())
    if all_indices!=list(range(3456)):raise ValueError('mesh coverage differs from original3456 vertices')
    metadata=json.loads((root/'raw/input_metadata.json').read_text(encoding='utf-8'))
    vertices=[v for p in metadata['packets']for v in p['vertices']]
    raw_pos=np.asarray([v['position_raw']for v in vertices],dtype=float)/32768
    raw_uv=np.asarray([v['uv_raw']for v in vertices],dtype=float)/32768
    raw_normal=np.asarray([v['normal_raw']for v in vertices],dtype=float)
    unit_normal=raw_normal/np.linalg.norm(raw_normal,axis=1)[:,None]
    decoded_normal=accessor(attrs['NORMAL'])
    if not np.array_equal(decoded_normal.astype('<f4'),unit_normal.astype('<f4')):raise ValueError('glTF normal policy differs from explicit unit normalization of raw normals')
    C=np.asarray(provenance['C_rows']);scale=float(C[0,0])
    if not np.array_equal(position.astype('<f4'),(raw_pos*scale).astype('<f4'))or not np.array_equal(uv.astype('<f4'),raw_uv.astype('<f4')):raise ValueError('position C mapping or original UV changed')
    units=float(nodes[0]['extras']['canonical_units']);floor=float(nodes[0]['extras']['canonical_floor'])
    def evaluate(seconds,chosen_weights):
        global_=global_matrices(seconds);matrices=global_[skin['joints']]@IBM
        result=np.zeros((3456,3))
        for slot in range(4):result+=chosen_weights[:,slot,None]*(np.einsum('vij,vj->vi',matrices[joints[:,slot],:3,:3],position)+matrices[joints[:,slot],:3,3])
        return result
    original_GE=[];checks=[];normalization_only=[];native_unquantized=[];native_vs_normGE=[]
    per_vertex={key:np.zeros(3456)for key in ['native_vs_source_GE','weight_normalization_only','native_vs_same_weights_GE','native_vs_G40_B80','midpoint_vs_GE_affine']}
    worst_frame=np.zeros(3456,dtype=int);worst_midpoint=np.zeros(3456,dtype=int)
    all_error_vectors=[]
    for sample,entry in enumerate(provenance['copied_source_records']):
        raw=(root/entry['file']).read_bytes()
        if sha(raw)!=entry['sha256']:raise ValueError('copied original source records changed')
        source_float=np.frombuffer(raw,dtype='<f4').reshape(44,76).astype(float)
        for node,path,input_times,values in track:
            bone=node-2
            if path=='translation':expected=source_float[bone,4:7]
            elif path=='scale':expected=np.repeat(np.dot(source_float[bone,:4],source_float[bone,:4]),3)
            else:
                expected=source_float[bone,:4]/np.linalg.norm(source_float[bone,:4])
                if np.dot(expected,values[sample])<0:expected=-expected
            if not np.array_equal(values[sample].astype('<f4'),expected.astype('<f4')):raise ValueError('serialized TRS channel does not preserve all44 raw source bone tracks')
        words=np.frombuffer(raw,dtype='<u4').reshape(44,76);GE=[]
        for i in range(44):
            value=((words[i,48:60]&0xffffff)<<8).copy().view('<f4');m=np.eye(4);m[:3]=value.reshape(3,4,order='F');GE.append(m)
        GE=np.asarray(GE);original_GE.append(GE)
        source_points=np.zeros_like(raw_pos);normalized_points=np.zeros_like(raw_pos)
        for slot in range(4):
            indices=np.maximum(joints[:,slot]-1,0)
            transformed=np.einsum('vij,vj->vi',GE[indices,:3,:3],raw_pos)+GE[indices,:3,3]
            source_points+=raw_weight[:,slot,None]*transformed;normalized_points+=weights[:,slot,None]*transformed
        original_pc=source_points*units;original_pc[:,1]-=floor*units
        normalized_pc=normalized_points*units;normalized_pc[:,1]-=floor*units
        native=evaluate(float(times[sample]),weights)
        diff=native-original_pc
        all_error_vectors.append(diff)
        error=np.linalg.norm(diff,axis=1);new=error>per_vertex['native_vs_source_GE'];worst_frame[new]=sample
        per_vertex['native_vs_source_GE']=np.maximum(per_vertex['native_vs_source_GE'],error)
        checks.append({'frame':sample,'vertices':3456,'max_euclidean_PC_units':float(np.linalg.norm(diff,axis=1).max()),'max_component_PC_units':float(abs(diff).max())})
        normalization_only.append(float(np.linalg.norm(normalized_pc-original_pc,axis=1).max()))
        native_vs_normGE.append(float(np.linalg.norm(native-normalized_pc,axis=1).max()))
        per_vertex['weight_normalization_only']=np.maximum(per_vertex['weight_normalization_only'],np.linalg.norm(normalized_pc-original_pc,axis=1))
        per_vertex['native_vs_same_weights_GE']=np.maximum(per_vertex['native_vs_same_weights_GE'],np.linalg.norm(native-normalized_pc,axis=1))
        raw_values=words.copy().view('<f4');G=raw_values[:,16:32].reshape(44,4,4).transpose(0,2,1);B=raw_values[:,32:48].reshape(44,4,4).transpose(0,2,1)
        product=G.astype(float)@B.astype(float);points=np.zeros_like(raw_pos)
        for slot in range(4):
            indices=np.maximum(joints[:,slot]-1,0);transformed=np.einsum('vij,vj->vi',product[indices,:3,:3],raw_pos)+product[indices,:3,3]
            points+=weights[:,slot,None]*transformed
        points*=units;points[:,1]-=floor*units
        native_unquantized.append(float(np.linalg.norm(native-points,axis=1).max()))
        per_vertex['native_vs_G40_B80']=np.maximum(per_vertex['native_vs_G40_B80'],np.linalg.norm(native-points,axis=1))
    midpoint=[]
    for sample in range(59):
        time=(times[sample]+times[sample+1])/2;GE=(original_GE[sample]+original_GE[sample+1])/2
        points=np.zeros_like(raw_pos)
        for slot in range(4):
            indices=np.maximum(joints[:,slot]-1,0);transformed=np.einsum('vij,vj->vi',GE[indices,:3,:3],raw_pos)+GE[indices,:3,3]
            points+=raw_weight[:,slot,None]*transformed
        points*=units;points[:,1]-=floor*units
        errors=np.linalg.norm(evaluate(float(time),weights)-points,axis=1)
        new=errors>per_vertex['midpoint_vs_GE_affine'];worst_midpoint[new]=sample
        per_vertex['midpoint_vs_GE_affine']=np.maximum(per_vertex['midpoint_vs_GE_affine'],errors)
        vertex=int(np.argmax(errors))
        affected=original_influences[vertex]
        midpoint.append({'interval_start_frame':sample,'midpoint_seconds':float(time),'vertex':vertex,
            'maximum_PC_units':float(errors[vertex]),'source_influences':affected,
            'source_local_quaternion_dot_to_next':{str(pair['source_bone']):float(np.asarray(provenance['source_nonunit_quaternions_xyzw'][sample][pair['source_bone']])@np.asarray(provenance['source_nonunit_quaternions_xyzw'][sample+1][pair['source_bone']]))for pair in affected}})
    texture_checks=[]
    for description,image in zip(provenance['copied_original_textures'],gltf['images']):
        path=root/image['uri'];rgba=Image.open(path).convert('RGBA')
        if sha(path.read_bytes())!=description['copied_sha256']or sha(rgba.tobytes())!=description['RGBA_sha256']:raise ValueError('original RGBA texture changed')
        texture_checks.append({'image':image['uri'],'RGBA_exact':True,'width':rgba.width,'height':rgba.height})
    cull_checks=[]
    for material in gltf['materials']:
        original=material['extras']['original_GE_parameters']
        matches=material.get('doubleSided',False)==(not original['cull_enabled'])
        if material['extras'].get('cull_policy')=='original_GE_enable_preserved_native_identity_winding' and not matches:
            raise ValueError('serialized native culling differs from retained original GE state')
        cull_checks.append({'source_material_id':material['extras']['source_material_id'],
            'source_cull_enabled':original['cull_enabled'],'source_cull_mode':original['cull_mode_raw'],
            'serialized_doubleSided':material.get('doubleSided',False),'source_cull_enable_matches':matches})
    # Query only already installed modules; do not download or install a validator.
    node=shutil.which('node');validator={'executed':False,'reason':'No installed Khronos gltf-validator module found; no dependencies installed.'}
    if node:
        probe=subprocess.run([node,'-e',"try{process.stdout.write(require.resolve('gltf-validator'))}catch(e){process.exitCode=3}"],cwd=root,capture_output=True,text=True,encoding='utf-8')
        if probe.returncode==0:
            module=probe.stdout.strip()
            program="const fs=require('fs'),p=require('path'),v=require(process.argv[1]);const f=process.argv[2];v.validateBytes(new Uint8Array(fs.readFileSync(f)),{uri:p.basename(f),externalResourceFunction:u=>Promise.resolve(new Uint8Array(fs.readFileSync(p.resolve(p.dirname(f),decodeURIComponent(u)))))}).then(r=>fs.writeFileSync(process.argv[3],JSON.stringify(r,null,2))).catch(e=>{process.stderr.write(String(e));process.exitCode=1});"
            validation_path=root/'khronos_validator.json'
            run=subprocess.run([node,'-e',program,module,str(gltf_path.resolve()),str(validation_path.resolve())],cwd=root,capture_output=True,text=True,encoding='utf-8')
            validator={'executed':True,'exit_code':run.returncode,'module':module,'stderr':run.stderr,'report':str(validation_path)}
            if run.returncode==0:
                data=json.loads(validation_path.read_text(encoding='utf-8'));validator['issues']=data['issues']
    bind_globals=global_matrices();bind_product=bind_globals[skin['joints']]@IBM
    source_frame_error=max(checks,key=lambda r:r['max_euclidean_PC_units'])
    csv_path=root/'per_vertex_errors.csv'
    with csv_path.open('w',encoding='utf-8',newline='')as stream:
        writer=csv.writer(stream);writer.writerow(['source_vertex','raw_weight_sum','worst_keyframe','native_vs_source_GE_max_PC','weight_normalization_only_max_PC',
            'native_vs_same_normalized_weights_GE_max_PC','native_vs_G40_B80_same_weights_max_PC','worst_midpoint_start_frame','midpoint_vs_GE_affine_max_PC'])
        for i in range(3456):writer.writerow([i,float(raw_weight[i].sum()),int(worst_frame[i]),float(per_vertex['native_vs_source_GE'][i]),
            float(per_vertex['weight_normalization_only'][i]),float(per_vertex['native_vs_same_weights_GE'][i]),float(per_vertex['native_vs_G40_B80'][i]),int(worst_midpoint[i]),float(per_vertex['midpoint_vs_GE_affine'][i])])
    error_array=root/'all_keyframe_error_vectors_PC.npy';np.save(error_array,np.asarray(all_error_vectors,dtype='<f8'),allow_pickle=False)
    report={'schema':'aya-native-gltf-verification/v1','decode_path':'serialized accessor/struct unpack + independent vector-quaternion rotation and scene traversal; no exporter pose arrays used',
        'artifact':identity(gltf_path),'binary':identity(root/gltf['buffers'][0]['uri']),'provenance':identity(root/'provenance.json'),
        'standard':'glTF2.0 +KHR_materials_unlit','specification':SPEC,'vertices':3456,'primitives':106,'source_bones':44,'synthetic_joints':1,
        'skin_joints':45,'sample_times':60,'animation_channels':132,'all_keyframe_vertex_comparisons':60*3456,
        'all_midpoint_vertex_comparisons':59*3456,'primitive_original_order_exact':True,'raw_UV_float32_exact':True,
        'source_normals_explicitly_unit_normalized':True,'maximum_unit_normal_length_error':float(abs(np.linalg.norm(decoded_normal,axis=1)-1).max()),
        'raw_source_copies_sha_exact':True,'source_raw_weights_preserved_in_extras':True,'native_weights_explicitly_normalized':True,
        'maximum_FLOAT_weight_sum_error':float(abs(weights.sum(axis=1)-1).max()),'original_weight_sum_range':[float(raw_weight.sum(axis=1).min()),float(raw_weight.sum(axis=1).max())],
        'maximum_keyframe_error_vs_source_GE':source_frame_error,
        'maximum_keyframe_error_vs_GE_with_same_normalized_weights_PC':max(native_vs_normGE),
        'maximum_keyframe_error_vs_unquantized_G40_B80_with_same_weights_PC':max(native_unquantized),
        'maximum_weight_normalization_only_error_PC':max(normalization_only),
        'maximum_between_key_midpoint_error_vs_GE_affine_PC':max(p['maximum_PC_units']for p in midpoint),
        'worst_midpoint_example':max(midpoint,key=lambda p:p['maximum_PC_units']),
        'midpoint_comparison_limit':subframe_limit,
        'per_vertex_errors':identity(csv_path),'all_keyframe_error_vectors':identity(error_array),
        'all_error_vectors_shape':[60,3456,3],'all_error_vectors_convention':'glTF decoded worldPC minus original GE weighted PC, float64',
        'bind_default_inverse_product_max_error':float(abs(bind_product[1:]-bind_globals[0]).max()),
        'per_frame_errors':checks,'texture_checks':texture_checks,'material_cull_checks':cull_checks,
        'all_original_cull_enable_flags_preserved':all(c['source_cull_enable_matches']for c in cull_checks),'Khronos_validator':validator,
        'all44_source_TRS_channels_checked_against_raw_snapshots':True,'basic_buffer_alignment_and_skin_attribute_checks_passed':True,
        'numerical_candidate_check_passed':max(native_unquantized)<2e-6 and float(abs(weights.sum(axis=1)-1).max())<6e-7,
        'lossless_vs_source_GE':False,'UE_import_executed':False,'existing_affine_runtime_replaced':False,'limitations':provenance['limits']}
    write_json(report_path,report)
    md=['# Aya native glTF candidate','',
        'This is a reviewable native-SRT interchange candidate. The verified affine source runtime remains unchanged. No UE importer/editor was run.','',
        '- Asset: `aya_native.gltf` +`aya_native.bin`; original-resolution PNGs in `textures/`.',
        '- One synthetic skeleton root preserves both source roots0 and43; 44 original indices remain unchanged in provenance.',
        '- 106 original draw primitives,3456 original vertices,60 actual source times,132 TRS channels.',
        '- Runtime weights are explicitly normalized for standard glTF; original weights/uint16 numerators/sums remain in mesh extras and `provenance.json`.',
        '- All raw44-record snapshots (including float24 commands) remain byte-identical in `raw/`.','',
        '- `per_vertex_errors.csv` gives every vertex maximum errors/attribution across all keys; `all_keyframe_error_vectors_PC.npy` stores all60x3456x3 signed PC error vectors.',
        '- Midpoint differences compare with the existing C replay GE-affine interpolation, not measured original PSP subframes. Original intermediate subframe motion was not sampled.',
        '- Joint/node map: scene node0 units/floor; synthetic skeleton joint node1; source bone i node(i+2), skin-joint(i+1); mesh node46. Skin0 IBM accessor5; shared60-time accessor6.',
        '- Provenance pointers: `asset.extras.source_provenance`, `skins[0].extras.source_parent/source_index_to_skin_joint`, `meshes[0].extras.original_influences/original_weight_sums`, `materials[*].extras.original_GE_parameters`.','',
        '- Primitives share global POSITION/NORMAL/UV/JOINTS/WEIGHTS accessors0..4 and have individual source-range index accessors;3456 is the preserved unique source-vertex inventory, not a measured UE-imported vertex count.',
        '- glTF NORMAL is explicitly unit-normalized from original signed-byte directions; raw vectors remain in `raw/input_metadata.json`.','',
        '## Independent decoded numerical verification','', '```json',json.dumps({k:report[k]for k in [
            'maximum_keyframe_error_vs_source_GE','maximum_keyframe_error_vs_GE_with_same_normalized_weights_PC',
            'maximum_keyframe_error_vs_unquantized_G40_B80_with_same_weights_PC','maximum_weight_normalization_only_error_PC',
            'maximum_between_key_midpoint_error_vs_GE_affine_PC','worst_midpoint_example','maximum_FLOAT_weight_sum_error','Khronos_validator',
            'numerical_candidate_check_passed']},indent=2),'```','',
        '## Fidelity limits','']+['- '+s for s in provenance['limits']]+['',
        'Khronos specification: '+SPEC,'',
        'Reproduce from the workspace root:','',
        '```powershell',
        "& 'C:\\Users\\25105\\AppData\\Local\\Programs\\Python\\Python313\\python.exe' -X utf8 '.\\work\\psp_parse\\tools\\export_aya_native_gltf.py' --source-clip-report '.\\work\\psp_parse\\out\\AYA_FIRE_REVERSE_SOURCE_SKIN_EXPORT.json' --out '.\\work\\psp_parse\\out\\AYA_NATIVE_GLTF_20261020'",'```']
    (root/'README.md').write_text('\n'.join(md)+'\n',encoding='utf-8')
    if not report['numerical_candidate_check_passed']:raise ValueError('native interchange candidate failed decoded numerical checks; inspect preserved report')
    print(json.dumps({k:report[k]for k in ['artifact','vertices','primitives','skin_joints','sample_times','maximum_keyframe_error_vs_source_GE',
        'maximum_keyframe_error_vs_unquantized_G40_B80_with_same_weights_PC','maximum_between_key_midpoint_error_vs_GE_affine_PC','Khronos_validator','numerical_candidate_check_passed']},ensure_ascii=False))
    return report


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--source-clip-report',type=Path)
    p.add_argument('--out',type=Path);p.add_argument('--verify-only',type=Path)
    a=p.parse_args()
    if a.verify_only:verify(a.verify_only,a.verify_only.parent/'verification.json')
    elif a.source_clip_report and a.out:export(a.source_clip_report,a.out)
    else:p.error('provide --source-clip-report and --out, or --verify-only asset.gltf')
