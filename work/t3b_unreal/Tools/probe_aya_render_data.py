"""Read actual UE RenderData CPU-skinned vertices with an offscreen real RHI.

This does not read GPU-skinned vertices or prove final rendered pixels.
Existing source/candidate packages are fingerprinted without saving them.
"""
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import struct
import traceback
import unreal

PROJECT = Path(unreal.Paths.convert_relative_path_to_full(unreal.Paths.project_dir())).resolve()
OUTPUT = Path(os.environ['T3B_RENDER_DATA_REPORT'])
INPUT = Path(os.environ['T3B_RENDER_DATA_IMPORT_REPORT'])
RUN = os.environ['T3B_RENDER_DATA_RUN_ID']
R = {'schema':'t3b-native-render-data-probe/v1','passed':False,
     'render_data_cpu_vertices_acquired':False,'GPU_skinned_vertices_read':False,
     'rendered_pixels_verified':False,'source_runtime_replaced':False}


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def check(value, message):
    if not value:
        raise RuntimeError(message)


def flush():
    OUTPUT.write_text(json.dumps(R,indent=2)+'\n',encoding='utf-8')


def main():
    imported = json.loads(INPUT.read_text(encoding='utf-8-sig'))
    original = json.loads((PROJECT/'Validation/asset_import_runs/0fac54502ca140d4accffa2e5a7bc618/ue_editor_asset_creation.json').read_text(encoding='utf-8'))
    packages = imported['saved_native_packages']+original['saved_assets']+imported.get('protected_packages', [])
    def unchanged():
        for item in packages:
            check(sha(Path(item['file'])) == item['sha256'],'Existing package changed: '+item['file'])
    unchanged()
    mesh = unreal.load_asset(imported['skeletal_meshes'][0]['asset'])
    animation = unreal.load_asset(imported['animations'][0]['asset'])
    check(mesh is not None and animation is not None,'Saved native candidates failed to load')
    R.update(input_report=str(INPUT),input_report_sha256=sha(INPUT),mesh=mesh.get_path_name(),animation=animation.get_path_name())
    world = unreal.EditorLoadingAndSavingUtils.new_blank_map(False)
    check(world is not None,'No temporary editor world')
    R['actual_force_raw_cvar'] = unreal.SystemLibrary.get_console_variable_int_value('a.ForceEvalRawData')
    check(R['actual_force_raw_cvar'] == 0,'Expected untouched default animation sampling policy')
    actor = unreal.get_editor_subsystem(unreal.EditorActorSubsystem).spawn_actor_from_class(
        unreal.SkeletalMeshActor,unreal.Vector(0,0,0),unreal.Rotator(0,0,0),True)
    check(actor is not None,'No temporary SkeletalMeshActor')
    component = actor.get_component_by_class(unreal.SkeletalMeshComponent)
    component.set_skinned_asset_and_update(mesh,True)
    component.set_editor_property('visibility_based_anim_tick_option',unreal.VisibilityBasedAnimTickOption.ALWAYS_TICK_POSE_AND_REFRESH_BONES)
    component.override_animation_data(animation,False,False,0.,1.)
    R['actual_material'] = component.get_material(0).get_path_name()
    editor_subsystem = unreal.get_editor_subsystem(unreal.SkeletalMeshEditorSubsystem)
    settings = unreal.SkeletalMeshEditorSubsystem.get_lod_build_settings(mesh,0)
    R['LOD0_full_precision_UVs_setting'] = bool(settings.get_editor_property('use_full_precision_u_vs'))
    R['raw_LOD0_render_vertex_count_official_API'] = editor_subsystem.get_num_verts(mesh,0)
    if imported.get('full_precision_UVs_expected'):
        check(R['LOD0_full_precision_UVs_setting'],'New candidate full-precision UV setting was not retained after reload')
    R['actual_bone_hierarchy'] = [{'index':i,'name':str(component.get_bone_name(i)),'parent':str(component.get_parent_bone(component.get_bone_name(i)))} for i in range(component.get_num_bones())]
    model = animation.get_editor_property('data_model_interface')
    R['actual_animation_clock'] = {'keys':model.get_number_of_keys(),'frames':model.get_number_of_frames(),'length_seconds':model.get_play_length()}
    R['actual_skeleton'] = mesh.get_editor_property('skeleton').get_path_name()
    R['path'] = 'GeometryScript explicit RenderData -> SkinnedMeshComponentToDynamicMesh -> GetCPUSkinnedVertices; real RHI permits MeshObject creation; CPU skinning is not GPU vertex readback.'
    R['sample_attempts'] = []
    provenance = PROJECT.parent/'psp_parse/out/AYA_NATIVE_GLTF_20261020/provenance.json'
    times = json.loads(provenance.read_text(encoding='utf-8'))['actual_times_seconds']
    indices = [0,30,59]
    R['requested_sample_indices'] = indices
    R['source_provenance_sha256'] = sha(provenance)
    output_points = OUTPUT.parent/'render_data_local_cm.f64'
    Q = unreal.GeometryScript_MeshQueries
    with output_points.open('wb') as stream:
        for frame in indices:
            time = times[frame]
            component.set_position(time,False)
            component.override_animation_data(animation,False,False,time,1.)
            actual = component.get_position()
            check(abs(time-actual) < 2e-6,'Actual native animation time differs')
            sample = {'source_frame':frame,'requested_time':time,'actual_time':actual}
            R['sample_attempts'].append(sample)
            flush()
            options = unreal.GeometryScriptCopyMeshFromComponentOptions()
            lod = unreal.GeometryScriptMeshReadLOD()
            lod.set_editor_property('lod_type',unreal.GeometryScriptLODType.RENDER_DATA)
            lod.set_editor_property('lod_index',0)
            options.set_editor_property('requested_lod',lod)
            dm = unreal.DynamicMesh()
            _,_,outcome = unreal.GeometryScript_SceneUtils.copy_mesh_from_component(component,dm,options,False)
            sample['copy_outcome'] = str(outcome)
            check(outcome == unreal.GeometryScriptOutcomePins.SUCCESS,'Actual RenderData copy failed')
            if frame == indices[0]:
                triangles = []
                uvs = []
                used = set()
                for ti in range(Q.get_num_triangle_i_ds(dm)):
                    tri,valid = Q.get_triangle_indices(dm,ti)
                    check(valid,'Unexpected triangle ID gap')
                    ids = [int(tri.x),int(tri.y),int(tri.z)]
                    triangles.append(ids)
                    used.update(ids)
                    uv = Q.get_triangle_u_vs(dm,0,ti)
                    check(uv[-1],'Triangle UV read failed')
                    uvs.append([[v.x,v.y] for v in uv[:3]])
                ids = sorted(used)
                R.update(vertex_count=Q.get_vertex_count(dm),triangle_count=len(triangles),
                         used_vertex_ids=ids,triangles=triangles,triangle_uvs=uvs,
                         source_triangle_count=1152,triangle_count_matches_source=len(triangles)==1152,
                         topology_fidelity_verified=False)
                flush()
                # Acquisition is not topology acceptance. Retain changed triangles
                # for independent analysis instead of discarding their geometry.
                check(0 < len(triangles) <= 1152,'Actual RenderData triangle count outside acquisition bounds')
            for index in ids:
                v,valid = Q.get_vertex_position(dm,index)
                check(valid,'RenderData vertex ID gap')
                stream.write(struct.pack('<3d',v.x,v.y,v.z))
            sample['points_written'] = len(ids)
            flush()
    R['point_file'] = {'file':str(output_points),'bytes':output_points.stat().st_size,'sha256':sha(output_points),
                       'format':'<source sample index, used_vertex_ids order, xyz float64 LE; centimeters>'}
    unchanged()
    R['all_existing_packages_unchanged'] = True
    R['render_data_cpu_vertices_acquired'] = True
    R['passed'] = True


if __name__ == '__main__':
    R.update(run_id=RUN,process_id=os.getpid(),script_sha256=sha(Path(__file__)),
             engine_version=unreal.SystemLibrary.get_engine_version())
    try:
        main()
    except Exception as error:
        R.update(error=str(error),traceback=traceback.format_exc())
        unreal.log_error(str(error))
    finally:
        R['finished_utc'] = datetime.now(timezone.utc).isoformat()
        flush()
    if not R['passed']:
        raise RuntimeError(R.get('error','RenderData probe incomplete'))
