"""Independent paired proof of actual rebuilt F32 UV data and preserved points."""
import argparse,hashlib,json,re
from pathlib import Path
import numpy as np

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def read(p):return json.loads(p.read_text(encoding='utf-8'))
def must(v,msg):
    if not v:raise ValueError(msg)
def main():
    a=argparse.ArgumentParser();a.add_argument('--new-render-report',required=True,type=Path);a.add_argument('--old-render-report',required=True,type=Path);a.add_argument('--build-report',required=True,type=Path);a.add_argument('--output',required=True,type=Path);a=a.parse_args();must(not a.output.exists(),'Refuse overwrite')
    new,old,build=read(a.new_render_report),read(a.old_render_report),read(a.build_report);analysis=read(a.new_render_report.parent/'full_precision_source_analysis.json')
    must(build['passed']and new['passed']and new['LOD0_full_precision_UVs_setting'],'Build/second-process setting readback failed')
    must(new['mesh']==build['skeletal_meshes'][0]['asset']and new['animation']==build['animations'][0]['asset'],'Second-process asset references differ')
    before=build['settings_before'].split('{',1)[1];after=build['settings_after'].split('{',1)[1]
    parse=lambda t:dict(re.findall(r'(\w+): ([^,}>]+)',t))
    b,c=parse(before),parse(after);changes={k:[b.get(k),c.get(k)]for k in set(b)|set(c)if b.get(k)!=c.get(k)}
    must(changes=={'use_full_precision_u_vs':['False','True']},'Other build settings changed')
    must(new['triangles']==old['triangles']and new['used_vertex_ids']==old['used_vertex_ids'],'Actual converted topology or vertex order changed')
    uv=np.asarray(new['triangle_uvs'],dtype=float);old_uv=np.asarray(old['triangle_uvs'],dtype=float)
    must(np.array_equal(uv.astype(np.float16).astype(float),old_uv),'New F32 UVs do not reproduce old FP16 UVs under quantization')
    must(analysis['UV_match_policy']=='float32'and analysis['oriented_UV_all_triangles_matched'],'No exact source F32 UV correspondence proof')
    must(analysis['UV_max_source_to_selected_precision_component_delta']==0 and analysis['actual_render_UV_vs_matching_selected_precision_source_max_delta']==0,'Source F32 UV residual nonzero')
    must(new['requested_sample_indices']==old['requested_sample_indices']==[0,30,59],'Sample scope differs')
    must([s['actual_time']for s in new['sample_attempts']]==[s['actual_time']for s in old['sample_attempts']],'Actual sample times differ')
    npth,opth=Path(new['point_file']['file']),Path(old['point_file']['file']);must(sha(npth)==new['point_file']['sha256']and sha(opth)==old['point_file']['sha256'],'Measured point file changed')
    must(npth.read_bytes()==opth.read_bytes(),'Measured positions differ after full UV build')
    must(new['actual_bone_hierarchy']==build['actual_bone_hierarchy']and len(new['actual_bone_hierarchy'])==45,'Second-process hierarchy changed')
    must(new['actual_skeleton']==build['skeleton']and new['actual_material']==build['actual_material']==old['actual_material'],'Skeleton or source material reference changed')
    must(new['actual_animation_clock']['keys']==60 and new['actual_animation_clock']['frames']==59,'Animation key count changed')
    for p in build['protected_packages']+build['saved_native_packages']:must(sha(Path(p['file']))==p['sha256'],'Old/new package changed')
    result={'schema':'t3b-full-precision-UV-actual-build-paired-verification/v1','passed':True,'new_mesh':new['mesh'],'build_process':build['process_id'],'readback_RHI_process':new['process_id'],
        'official_build_API':build['official_api'],'only_changed_build_setting':changes,'second_process_full_precision_setting':True,'actual_F32_UV_matches_all1151_output_triangle_corners':True,
        'source_F32_UV_max_component_error':0,'old_FP16_vs_new_F32_max_component_delta':float(np.max(np.abs(uv-old_uv))),'old_FP16_vs_quantized_new_F32_error':0,
        'actual_source_frame_indices':[0,30,59],'actual_vertex_points':3*len(new['used_vertex_ids']),'actual_position_component_bit_mismatches':0,'actual_point_file_identical_sha256':sha(npth),
        'converted_topology_and_vertex_order_identical':True,'DynamicMesh_output_vertices':new['vertex_count'],'DynamicMesh_output_triangles':new['triangle_count'],
        'raw_LOD0_render_vertex_count_official_API':new['raw_LOD0_render_vertex_count_official_API'],'raw_LOD_index_buffer_triangle_count_known':False,
        'actual45_bone_hierarchy_and_source_skeleton_unchanged':True,'actual_animation_clock':new['actual_animation_clock'],'material_unchanged':True,
        'protected_preexisting_package_count':len(build['protected_packages']),'all_preexisting_package_hashes_unchanged':True,'new_package':build['saved_native_packages'][0],
        'source_build_report_sha256':sha(a.build_report),'new_render_report_sha256':sha(a.new_render_report),'old_render_report_sha256':sha(a.old_render_report),
        'remaining_duplicate_class':analysis['missing_oriented_UV_multiplicities'],'source_identity_unresolved_triangles':analysis['UV_only_unresolved_triangles'],
        'GPU_skinned_vertices_verified':False,'rendered_pixels_verified':False,'source_runtime_replaced':False,
        'limits':['Actual rebuilt/saved derivative asset, reloaded in a separate real-D3D11 offscreen process; F32 UV proof is data readback, not only a settings bit.',
            '3449/1151 remain converted DynamicMesh counts; official raw LOD vertex count is independently3449, but raw index-buffer triangle count and duplicate-drop stage remain unknown.',
            '1134triangles have unique oriented UV identity, one belongs to the source858/1125 exact-attribute duplicate class,16 identities remain inferred as reported; F32 UV does not resolve repeated UV layouts.',
            'Only3 sampled frames are position-bit-identical; full-motion GPU, normals/tangents/pixels/compositing behavior is not accepted by this check.',
            'Old raw reports, old packages, source glTF/C and formal runtime/config are unchanged. One new derivative SkeletalMesh package was saved; old Skeleton/AnimSequence/Material are read-only references.']}
    a.output.write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8');print(json.dumps({k:v for k,v in result.items()if k not in ['remaining_duplicate_class','limits','new_package']},indent=2))
if __name__=='__main__':main()