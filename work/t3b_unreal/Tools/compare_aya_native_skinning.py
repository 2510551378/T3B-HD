"""Compare actual UE GeometryScript source-model skinned points with frozen C/glTF.
The UE capture is the measured side; glTF decoding here only builds a reference.
"""
import argparse,hashlib,json,struct
from pathlib import Path
import numpy as np

def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def must(v,msg):
    if not v:raise ValueError(msg)
def trs(node):
    x,y,z,w=node.get('rotation',[0,0,0,1]);s=node.get('scale',[1,1,1]);m=np.eye(4)
    m[:3,:3]=np.array([[1-2*(y*y+z*z),2*(x*y-z*w),2*(x*z+y*w)],[2*(x*y+z*w),1-2*(x*x+z*z),2*(y*z-x*w)],[2*(x*z-y*w),2*(y*z+x*w),1-2*(x*x+y*y)]])@np.diag(s)
    m[:3,3]=node.get('translation',[0,0,0]);return m

def main():
    a=argparse.ArgumentParser();a.add_argument('--ue-report',required=True,type=Path);a.add_argument('--output',required=True,type=Path);a.add_argument('--baseline-report',type=Path);a.add_argument('--capture-gltf',type=Path);a=a.parse_args()
    must(not a.output.exists(),'Refuse to overwrite prior comparison')
    project=Path(__file__).resolve().parents[1];gpath=project.parent/'psp_parse/out/AYA_NATIVE_GLTF_20261020/aya_native.gltf'
    g=json.loads(gpath.read_text(encoding='utf-8'));buf=(gpath.parent/g['buffers'][0]['uri']).read_bytes();r=json.loads(a.ue_report.read_text(encoding='utf-8'))
    def accessor(index):
        t=g['accessors'][index];v=g['bufferViews'][t['bufferView']];dt={5123:'<u2',5125:'<u4',5126:'<f4'}[t['componentType']];width={'SCALAR':1,'VEC2':2,'VEC3':3,'VEC4':4,'MAT4':16}[t['type']];size=np.dtype(dt).itemsize
        return np.ndarray((t['count'],width),dtype=dt,buffer=buf,offset=v.get('byteOffset',0)+t.get('byteOffset',0),strides=(v.get('byteStride',width*size),size)).copy()
    primitive=g['meshes'][0]['primitives'];attrs=primitive[0]['attributes'];vcount=g['accessors'][attrs['POSITION']]['count'];must(vcount==3456,'Frozen vertex count differs')
    ids=np.asarray(r['used_vertex_ids'],dtype=np.int64)
    expected_native_triangles=[];native_to_source={}
    if a.capture_gltf:
        captured=json.loads(a.capture_gltf.read_text(encoding='utf-8'));captured_bin=(a.capture_gltf.parent/captured['buffers'][0]['uri']).read_bytes()
        must(r['source_import_report']['gltf']['sha256']==digest(a.capture_gltf),'Actual imported glTF identity differs from capture mapping input')
        def caccess(index):
            t=captured['accessors'][index];v=captured['bufferViews'][t['bufferView']];dtype={5123:'<u2',5125:'<u4',5126:'<f4'}[t['componentType']];w={'SCALAR':1,'VEC2':2,'VEC3':3,'VEC4':4,'MAT4':16}[t['type']];size=np.dtype(dtype).itemsize
            return np.ndarray((t['count'],w),dtype=dtype,buffer=captured_bin,offset=v.get('byteOffset',0)+t.get('byteOffset',0),strides=(v.get('byteStride',w*size),size)).copy()
        offset=0
        for p in captured['meshes'][0]['primitives']:
            indices=caccess(p['indices']).astype(np.int64).reshape(-1);source_ids=p['extras']['compact_source_vertices'];count=captured['accessors'][p['attributes']['POSITION']]['count']
            must(len(source_ids)==count,'Capture compact source mapping length differs')
            expected_native_triangles.extend((indices+offset).reshape(-1,3).tolist())
            for i,source_id in enumerate(source_ids):native_to_source[offset+i]=source_id
            offset+=count
        must(offset==r['source_description_total_vertices']==3456,'Actual compact UE source-description count differs')
    else:
        for pi,p in enumerate(primitive):
            expected_native_triangles.extend((accessor(p['indices']).astype(np.int64).reshape(-1)+pi*vcount).reshape(-1,3).tolist())
        native_to_source={int(i):int(i)%vcount for i in ids}
    mapped=np.asarray([native_to_source[int(i)]for i in ids]);must(np.array_equal(mapped,np.arange(vcount)),'Actual native referenced point order is not source0..3455')
    must(r['triangles']==expected_native_triangles,'Actual native triangle topology does not prove primitive/source-index mapping')
    uv=accessor(attrs['TEXCOORD_0']).astype(float);source_triangles=np.asarray([[native_to_source[v]for v in tri]for tri in r['triangles']])
    uv_error=float(np.max(np.abs(np.asarray(r['triangle_uvs'])-uv[source_triangles])))
    actual=[]
    for p in r['point_files']:
        path=Path(p['file']);must(digest(path)==p['sha256'],'Actual UE point-file hash differs')
        actual.append(np.fromfile(path,dtype='<f8').reshape(60,3456,3))
    local,aligned=actual
    expected_pc=np.zeros_like(local);skin=g['skins'][0];joints=accessor(attrs['JOINTS_0']).astype(int);weights=accessor(attrs['WEIGHTS_0']).astype(float)
    inv=accessor(skin['inverseBindMatrices']).astype(float).reshape(-1,4,4).transpose(0,2,1);pos=np.column_stack([accessor(attrs['POSITION']).astype(float),np.ones(vcount)])
    parent=[-1]*len(g['nodes'])
    for i,node in enumerate(g['nodes']):
        for ch in node.get('children',[]):parent[ch]=i
    anim=g['animations'][0];channels=[];times=None
    for channel in anim['channels']:
        samp=anim['samplers'][channel['sampler']];t=accessor(samp['input']).reshape(-1)
        if times is None:times=t
        must(np.array_equal(t,times),'Reference animation channels differ in clock')
        channels.append((channel['target']['node'],channel['target']['path'],accessor(samp['output']).astype(float)))
    must(len(times)==60,'Expected60 source times')
    for frame,sample in enumerate(r['sample_attempts']):
        must(abs(sample['actual_position']-float(times[frame]))<2e-6,'Actual UE component did not reach requested source sample')
        nodes=[dict(n)for n in g['nodes']]
        for n,p,v in channels:nodes[n][p]=v[frame]
        localm=[trs(n)for n in nodes];world={}
        def globalm(i):
            if i not in world:world[i]=localm[i]if parent[i]<0 else globalm(parent[i])@localm[i]
            return world[i]
        matrices=np.stack([globalm(n)@inv[i]for i,n in enumerate(skin['joints'])]);posed=np.zeros((vcount,4))
        for j in range(4):posed+=np.einsum('nij,nj->ni',matrices[joints[:,j]],pos)*weights[:,j,None]
        expected_pc[frame]=posed[:,:3]
    core=json.loads((project/'Tools/source_core_verification.json').read_text(encoding='utf-8'));frozen=core['skins']['aya_fire'];probe=Path(frozen['frozen_c_probe']);clip=Path(frozen['source'])
    must(digest(probe)==frozen['frozen_c_probe_sha256']and digest(clip)==frozen['source_sha256'],'Frozen C reference changed')
    c=np.loadtxt(probe,delimiter=',',dtype=float)[:,2:5].astype(np.float32).reshape(60,3456,3);units,floor=struct.unpack_from('<2f',clip.read_bytes(),44)
    c[:,:,0]*=np.float32(units);c[:,:,1]=(c[:,:,1]-np.float32(floor))*np.float32(units);c[:,:,2]*=np.float32(units)
    expected_native=expected_pc[:,:,[0,2,1]]*100.;expected_aligned=expected_pc[:,:,[2,0,1]]*100.;expected_c_aligned=c[:,:,[2,0,1]].astype(float)*100.
    def compare(actual,expected):
        norms=np.linalg.norm(actual-expected,axis=2);f,v=np.unravel_index(np.argmax(norms),norms.shape)
        return {'points':int(norms.size),'max_euclidean_cm':float(norms[f,v]),'rms_cm':float(np.sqrt(np.mean(norms**2))),
            'worst_frame':int(f),'worst_source_vertex':int(v),'actual_cm':actual[f,v].tolist(),'expected_cm':expected[f,v].tolist(),
            'per_frame_max_cm':norms.max(axis=1).tolist()}
    aligned_tri=np.asarray(r['aligned_first_triangle_indices'],dtype=np.int64)
    ntri=len(aligned_tri);base_tri=np.asarray(r['triangles'][:ntri],dtype=np.int64)
    reversed_corners=np.array([1,0,2]);normal_expected=np.asarray(r['first_frame_triangle_normals'][:ntri])[:,reversed_corners,:][:,:,[1,0,2]]
    normal_actual=np.asarray(r['aligned_first_triangle_normals'])
    orientation={'sampled_triangles':ntri,'actual_reflection_reverses_first_two_triangle_indices':bool(np.array_equal(aligned_tri,base_tri[:,reversed_corners])),
        'max_split_normal_component_error_after_corner_reorder':float(np.max(np.abs(normal_actual-normal_expected))),
        'installed_source':'SceneComponentToDynamicMesh.cpp:855 ApplyTransform(...,true); GeometryCore/Private/DynamicMesh/MeshTransforms.cpp:231-233 reverses triangle orientation when det<0',
        'limits':'Only first12 triangles/frame0 split normal readback; not full tangent/binormal/GPU-cull validation.'}
    report={'comparison_script_sha256':digest(Path(__file__)),'orientation_probe':orientation,'schema':'t3b-actual-UE-native-source-model-skinning-comparison/v1','comparison_executed':True,
        'actual_UE_report':str(a.ue_report.resolve()),'actual_UE_report_sha256':digest(a.ue_report),'gltf_sha256':digest(gpath),
        'actual_UE_method':r['skinning_method'],'native_render_buffer_points_verified':False,'native_GPU_pixels_verified':False,
        'referenced_vertices':3456,'native_triangles':1152,'source_index_mapping_proven_by_complete_actual_triangle_topology':True,
        'source_description_total_vertices':r['source_description_total_vertices'],'unreferenced_source_description_vertices':r['source_description_total_vertices']-3456,'max_referenced_source_description_vertex_ID':max(r['used_vertex_ids']),
        'raw_UV_max_component_error':uv_error,'native_source_model_vs_frozen_gltf':compare(local,expected_native),'aligned_UE_source_model_vs_frozen_gltf':compare(aligned,expected_aligned),
        'aligned_UE_source_model_vs_frozen_C':compare(aligned,expected_c_aligned),'actual_UE_reflection_vs_direct_matrix_max_cm':float(np.max(np.abs(aligned-local[:,:,[1,0,2]]))),
        'alignment_matrix_rows':r['alignment']['matrix_rows'],'alignment_determinant':-1,
        'source_pose_times_actually_advanced':all(abs(s['actual_position']-s['requested_time'])<2e-6 for s in r['sample_attempts']),
        'first_last_actual_points_differ_max_cm':float(np.max(np.abs(local[-1]-local[0]))),
        'previous161_and_native3_packages_unchanged':r['previous161_and_native3_packages_unchanged'],
        'limits':['Actual UE CPU source-description skinning is measured, through FSkeletalMeshOperations::GetPosedMesh; this does not substitute Python glTF reference arithmetic for measured UE points.',
            'NullRHI prevents MeshObject/render-buffer/GPU skinning; SourceModel and render-buffer weights/layout may differ.',
            'Measured error includes source-to-glTF weight normalization, source float24 quantization, importer/resampling/compression and CPU skin arithmetic; causes are not individually isolated.',
            'Only1152triangles/3456referenced vertices are compared; any unreferenced source-description vertices are never filled or counted as source geometry. Actual unreferenced count is reported explicitly.',
            'Reflection is applied to a transient component, no old asset or frozen glTF is edited. Render culling/normal/tangent behavior still requires visual verification.',
            'Caffine midpoint3.117cm is not a measurement of unobserved PSP subframes; this capture evaluates original60 sample times.']}
    report['capture_gltf']=str(a.capture_gltf.resolve())if a.capture_gltf else str(gpath)
    report['capture_gltf_sha256']=digest(a.capture_gltf)if a.capture_gltf else digest(gpath)
    report['raw_sampling_control']=r.get('raw_sampling_control')
    if a.baseline_report:
        base=json.loads(a.baseline_report.read_text(encoding='utf-8'))
        must(base['used_vertex_ids']==r['used_vertex_ids']and base['triangles']==r['triangles'],'Control geometry/topology/source mapping differs')
        must([s['requested_time']for s in base['sample_attempts']]==[s['requested_time']for s in r['sample_attempts']],'Control source times differ')
        must(base['actual_material_reference']==r['actual_material_reference'],'Control material differs')
        base_local_path=Path(base['point_files'][0]['file']);base_aligned_path=Path(base['point_files'][1]['file'])
        must(digest(base_local_path)==base['point_files'][0]['sha256']and digest(base_aligned_path)==base['point_files'][1]['sha256'],'Frozen default UE point file changed')
        base_local=np.fromfile(base_local_path,dtype='<f8').reshape(60,3456,3);base_aligned=np.fromfile(base_aligned_path,dtype='<f8').reshape(60,3456,3)
        request=json.loads((a.ue_report.parent/'request.json').read_text(encoding='utf-8-sig'));base_request=json.loads((a.baseline_report.parent/'request.json').read_text(encoding='utf-8-sig'))
        must(request['input_report']==base_request['input_report'],'Control native asset source report differs')
        report['paired_default_control']={'baseline_UE_report':str(a.baseline_report.resolve()),'baseline_UE_report_sha256':digest(a.baseline_report),
            'same_native_import_report':request['input_report'],'same_topology_and_times_and_material':True,
            'raw_vs_default_actual_UE_aligned_points':compare(aligned,base_aligned),
            'default_vs_frozen_gltf':compare(base_local,expected_native),'default_vs_frozen_C':compare(base_aligned,expected_c_aligned),
            'limits':['Default c644 capture used the untouched process default policy; it did not record ForceEvalRawData directly. The separate readonly settings inspection read default0. The raw controlled capture records actual before/after/final values.',
                'A paired actual-point difference demonstrates sensitivity to the process-local raw-sampling directive; it does not isolate which individual ACL quantization track caused an error.',
                'Raw data model still uses the importer-generated uniform key grid; forcing raw does not recover unobserved PSP intermediate frames.']}
    a.output.write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({k:v for k,v in report.items()if k not in ['limits']and not isinstance(v,dict)},indent=2))
    for key in ['native_source_model_vs_frozen_gltf','aligned_UE_source_model_vs_frozen_gltf','aligned_UE_source_model_vs_frozen_C']:print(key,{k:v for k,v in report[key].items()if k!='per_frame_max_cm'})
if __name__=='__main__':main()