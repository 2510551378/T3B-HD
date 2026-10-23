"""Actual UE component evaluation -> GeometryScript skinned DynamicMesh probe."""
from datetime import datetime,timezone
import hashlib,json,os,struct,traceback
from pathlib import Path
import unreal
PROJECT=Path(unreal.Paths.convert_relative_path_to_full(unreal.Paths.project_dir())).resolve()
RUN=os.environ['T3B_NATIVE_RUN_ID'];OUTPUT=Path(os.environ['T3B_NATIVE_REPORT_PATH']);INPUT=Path(os.environ['T3B_NATIVE_SAVED_REPORT'])
R={'schema':'t3b-native-skinning-probe/v1','passed':False,'native_skinning_vertices_acquired':False,'ue_render_verified':False,'source_runtime_replaced':False}
def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def must(v,msg):
    if not v:raise RuntimeError(msg)
def vec(v):return [float(v.x),float(v.y),float(v.z)]
def tf(t):return {'translation':vec(t.translation),'scale':vec(t.scale3d),'quaternion':[t.rotation.x,t.rotation.y,t.rotation.z,t.rotation.w]}
def main():
    src=json.loads(INPUT.read_text(encoding='utf-8'));frozen=json.loads((PROJECT/'Validation/asset_import_runs/0fac54502ca140d4accffa2e5a7bc618/ue_editor_asset_creation.json').read_text(encoding='utf-8'))
    prior=json.loads((PROJECT/'Validation/native_import_runs/64e9826c75854a7ba8f7f36eabefb4cf/ue_native_import.json').read_text(encoding='utf-8'))
    packages=src['saved_native_packages']+frozen['saved_assets']+prior['saved_native_packages']
    R['source_import_report']={'file':str(INPUT),'sha256':digest(INPUT),'gltf':src['source_gltf']}
    R['native_candidate_kind']=src.get('candidate_kind','original')
    def unchanged():
        for p in packages:must(digest(Path(p['file']))==p['sha256'],'Existing package changed: '+p['file'])
    unchanged();mesh=unreal.load_asset(src['skeletal_meshes'][0]['asset']);animation=unreal.load_asset(src['animations'][0]['asset'])
    R['API_docs']={}
    for clsname,methods in {'GeometryScript_SceneUtils':['copy_mesh_from_component'],'GeometryScript_MeshQueries':['get_all_vertex_positions','get_vertex_position','get_all_triangle_indices','get_triangle_u_vs','get_triangle_normals'],'GeometryScript_List':['convert_vector_list_to_array','convert_triangle_list_to_array'],'SkeletalMeshComponent':['override_animation_data','get_bone_transform'],'EditorActorSubsystem':['spawn_actor_from_class']}.items():
        cls=getattr(unreal,clsname,None);R['API_docs'][clsname]={m:getattr(getattr(cls,m,None),'__doc__',None)for m in methods}
    world=unreal.EditorLoadingAndSavingUtils.new_blank_map(False);must(world is not None,'No temporary editor world')
    force_raw_requested=os.environ.get('T3B_NATIVE_FORCE_RAW','0')=='1'
    R['raw_sampling_control']={'requested_force_raw':force_raw_requested,'CVar_before':unreal.SystemLibrary.get_console_variable_int_value('a.ForceEvalRawData')}
    if force_raw_requested:unreal.SystemLibrary.execute_console_command(world,'a.ForceEvalRawData 1')
    R['raw_sampling_control']['CVar_after']=unreal.SystemLibrary.get_console_variable_int_value('a.ForceEvalRawData')
    must(R['raw_sampling_control']['CVar_after']==int(force_raw_requested),'Actual ForceEvalRawData CVar does not match requested isolated sampling policy')
    R['raw_sampling_control']['source_branch']='AnimSequence.cpp:3692-3702: CanEvaluateRawAnimationData() && (GForceRawData==1 || other conditions); GetBonePose:1765 and1853-1859 evaluates DataModelInterface when raw condition holds. The CVar guarantees raw when raw animation data is evaluable.'
    actor=unreal.get_editor_subsystem(unreal.EditorActorSubsystem).spawn_actor_from_class(unreal.SkeletalMeshActor,unreal.Vector(0,0,0),unreal.Rotator(0,0,0),True)
    must(actor is not None,'Cannot spawn isolated transient SkeletalMeshActor')
    component=actor.get_component_by_class(unreal.SkeletalMeshComponent);component.set_skinned_asset_and_update(mesh,True)
    component.set_editor_property('visibility_based_anim_tick_option',unreal.VisibilityBasedAnimTickOption.ALWAYS_TICK_POSE_AND_REFRESH_BONES)
    R['geometry_query_members']=[x for x in dir(unreal.GeometryScript_MeshQueries)if any(k in x for k in ['uv','triangle','normal'])]
    R['component']=component.get_path_name();R['actual_material_reference']=component.get_material(0).get_path_name()
    Q=unreal.GeometryScript_MeshQueries;U=unreal.GeometryScript_SceneUtils
    gltf_dir=PROJECT.parent/'psp_parse/out/AYA_NATIVE_GLTF_20261020'
    times=json.loads((gltf_dir/'provenance.json').read_text(encoding='utf-8'))['actual_times_seconds']
    R['sample_attempts']=[];R['skinning_method']='GeometryScript SourceModel -> FSkeletalMeshOperations::GetPosedMesh with real component animation transforms; NOT render-buffer GetCPUSkinnedVertices.'
    R['render_buffer_limit']='FApp::CanEverRender is false with -NullRHI (App.h:400-406), so MeshObject is absent; prior attempted RenderData path failed. No GPU/render-buffer acceptance.'
    R['alignment']={'matrix_rows':[[0,1,0,0],[1,0,0,0],[0,0,1,0],[0,0,0,1]],'determinant':-1,'implementation':'temporary actor yaw90deg and scale(1,-1,1); world DynamicMesh copy applies full component transform','existing_assets_changed':False}
    local_path=OUTPUT.parent/'native_source_model_local_cm.f64';aligned_path=OUTPUT.parent/'native_source_model_aligned_PMC_cm.f64'
    component.override_animation_data(animation,False,False,0.,1.)
    def copy(world_space):
        dm=unreal.DynamicMesh();opts=unreal.GeometryScriptCopyMeshFromComponentOptions();lod=unreal.GeometryScriptMeshReadLOD();lod.set_editor_property('lod_type',unreal.GeometryScriptLODType.SOURCE_MODEL);lod.set_editor_property('lod_index',0);opts.set_editor_property('requested_lod',lod)
        copied,world_transform,outcome=U.copy_mesh_from_component(component,dm,opts,world_space)
        must(outcome==unreal.GeometryScriptOutcomePins.SUCCESS,'Actual native SourceModel copy failed')
        return dm,world_transform
    with local_path.open('wb')as local_file,aligned_path.open('wb')as aligned_file:
        for frame,time in enumerate(times):
            actor.set_actor_rotation(unreal.Rotator(0,0,0),False);actor.set_actor_scale3d(unreal.Vector(1,1,1))
            component.set_position(time,False)
            component.override_animation_data(animation,False,False,time,1.)
            actual_time=component.get_position();must(abs(actual_time-time)<2e-6,'Actual component time differs from requested source sample')
            sample={'frame':frame,'requested_time':time,'actual_position':actual_time,'component_world':tf(component.get_world_transform()),'bones':[{'name':str(component.get_bone_name(i)),'world':tf(component.get_bone_transform(component.get_bone_name(i)))}for i in range(component.get_num_bones())]}
            R['sample_attempts'].append(sample)
            dm,world_transform=copy(False)
            if frame==0:
                triangles=[];used=set();uvs=[];normals=[]
                for ti in range(Q.get_num_triangle_i_ds(dm)):
                    tri,valid=Q.get_triangle_indices(dm,ti);must(valid,'Triangle gap')
                    indices=[int(tri.x),int(tri.y),int(tri.z)];triangles.append(indices);used.update(indices)
                    uv=Q.get_triangle_u_vs(dm,0,ti);uvs.append([[float(v.x),float(v.y)]for v in uv[:3]])
                    nr=Q.get_triangle_normals(dm,ti);normals.append([vec(v)for v in nr[1:4]])
                ids=sorted(used)
                R.update(source_description_total_vertices=Q.get_vertex_count(dm),source_description_unreferenced_vertices=Q.get_vertex_count(dm)-len(ids),max_referenced_vertex_id=max(ids),connected_vertex_count=len(ids),used_vertex_ids=ids,triangles=triangles,triangle_uvs=uvs,first_frame_triangle_normals=normals)
                must(len(ids)==3456 and len(triangles)==1152,'Unexpected actual native connected geometry count')
            positions=[]
            for i in ids:
                v,valid=Q.get_vertex_position(dm,i);must(valid,'Unexpected connected vertex gap');positions.append(vec(v));local_file.write(struct.pack('<3d',v.x,v.y,v.z))
            actor.set_actor_rotation(unreal.Rotator(pitch=0,yaw=90,roll=0),False);actor.set_actor_scale3d(unreal.Vector(1,-1,1))
            aligned,aligned_world=copy(True);sample['aligned_component_world']=tf(aligned_world)
            sample['alignment_basis_readback']=[vec(aligned_world.transform_location(unreal.Vector(*v)))for v in [(0,0,0),(1,0,0),(0,1,0),(0,0,1)]]
            max_error=0.
            for idx,i in enumerate(ids):
                v,valid=Q.get_vertex_position(aligned,i);must(valid,'Aligned copy lost connected vertex');aligned_file.write(struct.pack('<3d',v.x,v.y,v.z));old=positions[idx]
                max_error=max(max_error,abs(v.x-old[1]),abs(v.y-old[0]),abs(v.z-old[2]))
            sample['actual_world_alignment_max_component_error_cm']=max_error
            if frame==0:
                R['aligned_first_triangle_indices']=[];R['aligned_first_triangle_normals']=[]
                for ti in range(min(12,Q.get_num_triangle_i_ds(aligned))):
                    tri,valid=Q.get_triangle_indices(aligned,ti);R['aligned_first_triangle_indices'].append([tri.x,tri.y,tri.z])
                    nr=Q.get_triangle_normals(aligned,ti);R['aligned_first_triangle_normals'].append([vec(v)for v in nr[1:4]])
            R['native_skinning_vertices_acquired']=True
    R['raw_sampling_control']['CVar_final']=unreal.SystemLibrary.get_console_variable_int_value('a.ForceEvalRawData')
    must(R['raw_sampling_control']['CVar_final']==int(force_raw_requested),'ForceEvalRawData changed during capture')
    R['point_files']=[{'file':str(path),'sha256':digest(path),'bytes':path.stat().st_size,'format':'<sample, used_vertex_id order, xyz float64 LE; centimeters>','frames':len(times),'vertices':3456}for path in [local_path,aligned_path]]
    R['alignment_numeric_verified']=all(s['actual_world_alignment_max_component_error_cm']<1e-8 for s in R['sample_attempts'])
    unchanged();R['previous161_and_native3_packages_unchanged']=True;R['asset_writes_performed']=False;R['passed']=R['native_skinning_vertices_acquired']and R['alignment_numeric_verified']and len(R['sample_attempts'])==60
if __name__=='__main__':
    try:main()
    except Exception as e:R['error']=str(e);R['traceback']=traceback.format_exc();raise
    finally:
        R.update(run_id=RUN,process_id=os.getpid(),script_sha256=digest(Path(__file__)),engine_version=unreal.SystemLibrary.get_engine_version(),finished_utc=datetime.now(timezone.utc).isoformat())
        OUTPUT.write_text(json.dumps(R,indent=2)+'\n',encoding='utf-8')