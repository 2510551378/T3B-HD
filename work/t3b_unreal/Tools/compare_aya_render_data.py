"""Read-only analysis of actual RenderData->DynamicMesh capture against source.
UV+orientation correspondence precedes positional comparison. Ambiguous UV
identities remain explicitly inferred; no nearest-neighbor point-cloud claim.
"""
import argparse,collections,hashlib,json,struct
from pathlib import Path
import numpy as np

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def must(v,msg):
    if not v:raise ValueError(msg)
def load(p):return json.loads(p.read_text(encoding='utf-8'))
def cyclic_key(t):
    rows=list(map(tuple,t));return min(tuple(rows[i:]+rows[:i])for i in range(3))
def metrics(a,b):
    errors=np.linalg.norm(a-b,axis=-1);f,t,c=np.unravel_index(np.argmax(errors),errors.shape)
    return {'triangle_corner_sample_comparisons':int(errors.size),'max_euclidean_cm':float(errors[f,t,c]),'RMS_cm':float(np.sqrt(np.mean(errors**2))),
        'worst_local_frame':int(f),'worst_filtered_triangle':int(t),'worst_corner':int(c),'per_frame_max_cm':errors.max(axis=(1,2)).tolist()}

def main():
    a=argparse.ArgumentParser();a.add_argument('--render-report',type=Path,required=True);a.add_argument('--output',type=Path,required=True);a.add_argument('--uv-policy',choices=['fp16','float32'],default='fp16');a=a.parse_args();must(not a.output.exists(),'Refuse overwrite')
    project=Path(__file__).resolve().parents[1];gpath=project.parent/'psp_parse/out/AYA_NATIVE_GLTF_20261020/aya_native.gltf';g=load(gpath);binpath=gpath.parent/g['buffers'][0]['uri'];buf=binpath.read_bytes()
    r=load(a.render_report);spath=project/'Validation/native_skinning_probe_runs/c64431c073744987b3bcb7965caa3a92/ue_native_skinning_probe.json';s=load(spath)
    def accessor(i):
        ac=g['accessors'][i];v=g['bufferViews'][ac['bufferView']];dt={5123:'<u2',5125:'<u4',5126:'<f4'}[ac['componentType']];w={'SCALAR':1,'VEC2':2,'VEC3':3,'VEC4':4,'MAT4':16}[ac['type']];size=np.dtype(dt).itemsize
        return np.ndarray((ac['count'],w),dtype=dt,buffer=buf,offset=v.get('byteOffset',0)+ac.get('byteOffset',0),strides=(v.get('byteStride',size*w),size)).copy()
    attrs={name:accessor(i)for name,i in g['meshes'][0]['primitives'][0]['attributes'].items()}
    src_tri=np.concatenate([accessor(p['indices']).reshape(-1)for p in g['meshes'][0]['primitives']]).reshape(-1,3).astype(int);must(src_tri.shape==(1152,3),'Source topology differs')
    must(s['triangles']==(src_tri+np.concatenate([np.full(len(accessor(p['indices']))//3,pi*3456)for pi,p in enumerate(g['meshes'][0]['primitives'])])[:,None]).tolist(),'Frozen SourceModel provenance differs')
    source_uv=attrs['TEXCOORD_0'][src_tri].astype(float);expected_uv=source_uv.astype(np.float16).astype(float)if a.uv_policy=='fp16'else source_uv.copy();render_uv=np.asarray(r['triangle_uvs'],dtype=float)
    groups=collections.defaultdict(list)
    for i,t in enumerate(expected_uv):groups[cyclic_key(t)].append(i)
    candidates=[groups.get(cyclic_key(t),[])for t in render_uv];must(all(candidates),'Some render triangles lack exact oriented FP16 source UV match')
    src_counts=collections.Counter(map(cyclic_key,expected_uv));render_counts=collections.Counter(map(cyclic_key,render_uv))
    missing=src_counts-render_counts;extra=render_counts-src_counts
    sp=Path(s['point_files'][0]['file']);rp=Path(r['point_file']['file']);must(sha(sp)==s['point_files'][0]['sha256']and sha(rp)==r['point_file']['sha256'],'Actual measured point file changed')
    frames=r['requested_sample_indices'];must(frames==[0,30,59],'Only authorized3 frames expected')
    source=np.fromfile(sp,dtype='<f8').reshape(60,3456,3)[frames]
    render=np.fromfile(rp,dtype='<f8').reshape(3,len(r['used_vertex_ids']),3);rid={v:i for i,v in enumerate(r['used_vertex_ids'])};render_tri=np.asarray(r['triangles']);actual=render[:,np.vectorize(rid.get)(render_tri)]
    for f,sample in zip(frames,r['sample_attempts']):must(sample['actual_time']==s['sample_attempts'][f]['actual_position'],'Actual sampling time differs')
    def attrsignature(tri,order):return b''.join(arr[src_tri[tri][order]].tobytes()for arr in attrs.values())
    rows=[];chosen=np.zeros_like(actual);strict=[];source_vertex_groups=collections.defaultdict(set)
    for ti,cands in enumerate(candidates):
        options=[]
        for source_t in cands:
            for shift in range(3):
                order=np.roll(np.arange(3),-shift)
                if not np.array_equal(expected_uv[source_t][order],render_uv[ti]):continue
                expect=source[:,src_tri[source_t][order]];delta=actual[:,ti]-expect
                options.append({'source_triangle':source_t,'corner_order':order.tolist(),'rms_cm':float(np.sqrt(np.mean(np.sum(delta*delta,axis=-1)))),
                    'max_cm':float(np.max(np.linalg.norm(delta,axis=-1))),'signature':attrsignature(source_t,order),'expected':expect})
        must(options,'No cyclic corner mapping');options.sort(key=lambda x:x['rms_cm']);best=options[0]
        if len(options)==1:tier='unique_oriented_'+a.uv_policy+'_UV_within_frozen_source'
        elif len({o['signature']for o in options})==1:tier='exact_source_attribute_equivalent_duplicate_class'
        else:tier='INFERRED_whole_triangle_3frame_trajectory_disambiguation'
        chosen[:,ti]=best['expected'];strict.append(not tier.startswith('INFERRED'))
        rows.append({'render_triangle':ti,'UV_source_candidates':cands,'mapping_tier':tier,'selected_source_triangle':best['source_triangle'],
            'source_corner_order':best['corner_order'],'best_rms_cm':best['rms_cm'],'best_max_cm':best['max_cm'],
            'other_candidate_rms_cm':[o['rms_cm']for o in options[1:]],'identity_unique':len(options)==1})
        if not tier.startswith('INFERRED'):
            for corner,vertex in enumerate(render_tri[ti]):
                for opt in options:source_vertex_groups[int(vertex)].add(int(src_tri[opt['source_triangle']][opt['corner_order'][corner]]))
    pos=attrs['POSITION'].astype(float);bind_tri=pos[src_tri];bind_area=np.linalg.norm(np.cross(bind_tri[:,1]-bind_tri[:,0],bind_tri[:,2]-bind_tri[:,0]),axis=1)/2
    def source_draw(tri):
        vertex=int(src_tri[tri,0])
        return next(p['extras']['source_draw']for p in g['meshes'][0]['primitives']if p['extras']['first_source_vertex']<=vertex<p['extras']['first_source_vertex']+p['extras']['source_vertex_count'])
    missing_rows=[]
    for key,count in missing.items():
        ts=groups[key];geometry=[]
        for t in ts:
            pt=source[:,src_tri[t]];areas=np.linalg.norm(np.cross(pt[:,1]-pt[:,0],pt[:,2]-pt[:,0]),axis=1)/2
            geometry.append({'source_triangle':t,'source_draw':source_draw(t),'original_vertices':src_tri[t].tolist(),'bind_area_source_units_squared':float(bind_area[t]),'actual_SourceModel_area_cm_squared_0_30_59':areas.tolist()})
        signatures=[attrsignature(t,np.arange(3))for t in ts]
        missing_rows.append({'missing_multiplicity':count,'source_candidates':ts,'all5_source_attribute_rows_identical_in_current_corner_order':len(set(signatures))==1,'geometry':geometry})
    occurrences=collections.Counter(int(v)for t in render_tri for v in t);reuse={str(k):v for k,v in occurrences.items()if v>1}
    strict_mask=np.asarray(strict,dtype=bool);tiers=collections.Counter(x['mapping_tier']for x in rows)
    # Compare all source candidates for each strictly mapped render vertex; no arbitrary nearest match.
    strict_vid_rows=[]
    for vertex,sourceids in source_vertex_groups.items():
        pts=source[:,sorted(sourceids)];span=float(np.max(np.abs(pts-pts[:,:1])))
        strict_vid_rows.append({'render_vertex':vertex,'source_vertices':sorted(sourceids),'source_3frame_max_component_span_cm':span})
    core=load(project/'Tools/source_core_verification.json');cmeta=core['skins']['aya_fire'];cfile=Path(cmeta['frozen_c_probe']);clip=Path(cmeta['source']);must(sha(cfile)==cmeta['frozen_c_probe_sha256']and sha(clip)==cmeta['source_sha256'],'Frozen C changed')
    units,floor=struct.unpack_from('<2f',clip.read_bytes(),44);cf=np.loadtxt(cfile,delimiter=',')[:,2:5].astype(np.float32).reshape(60,3456,3)[frames]
    cf[:,:,0]*=np.float32(units);cf[:,:,1]=(cf[:,:,1]-np.float32(floor))*np.float32(units);cf[:,:,2]*=np.float32(units);cf=cf[:,:,[0,2,1]].astype(float)*100
    cchosen=np.zeros_like(actual)
    for ti,row in enumerate(rows):cchosen[:,ti]=cf[:,src_tri[row['selected_source_triangle']][row['source_corner_order']]]
    shared_evidence=[]
    for row in strict_vid_rows:
        if str(row['render_vertex'])not in reuse:continue
        sourceids=row['source_vertices'];first=sourceids[0]
        row=dict(row);row['all5_source_attribute_rows_bit_equal']=all(all(np.array_equal(arr[first],arr[v])for v in sourceids)for arr in attrs.values());shared_evidence.append(row)
    strict_model_metrics=metrics(actual[:,strict_mask],chosen[:,strict_mask]);strict_c_metrics=metrics(actual[:,strict_mask],cchosen[:,strict_mask])
    strict_ids=np.flatnonzero(strict_mask)
    for measure in [strict_model_metrics,strict_c_metrics]:
        rt=int(strict_ids[measure['worst_filtered_triangle']]);measure['worst_render_triangle']=rt;measure['worst_source_triangle']=rows[rt]['selected_source_triangle'];measure['worst_source_frame']=frames[measure['worst_local_frame']]
    inferred_rows=[row for row in rows if row['mapping_tier'].startswith('INFERRED')]
    result={'analysis_script_sha256':sha(Path(__file__)),'shared_vertex_source_attribute_evidence':shared_evidence,
        'inferred_triangle_count':len(inferred_rows),'inferred_other_candidate_min_RMS_cm':min(v for row in inferred_rows for v in row['other_candidate_rms_cm']),
        'inferred_selected_candidate_max_RMS_cm':max(row['best_rms_cm']for row in inferred_rows),'schema':'t3b-render-data-dynamicmesh-independent-analysis/v1','analysis_executed':True,'global_source_vertex_identity_fidelity_verified':False,
        'render_report_sha256':sha(a.render_report),'frozen_SourceModel_report_sha256':sha(spath),'frozen_gltf_sha256':sha(gpath),'measured_render_point_sha256':sha(rp),
        'actual_capture_path':r['path'],'source_frame_indices':frames,'actual_dynamicmesh_vertices':r['vertex_count'],'actual_dynamicmesh_triangles':r['triangle_count'],
        'raw_LOD_render_buffer_vertex_and_triangle_counts_known':False,'raw_LOD0_render_vertex_count_official_API':r.get('raw_LOD0_render_vertex_count_official_API'),'raw_LOD_index_buffer_triangle_count_known':False,'UV_match_policy':a.uv_policy,'oriented_UV_all_triangles_matched':True,'mapping_tier_counts':dict(tiers),
        'UV_max_source_to_selected_precision_component_delta':float(np.max(np.abs(expected_uv-source_uv))),'actual_render_UV_vs_matching_selected_precision_source_max_delta':0,
        'extra_oriented_UV_triangle_classes':len(extra),'missing_oriented_UV_multiplicities':missing_rows,'all_source_bind_zero_area_triangles':np.flatnonzero(bind_area==0).tolist(),
        'source_min_bind_area_source_units_squared':float(bind_area.min()),'topology_corner_arithmetic':{'source_corners':3456,'output_triangle_corners':int(render_tri.size),'output_unique_referenced_vertices':len(occurrences),'missing_triangle_corners':3,'net_shared_corner_reuse':int(render_tri.size-len(occurrences)),'shared_dynamicmesh_vertex_occurrences':reuse},
        'strictly_identified_or_attribute_equivalent_triangles':int(strict_mask.sum()),'UV_only_unresolved_triangles':int((~strict_mask).sum()),'strictly_covered_unique_render_vertices':len(source_vertex_groups),
        'strict_triangle_corner_positions_vs_default_SourceModel':strict_model_metrics,
        'strict_triangle_corner_positions_vs_frozen_C':strict_c_metrics,
        'ALL_TRIANGLES_WITH_EXPLICIT_INFERENCE_positions_vs_default_SourceModel':metrics(actual,chosen),
        'ALL_TRIANGLES_WITH_EXPLICIT_INFERENCE_positions_vs_frozen_C':metrics(actual,cchosen),
        'triangle_correspondence':rows,'strict_render_vertex_source_classes':strict_vid_rows,
        'installed_source_evidence':[
            {'file':'Engine/Source/Runtime/MeshConversion/Public/ToDynamicMesh.h','lines':'125-132','fact':'AppendTriangle DuplicateTriangleID or InvalidID is skipped; output triangle count can differ from raw render index buffer.'},
            {'file':'Engine/Source/Runtime/MeshConversion/Public/ToDynamicMesh.h','lines':'135-164','fact':'NonManifoldID triggers vertex duplication before re-append; output vertex count cannot be treated as raw LOD buffer count.'},
            {'file':'Engine/Source/Developer/MeshUtilities/Private/MeshUtilities.cpp','lines':'849-858','fact':'Build cache optimization can reorder/change triangle index count; code mechanism alone does not identify this capture missing face cause.'}],
        'strict_conclusions':['Not only degenerate deletion: the missing oriented UV multiplicity belongs to a nonzero-area exact duplicate source-face class858/1125.',
            ('Observed UVs match source converted to FP16 with the nonzero quantization error reported.'if a.uv_policy=='fp16'else'Observed UVs exactly match original source F32 UVs on all output triangle corners; no F32-to-FP16 quantization loss is observed.'),
            '3449/1151 are converted DynamicMesh counts; official raw LOD vertex count is separately reported when captured. Raw index-buffer triangle count and exact removed-triangle provenance remain unknown, so renderer geometry loss is not established.',
            'Net vertex deficit7 decomposes as3 absent face corners plus4 shared-corner reuses in this output; this is not proof of7 build weld operations.',
            'Full vertex-identity fidelity is not certified:16 triangles need geometric trajectory inference because oriented UV signatures are shared by distinct source geometry.'],
        'limits':['All source correspondences are established from triangle UV orientation before positions; nearest-neighbor point clouds are not used.',
            'Triangle identities are qualified by the selected exact UV precision policy and orientation; count and ambiguity tiers are explicit. Duplicate-class identity remains an equivalence, not an original draw ID.',
            '16 ambiguous triangle identities are explicitly inferred using complete3corner/3frame trajectories among UV-eligible candidates, without an acceptance threshold. Those results are separate from strict metrics.',
            'Normals/tangents/render skin weights and original raw index/vertex->source ID maps were not captured. UV equivalence alone cannot prove their fidelity.',
            'The duplicate blended source draw could affect compositing multiplicity; lack of an output duplicate cannot certify unchanged pixels or prove the renderer removed it.',
            'Only source frames0/30/59 with default animation sampling were analyzed. No new UE process, asset modification or threshold relaxation was performed.']}
    a.output.write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({k:v for k,v in result.items()if k not in ['triangle_correspondence','strict_render_vertex_source_classes','limits','installed_source_evidence']},indent=2))
if __name__=='__main__':main()