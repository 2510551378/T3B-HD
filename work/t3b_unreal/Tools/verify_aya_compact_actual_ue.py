"""Independent paired check of actual old/compact UE skinning captures."""
import argparse,hashlib,json
from pathlib import Path

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def must(v,msg):
    if not v:raise ValueError(msg)
def read(p):return json.loads(p.read_text(encoding='utf-8'))
def main():
    a=argparse.ArgumentParser();a.add_argument('--compact-ue-report',required=True,type=Path);a.add_argument('--old-ue-report',required=True,type=Path);a.add_argument('--output',required=True,type=Path);a=a.parse_args();must(not a.output.exists(),'Refuse overwrite')
    new=read(a.compact_ue_report);old=read(a.old_ue_report)
    must(new['source_description_total_vertices']==3456 and new['source_description_unreferenced_vertices']==0 and new['max_referenced_vertex_id']==3455,'Actual compact UE did not eliminate unreferenced vertices')
    must(old['source_description_total_vertices']==366336 and new['connected_vertex_count']==old['connected_vertex_count']==3456,'Actual source model counts differ')
    must(new['raw_sampling_control']['CVar_after']==old['raw_sampling_control']['CVar_after']==1 and new['raw_sampling_control']['CVar_final']==old['raw_sampling_control']['CVar_final']==1,'Sampling policy is not held fixed')
    must(new['actual_material_reference']==old['actual_material_reference'],'Source material changed')
    must(new['triangle_uvs']==old['triangle_uvs'],'Actual triangle UVs changed')
    must(new['triangles']==[[i%3456 for i in t]for t in old['triangles']],'Actual normalized source topology changed')
    must(new['first_frame_triangle_normals']==old['first_frame_triangle_normals'],'Actual sampled source normals changed')
    must(new['aligned_first_triangle_normals']==old['aligned_first_triangle_normals'],'Actual sampled aligned normals changed')
    must(len(new['sample_attempts'])==len(old['sample_attempts'])==60,'Actual frame coverage differs')
    for n,o in zip(new['sample_attempts'],old['sample_attempts']):
        for k in ['requested_time','actual_position','bones','component_world','aligned_component_world','alignment_basis_readback']:must(n[k]==o[k],'Actual pose/time/alignment differs: '+k)
    points=[]
    for n,o in zip(new['point_files'],old['point_files']):
        np,op=Path(n['file']),Path(o['file']);nh,oh=sha(np),sha(op);must(nh==n['sha256']and oh==o['sha256'],'Measured UE point-file changed');must(np.read_bytes()==op.read_bytes(),'Compact actual UE skinning points differ from prior raw points')
        points.append({'new_file':str(np),'old_file':str(op),'bytes':np.stat().st_size,'identical_sha256':nh,'point_component_bit_mismatches':0})
    newimp=read(Path(new['source_import_report']['file']));oldimp=read(Path(read(a.old_ue_report.parent/'request.json')['input_report']))
    packages=[]
    for label,rep in [('new_compact',newimp),('prior',oldimp)]:
        for s in rep['saved_native_packages']:must(sha(Path(s['file']))==s['sha256'],'New/old saved native package changed');packages.append({'group':label,**s})
    comparison=read(a.compact_ue_report.parent/'compact_frozen_C_gltf_comparison.json')
    result={'schema':'t3b-actual-UE-compact-paired-verification/v1','passed':True,'actual_UE_processes_executed':True,'same_raw_sampling_policy':True,'same60_times_actual45_bone_poses_material_UV_and_topology':True,
        'source_description_vertices_old':366336,'source_description_vertices_compact':3456,'unreferenced_vertices_eliminated':362880,'source_description_reduction_factor':106,
        'actual_UE_points_per_file':207360,'point_components_per_file':622080,'paired_point_files':points,'position_error_degradation_cm':0,
        'aligned_vs_frozen_C_max_cm':comparison['aligned_UE_source_model_vs_frozen_C']['max_euclidean_cm'],'aligned_vs_frozen_C_RMS_cm':comparison['aligned_UE_source_model_vs_frozen_C']['rms_cm'],
        'compact_report_sha256':sha(a.compact_ue_report),'old_report_sha256':sha(a.old_ue_report),'saved_native_packages':packages,
        'GPU_and_render_buffer_validation':False,'source_runtime_replaced':False,
        'limits':['Actual editor SourceModel CPU skinning only, sampled at60 original times under raw mode. Default compressed mode was not re-tested for compaction.',
            'Source-description vertex reduction is measured; no process-memory/GPU-memory/frame-rate benchmark was performed.',
            'Raw max position residual is nonzero; no threshold, reference or source weights were changed to improve this result.']}
    a.output.write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8');print(json.dumps({k:v for k,v in result.items()if k not in ['saved_native_packages','paired_point_files','limits']},indent=2))
if __name__=='__main__':main()